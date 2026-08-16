from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from idolmv_pipeline.seedance import tunnel
from idolmv_pipeline.seedance.client import SeedanceClient
from idolmv_pipeline.seedance.media import extract_audio, extract_check_frame, mux_audio, pad_audio_to, probe_duration, trim_reference
from idolmv_pipeline.seedance.state import RunState
from idolmv_pipeline.video_tasks.manifest import write_manifest
from idolmv_pipeline.video_tasks.models import AnchorSpec, PromptVariant, ReferenceSpec, VideoTaskAdapter
from idolmv_pipeline.video_tasks.planner import (
    BUILD_AND_UPLOAD,
    NEED_MATERIAL_REBIND,
    NEED_SOURCE_FOR_REBUILD,
    REUSE_REMOTE,
    UPLOAD_EXISTING_ARTIFACT,
    VISIBILITY_IDENTIFIABLE,
    VISIBILITY_OPAQUE,
    InspectedMaterial,
    AssetDecision,
    plan_material,
)


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def _fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


# 处理器版本：处理产物的生成逻辑一旦变化（影响产物内容），递增此值以强制重建缓存。
# Phase 1 引入 Artifact Signature，把「源文件指纹 + 处理参数 + 处理器版本」一起纳入产物缓存判断。
_PROCESSOR_VERSION = 2


def _read_signature(marker_path: Path) -> str | None:
    """读取 marker 中记录的 Artifact Signature；旧格式（仅源指纹）或无文件返回 None。"""
    if marker_path and marker_path.exists():
        try:
            data = json.loads(marker_path.read_text())
            sig = data.get("signature")
            return sig if isinstance(sig, str) and sig else None
        except Exception:
            return None
    return None


def _artifact_signature(source_fp: dict | None, transform: dict) -> str:
    """计算产物缓存签名 = hash(源文件指纹 + 处理参数 transform + 处理器版本)。
    任一变化 → 签名变化 → 产物重建 → asset 自动重传。"""
    payload = {
        "source": source_fp,
        "transform": transform,
        "processor": _PROCESSOR_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _fingerprint_content_same(a: dict | None, b: dict | None) -> bool:
    """比较两个指纹的「内容」是否一致（忽略 path，只看 size + mtime_ns）。
    用于判断源文件是否真的被编辑：同一文件移动到不同路径（如 anchors/ 与 anchors/selected/）
    不应被视为"已修改"。"""
    if not a or not b:
        return False
    return a.get("size") == b.get("size") and a.get("mtime_ns") == b.get("mtime_ns")


def _write_marker(marker_path: Path, signature: str, source_fp: dict | None, transform: dict) -> None:
    """写入 Artifact Signature marker（含源指纹与 transform，便于排查）。"""
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps({
        "signature": signature,
        "source": source_fp,
        "transform": transform,
        "processor": _PROCESSOR_VERSION,
    }, ensure_ascii=False))


class VideoTaskRunner:
    def __init__(self, adapter: VideoTaskAdapter, client: SeedanceClient | None = None, progress=None):
        self.adapter = adapter
        self.client = client or SeedanceClient(model=adapter.model)
        self.progress = progress or (lambda **_: None)
        self._state_lock = threading.Lock()

    def _progress(self, stage: str, message: str, **values) -> None:
        self.progress(stage=stage, message=message, **values)

    def validate(self) -> list[str]:
        errors = []
        if not self.adapter.anchors:
            errors.append("anchors must not be empty")
        if not self.adapter.references:
            errors.append("references must not be empty")
        keys = [anchor.key for anchor in self.adapter.anchors]
        if len(keys) != len(set(keys)):
            errors.append("anchor keys must be unique")
        for anchor in self.adapter.anchors:
            if not (self.adapter.task_dir / anchor.file).is_file():
                errors.append(f"missing anchor: {anchor.file}")
            if anchor.prompt_variant and anchor.prompt_variant not in {prompt.name for prompt in self.adapter.prompts}:
                errors.append(f"unknown prompt variant for {anchor.key}: {anchor.prompt_variant}")
        for reference in self.adapter.references:
            if not (self.adapter.task_dir / reference.file).is_file():
                errors.append(f"missing reference: {reference.file}")
            if reference.audio_file and not (self.adapter.task_dir / reference.audio_file).is_file():
                errors.append(f"missing reference audio: {reference.audio_file}")
        if self.adapter.mode in {"lip_sync", "dance_lip_sync"} or self.adapter.kind == "singing":
            lyrics = str(self.adapter.metadata.get("lyrics_text") or "")
            if self.adapter.lyrics_file:
                lyrics_path = self.adapter.task_dir / self.adapter.lyrics_file
                if not lyrics_path.is_file() or not lyrics_path.read_text().strip():
                    errors.append(f"missing or empty lyrics: {self.adapter.lyrics_file}")
            elif not lyrics.strip():
                errors.append("singing task requires lyrics_file or metadata.lyrics_text")
        return errors

    # ── work 产物双路径 ──────────────────────────────────────────────────────
    # 新路径 = 任务级 work 目录（<dir>/<task>/<ref>/，多任务共文件夹互不覆盖）；
    # 旧路径 = 文件夹级共享目录（<dir>/<ref>/，历史产物所在地），只读回退：
    # 存量产物与 marker 继续有效（复用证明不失效、不触发一次性重传），重建才写新路径。

    def _work_artifact(self, reference: ReferenceSpec, filename: str) -> tuple[Path, Path | None]:
        new = self.adapter.work_dir / reference.name / filename
        legacy_dir = self.adapter.metadata.get("legacy_work_dir")
        old = (Path(legacy_dir) / reference.name / filename) if legacy_dir else None
        return new, old

    def _artifact_target(self, reference: ReferenceSpec, filename: str) -> Path:
        """重建时的写入目标（永远写任务级新路径）。"""
        return self._work_artifact(reference, filename)[0]

    def _artifact_existing(self, reference: ReferenceSpec, filename: str) -> Path:
        """读取/上传用的现存产物路径：新路径优先，回退旧共享路径。"""
        new, old = self._work_artifact(reference, filename)
        if new.exists():
            return new
        if old and old.exists():
            return old
        return new

    def _read_json_any(self, reference: ReferenceSpec, filename: str):
        """从新/旧两处读 marker JSON，先新后旧；都没有返回 None。"""
        for path in self._work_artifact(reference, filename):
            if path and path.exists():
                try:
                    return json.loads(path.read_text())
                except Exception:
                    return None
        return None

    def _read_signature_any(self, reference: ReferenceSpec, marker_name: str) -> str | None:
        for path in self._work_artifact(reference, marker_name):
            if path and path.exists():
                sig = _read_signature(path)
                if sig:
                    return sig
        return None

    def _reference_audio(self, reference: ReferenceSpec) -> Path:
        return self._artifact_existing(reference, "audio.mp3")

    def _reference_audio_padded(self, reference: ReferenceSpec) -> Path:
        return self._artifact_existing(reference, "audio_padded.mp3")

    def _reference_segment(self, reference: ReferenceSpec, index: int = 0) -> Path:
        return self._artifact_existing(reference, f"segment_{index:02d}.mp4")

    def _max_duration_for_model(self) -> int:
        model = self.adapter.model or "sd2.5"
        return 30 if "sd2.5" in model else 15

    def _segments(self, reference: ReferenceSpec) -> list[tuple[float, float, int, float, str]]:
        """Returns list of (start, cut_duration, seedance_duration, original_total, pad_mode).
        original_total is the raw duration before padding, used to trim padding later."""
        total = probe_duration(self.adapter.task_dir / reference.file)
        if reference.split_mode == "fixed":
            return [(segment.start, segment.cut_duration or total - segment.start, segment.seedance_duration, total, "back") for segment in reference.segments]
        max_duration = self._max_duration_for_model()
        pad_mode = getattr(reference, "pad_mode", "back")
        # 超时长：直接截断到 max_duration，时长对齐失去意义，归一为 none
        if total > max_duration:
            pad_mode = "none"
        ceil_total = min(math.ceil(total), max_duration)
        seedance_duration = max(4, ceil_total)
        if pad_mode == "none":
            # 不补齐：超时长截断到 ceil_total；正常 none 保持原始时长
            cut_duration = ceil_total if total > max_duration else total
            return [(0.0, cut_duration, seedance_duration, total, "none")]
        return [(0.0, ceil_total, seedance_duration, total, pad_mode)]

    def prepare(self) -> None:
        self._progress("validating", "正在校验任务素材")
        errors = self.validate()
        if errors:
            raise ValueError("Invalid video task:\n- " + "\n- ".join(errors))
        self._progress("preparing", "正在处理参考视频和音频")
        for reference in self.adapter.references:
            segments = self._segments(reference)
            # 写入走任务级新路径；现存产物（新或旧共享路径）有效则直接复用，不重建不搬迁
            audio = self._artifact_target(reference, "audio.mp3")
            audio_cur = self._artifact_existing(reference, "audio.mp3")
            source = self.adapter.task_dir / (reference.audio_file or reference.file)
            # 用源文件指纹判断是否需要重新生成音频缓存，避免切换音视频后沿用旧的 work_dir 缓存
            fingerprint_marker = audio.with_name("audio.src.json")
            current_fp = _fingerprint(source) if source.exists() else None
            cached_fp = self._read_json_any(reference, "audio.src.json")
            audio_refreshed = False
            if not audio_cur.exists() or cached_fp != current_fp:
                if reference.pass_reference_video:
                    # 视频模式：从视频提取音频
                    extract_audio(source, audio)
                else:
                    # 纯音频模式：reference.file 本身就是音频，直接拷贝（对等视频提取音频，不再二次转码）
                    shutil.copyfile(source, audio)
                if current_fp is not None:
                    fingerprint_marker.write_text(json.dumps(current_fp))
                else:
                    # 源缺失时清掉过期标记，避免残留指纹让后续 inspect 误判缓存仍有效
                    fingerprint_marker.unlink(missing_ok=True)
                audio_refreshed = True
                audio_cur = audio
            pad_mode = segments[0][4] if segments else "back"
            if segments and len(segments) == 1:
                seedance_duration = segments[0][2]
                actual = probe_duration(audio_cur)
                if actual < seedance_duration and reference.pass_reference_audio:
                    padded = self._artifact_target(reference, "audio_padded.mp3")
                    padded_cur = self._artifact_existing(reference, "audio_padded.mp3")
                    # 补齐音频的内容依赖 pad_mode + seedance_duration + 源音频，用 Artifact Signature 判断是否重建
                    padded_transform = {"kind": "audio_padded", "pad_mode": pad_mode, "seedance_duration": seedance_duration}
                    padded_signature = _artifact_signature(current_fp, padded_transform)
                    padded_marker = padded.with_name("audio_padded.src.json")
                    cached_padded_sig = self._read_signature_any(reference, "audio_padded.src.json")
                    if not padded_cur.exists() or audio_refreshed or cached_padded_sig != padded_signature:
                        pad_audio_to(audio_cur, padded, seedance_duration, pad_mode=pad_mode)
                        _write_marker(padded_marker, padded_signature, current_fp, padded_transform)
                        padded_cur = padded
                    object.__setattr__(reference, 'audio_file_url', str(padded_cur.resolve()))
                elif reference.pass_reference_audio and not reference.audio_file_url:
                    object.__setattr__(reference, 'audio_file_url', str(audio_cur.resolve()))
            elif reference.pass_reference_audio and not reference.audio_file_url:
                object.__setattr__(reference, 'audio_file_url', str(audio_cur.resolve()))
            # 纯口型模式（pass_reference_video=False）下 reference.file 是纯音频文件，
            # 不做视频切片/check frame，只准备音频（上面已处理）。
            if not reference.pass_reference_video:
                continue
            for index, (start, duration, _, original_total, seg_pad_mode) in enumerate(segments):
                segment = self._artifact_target(reference, f"segment_{index:02d}.mp4")
                segment_cur = self._artifact_existing(reference, f"segment_{index:02d}.mp4")
                seg_source = self.adapter.task_dir / reference.file
                seg_fp = _fingerprint(seg_source) if seg_source.exists() else None
                seg_marker = segment.with_name(f"segment_{index:02d}.src.json")
                # 切片内容依赖源视频 + 截取参数（start/duration/crop/pad_mode/original_duration），
                # 用 Artifact Signature 判断是否重建（更换 pad_mode/split/crop 会触发）
                seg_transform = {
                    "kind": "segment",
                    "start": start,
                    "duration": duration,
                    "crop_filter": reference.crop_filter,
                    "pad_mode": seg_pad_mode,
                    "original_duration": original_total,
                }
                seg_signature = _artifact_signature(seg_fp, seg_transform)
                cached_seg_sig = self._read_signature_any(reference, f"segment_{index:02d}.src.json")
                if not segment_cur.exists() or cached_seg_sig != seg_signature:
                    trim_reference(seg_source, segment, start, duration, reference.crop_filter, pad_mode=seg_pad_mode, original_duration=original_total)
                    _write_marker(seg_marker, seg_signature, seg_fp, seg_transform)
                    segment_cur = segment
                check_frame = segment_cur.with_name(f"segment_{index:02d}_check.jpg")
                if not check_frame.exists():
                    extract_check_frame(segment_cur, check_frame)

    def _load_assets(self) -> dict:
        return json.loads(self.adapter.assets_file.read_text()) if self.adapter.assets_file.exists() else {}

    def _save_assets(self, assets: dict) -> None:
        self.adapter.assets_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.adapter.assets_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(assets, indent=2, ensure_ascii=False))
        temporary.replace(self.adapter.assets_file)

    def _append_asset_ledger(self, key: str, path: Path, assets: dict) -> None:
        """资产台账（append-only）：每次上传成功追加一行，永不删除、清缓存不清除。

        assets.json 里的记录会被后续重传覆盖（同 key 换内容时理应如此），台账是
        唯一完整历史：任何被覆盖的 asset_id 都能按任务/key/指纹/transform 找回。"""
        try:
            entry = {
                "time": datetime.now().isoformat(timespec="seconds"),
                "task": self.adapter.name,
                "key": key,
                "asset_id": assets.get(key),
                "source": assets.get(f"{key}__source"),
                "transform": assets.get(f"{key}__transform"),
                "artifact": str(path),
            }
            ledger = self.adapter.assets_file.parent / "asset_ledger.jsonl"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with ledger.open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # 台账写失败不阻断上传主流程
            logger.warning("asset ledger append failed for %s", key, exc_info=True)

    def _anchor_asset_key(self, anchor: AnchorSpec) -> str:
        # key 按任务隔离（多任务共文件夹时，各任务的素材互不抢 key、不互相顶缓存）；
        # 显式 anchor_asset_keys 映射优先（保持自定义能力，格式不变）
        custom = self.adapter.metadata.get("anchor_asset_keys", {}).get(anchor.key)
        if custom:
            return custom
        return f"anchor_{_safe(self.adapter.name)}_{anchor.key}"

    def _reference_asset_key(self, reference: ReferenceSpec, index: int) -> str:
        custom = self.adapter.metadata.get("reference_asset_keys", {}).get(f"{reference.name}:{index}")
        if custom:
            return custom
        return f"reference_{_safe(self.adapter.name)}_{reference.name}_{index:02d}"

    def _audio_asset_key(self, reference: ReferenceSpec) -> str:
        return f"{_safe(self.adapter.name)}_{reference.name}:audio"

    def _legacy_asset_keys(self, anchor: AnchorSpec | None = None, reference: ReferenceSpec | None = None, index: int | None = None) -> list[str]:
        """旧版（按文件夹位置命名、无任务前缀）的 key 列表，作只读回退用。"""
        keys = []
        if anchor is not None:
            keys.append(f"anchor_{anchor.key}")
        if reference is not None and index is not None:
            keys.append(f"reference_{reference.name}_{index:02d}")
        if reference is not None:
            keys.append(f"{reference.name}:audio")
        return keys

    def _virtualize_legacy_keys(self, assets: dict) -> bool:
        """把旧 key 的条目在内存里映射到新 key（不改动旧条目本身）。

        复用判定与提交都统一走新 key；upload 阶段如有写入会顺带把虚拟化
        结果落盘，状态面板每次计划前也会虚拟化，保证显示与决策一致。"""
        changed = False
        for anchor in self.adapter.anchors:
            new_key = self._anchor_asset_key(anchor)
            if assets.get(new_key):
                continue
            for legacy in self._legacy_asset_keys(anchor=anchor):
                if assets.get(legacy):
                    for suffix in ("", "__source", "__transform"):
                        if f"{legacy}{suffix}" in assets:
                            assets[f"{new_key}{suffix}"] = assets[f"{legacy}{suffix}"]
                    changed = True
                    break
        for reference in self.adapter.references:
            # 探测失败（如源缺失，Status 容错路径）不阻断虚拟化：视频引用退化为 1 段（与
            # 后续 plan 的行为一致，plan 自身会暴露问题），纯音频引用无分段
            try:
                seg_count = len(self._segments(reference))
            except Exception:
                seg_count = 1 if reference.pass_reference_video else 0
            for index in range(seg_count):
                new_key = self._reference_asset_key(reference, index)
                if assets.get(new_key):
                    continue
                legacy = f"reference_{reference.name}_{index:02d}"
                if assets.get(legacy):
                    for suffix in ("", "__source", "__transform"):
                        if f"{legacy}{suffix}" in assets:
                            assets[f"{new_key}{suffix}"] = assets[f"{legacy}{suffix}"]
                    changed = True
            new_audio = self._audio_asset_key(reference)
            if not assets.get(new_audio):
                legacy_audio = f"{reference.name}:audio"
                if assets.get(legacy_audio):
                    for suffix in ("", "__source", "__transform"):
                        if f"{legacy_audio}{suffix}" in assets:
                            assets[f"{new_audio}{suffix}"] = assets[f"{legacy_audio}{suffix}"]
                    changed = True
        return changed

    # ─────────────────────────────────────────────────────────────
    # Phase 2：Planner 决策（plan → prepare required → upload required）
    # ─────────────────────────────────────────────────────────────
    def _resolve_transform(self, kind: str, reference: ReferenceSpec | None = None, index: int | None = None) -> dict | None:
        """计算某素材的期望 transform（与 Phase 1 产物签名一致）。"""
        if kind == "anchor":
            return {"kind": "anchor"}
        if reference is None:
            return None
        if kind == "segment":
            segments = self._segments(reference)
            seg = segments[index] if segments and index is not None else None
            if seg is None:
                return None
            start, duration, _, original_total, pad_mode = seg
            return {
                "kind": "segment", "start": start, "duration": duration,
                "crop_filter": reference.crop_filter, "pad_mode": pad_mode,
                "original_duration": original_total,
            }
        if kind == "audio":
            segments = self._segments(reference)
            pad_mode = segments[0][4] if segments else "back"
            seedance_duration = segments[0][2] if segments else None
            # 音频源 = 独立音频（audio_file）或 reference.file（纯音频任务时 file 本身是音频）。
            # seedance_duration 基于音频源自身时长，避免与视频提取时长不一致导致误判重传。
            audio_total = None
            audio_src_name = reference.audio_file or reference.file
            if audio_src_name:
                audio_source = self.adapter.task_dir / audio_src_name
                if audio_source.exists() and re.search(r"\.(mp3|wav|m4a|aac|flac|ogg)$", audio_src_name, re.I):
                    audio_total = probe_duration(audio_source)
                    max_dur = self._max_duration_for_model()
                    seedance_duration = max(4, min(math.ceil(audio_total), max_dur))
            # kind 判断：独立音频比 seedance_duration 短则会被 pad（audio_padded），
            # 未 prepare（audio_file_url 未设）时按源时长推断，与 prepare 后产物一致
            need_pad = (audio_total is not None and seedance_duration is not None and audio_total < seedance_duration) \
                or (reference.audio_file_url and "padded" in reference.audio_file_url)
            return {"kind": "audio_padded" if need_pad else "audio",
                    "pad_mode": pad_mode, "seedance_duration": seedance_duration}
        return None

    def _anchor_alias_key(self, anchor: AnchorSpec, assets: dict, current_src: dict | None) -> str | None:
        """在 assets 里找「内容指纹与当前源文件一致」的其他 anchor 条目。

        两个复用场景都靠它：跨文件夹复制时迁移过来的条目（key 是源任务的位置键，
        未必等于本任务的位置键）、同文件夹内调整 anchor 顺序（同一张图换了
        anchor-N 位置键）。segment/audio 条目的 __source 是 runtime/work 产物指纹，
        不会与源文件一致；再以 transform 限定 anchor 类双保险，不会错配。"""
        if current_src is None:
            return None
        own_key = self._anchor_asset_key(anchor)
        for k in assets:
            if k == own_key or k.endswith("__source") or k.endswith("__transform"):
                continue
            fp = assets.get(f"{k}__source")
            if not isinstance(fp, dict) or not _fingerprint_content_same(fp, current_src):
                continue
            # 第三道闸：segment/audio 的 __source.path 指向 runtime/work 产物，一律排除。
            # 即使指纹碰巧相等也不认领——错复用的代价（生成用错素材）远大于多传一次
            if "/runtime/work/" in str(fp.get("path", "")).replace("\\", "/"):
                continue
            transform = assets.get(f"{k}__transform")
            if transform not in (None, {"kind": "anchor"}):
                continue
            if assets.get(k):
                return k
        return None

    def _adopt_anchor_aliases(self, assets: dict, persist: bool = False) -> bool:
        """把「内容指纹命中别名条目」的 anchor 在名义 key 下落账。

        inspect 阶段决策可走别名资产，但提交/显示统一读名义 key（submit 里
        assets[self._anchor_asset_key(anchor)]），所以在 upload/状态展示前把
        别名的 asset_id 与边车键复制到名义 key 下；persist=True 时写回 assets.json。"""
        changed = False
        for anchor in self.adapter.anchors:
            key = self._anchor_asset_key(anchor)
            path = self.adapter.task_dir / anchor.file
            if not path.is_file() or assets.get(key):
                continue
            alias = self._anchor_alias_key(anchor, assets, _fingerprint(path))
            if alias is None:
                continue
            assets[key] = assets[alias]
            assets[f"{key}__source"] = _fingerprint(path)
            assets[f"{key}__transform"] = assets.get(f"{alias}__transform", {"kind": "anchor"})
            changed = True
        if changed and persist:
            self._save_assets(assets)
        return changed

    def _inspect_anchor(self, anchor: AnchorSpec, assets: dict) -> InspectedMaterial:
        key = self._anchor_asset_key(anchor)
        path = self.adapter.task_dir / anchor.file
        source_exists = path.exists()
        desired = self._resolve_transform("anchor")
        current_src = _fingerprint(path) if source_exists else None
        # 名义 key 的缓存记录
        cached_src = assets.get(f"{key}__source")
        asset_exists = bool(assets.get(key))
        asset_transform = assets.get(f"{key}__transform") if asset_exists else None
        # 名义 key 指纹不匹配（或无记录）时按内容指纹找别名条目复用
        # （跨文件夹复制迁移 / 同文件夹换位），提交阶段由 _adopt_anchor_aliases 落账
        if source_exists and not _fingerprint_content_same(cached_src, current_src):
            alias = self._anchor_alias_key(anchor, assets, current_src)
            if alias is not None:
                cached_src = assets.get(f"{alias}__source")
                asset_exists = bool(assets.get(alias))
                asset_transform = assets.get(f"{alias}__transform")
        # anchor 的上传产物就是源文件本身：指纹不匹配 = 云端是旧图。
        # anchor 的 transform 恒为 {"kind":"anchor"}，若只看 transform 相等会把
        # 已编辑的源图误判为可复用，这里置空 asset_transform 强制走重传判定
        if asset_exists and not _fingerprint_content_same(cached_src, current_src):
            asset_transform = None
        artifact_valid = source_exists and _fingerprint_content_same(cached_src, current_src)
        artifact_transform = desired if source_exists else None
        # 兼容旧资产：asset 有 __source 但无 __transform 时，若源指纹一致则视为匹配（不误判重传）
        if asset_exists and asset_transform is None and artifact_valid:
            asset_transform = desired
        return InspectedMaterial(
            material_id=key, asset_key=key,
            source_exists=source_exists,
            artifact_valid=artifact_valid, artifact_transform=artifact_transform,
            asset_exists=asset_exists, asset_transform=asset_transform,
            visibility=VISIBILITY_IDENTIFIABLE if source_exists else VISIBILITY_OPAQUE,
            desired_transform=desired,
        )

    def _inspect_reference(self, reference: ReferenceSpec, assets: dict, index: int) -> InspectedMaterial:
        key = self._reference_asset_key(reference, index)
        seg_source = self.adapter.task_dir / reference.file
        source_exists = seg_source.exists()
        segment = self._reference_segment(reference, index)
        desired = self._resolve_transform("segment", reference, index)
        desired_sig = _artifact_signature(_fingerprint(seg_source) if source_exists else None, desired) if desired else None
        # marker 从新（任务级）/旧（文件夹级共享）两处读，任一签名匹配即产物有效
        cached_sig = self._read_signature_any(reference, f"segment_{index:02d}.src.json")
        artifact_valid = source_exists and segment.exists() and cached_sig is not None and cached_sig == desired_sig
        marker_data = self._read_json_any(reference, f"segment_{index:02d}.src.json")
        artifact_transform = marker_data.get("transform") if isinstance(marker_data, dict) else None
        cached_src = assets.get(f"{key}__source")
        asset_transform = assets.get(f"{key}__transform")
        # 判断「云端资产是否对应当前本地产物」——决定能否复用：
        # - 资产有 __transform：transform 匹配 desired 才算有效
        # - 旧资产无 __transform：上传时的产物指纹（__source）与当前切片一致才算有效
        asset_matches_current = False
        if asset_transform is not None:
            asset_matches_current = (asset_transform == desired)
        else:
            asset_matches_current = _fingerprint_content_same(cached_src, _fingerprint(segment) if segment.exists() else None)
        # 资产「是否存在」（用于 asset_state / asset_id 显示）：资产存在且对应当前产物 → 视为"已上传"，
        # 不依赖 artifact_valid（status 面板未 prepare 时无法确认产物，但资产已上传的事实成立）。
        asset_exists = bool(assets.get(key)) and asset_matches_current
        # 能否「复用」（REUSE_REMOTE）：还需产物对应当前源（artifact_valid），避免误用残留旧产物；
        # 否则即使资产 __source 匹配旧产物，也仅显示"已上传"但 action 走重传（UPLOAD_EXISTING_ARTIFACT / BUILD_AND_UPLOAD）
        asset_transform = desired if (asset_exists and artifact_valid) else None
        return InspectedMaterial(
            material_id=key, asset_key=key,
            source_exists=source_exists,
            artifact_valid=artifact_valid, artifact_transform=artifact_transform,
            asset_exists=asset_exists, asset_transform=asset_transform,
            visibility=VISIBILITY_IDENTIFIABLE if source_exists else VISIBILITY_OPAQUE,
            desired_transform=desired,
        )

    def _inspect_audio(self, reference: ReferenceSpec, assets: dict) -> InspectedMaterial:
        key = self._audio_asset_key(reference)
        source = self.adapter.task_dir / (reference.audio_file or reference.file)
        source_exists = source.exists()
        desired = self._resolve_transform("audio", reference)
        # 音频产物是 audio_file_url（prepare 后确定）；若未 prepare，按 audio.mp3 判断
        audio_path = None
        if reference.audio_file_url:
            audio_path = Path(reference.audio_file_url)
        else:
            audio_path = self._reference_audio(reference)
        cached_sig = self._read_signature_any(reference, "audio_padded.src.json") if audio_path else None
        # 音频产物是否有效：源音频未变 + 产物存在（或用 padded marker 签名匹配）
        current_src = _fingerprint(source) if source_exists else None
        # 源标记按「实际要上传的产物」选择：补齐时长时上传 audio_padded.mp3，否则上传 audio.mp3。
        # 这样能避免 audio.src.json 被上一次用不同源（如临时切到某视频提取音频）污染后误判当前源失效。
        want_padded = bool(desired and desired.get("kind") == "audio_padded")
        src_marker_name = "audio_padded.src.json" if want_padded else "audio.src.json"
        cached_audio_src_data = self._read_json_any(reference, src_marker_name) if audio_path else None
        cached_audio_src = None
        if isinstance(cached_audio_src_data, dict):
            cached_audio_src = cached_audio_src_data.get("source") if "source" in cached_audio_src_data else cached_audio_src_data
        # 产物存在性：按 want_padded 检查实际要上传的文件（audio_padded.mp3 或 audio.mp3）
        artifact_file = self._artifact_existing(reference, "audio_padded.mp3") if want_padded else audio_path
        artifact_valid = (source_exists and artifact_file is not None and artifact_file.exists()
                          and cached_audio_src is not None and cached_audio_src == current_src)
        artifact_transform = None
        padded_marker_data = self._read_json_any(reference, "audio_padded.src.json")
        if isinstance(padded_marker_data, dict):
            artifact_transform = padded_marker_data.get("transform")
        if artifact_transform is None:
            audio_marker_data = self._read_json_any(reference, "audio.src.json")
            if isinstance(audio_marker_data, dict):
                artifact_transform = audio_marker_data.get("transform") or {"kind": "audio"}
        asset_exists = bool(assets.get(key))
        asset_transform = assets.get(f"{key}__transform")
        # 判断「云端资产是否对应当前本地产物」——决定能否复用（与 _inspect_reference 一致）：
        # - 资产有 __transform：transform 匹配 desired 才算有效
        # - 旧资产无 __transform：上传时的产物指纹（__source）与当前音频产物一致才算有效。
        #   用 __source.path 定位产物文件比对（该 path 即上传时的产物，可能是 audio_padded.mp3 或 audio.mp3），
        #   避免用未 prepare 时推断的 audio.mp3 误比对 padded 资产。
        asset_matches_current = False
        if asset_transform is not None:
            asset_matches_current = (asset_transform == desired)
        else:
            cached_asset_src = assets.get(f"{key}__source")
            artifact_path = None
            if isinstance(cached_asset_src, dict) and cached_asset_src.get("path"):
                p = Path(cached_asset_src["path"])
                artifact_path = p if p.is_file() else (audio_path if audio_path is not None and audio_path.exists() else None)
            elif audio_path is not None and audio_path.exists():
                artifact_path = audio_path
            asset_matches_current = _fingerprint_content_same(cached_asset_src, _fingerprint(artifact_path) if artifact_path else None)
        # 资产「是否存在」（用于 asset_state / asset_id 显示）：资产存在且对应当前产物 → 视为"已上传"，
        # 不依赖 artifact_valid（status 面板未 prepare 时无法确认产物，但资产已上传的事实成立）。
        effective_asset_exists = asset_exists and asset_matches_current
        # 能否「复用」（REUSE）：还需产物对应当前源（artifact_valid），避免误用残留旧产物
        effective_asset_transform = desired if (effective_asset_exists and artifact_valid) else None
        return InspectedMaterial(
            material_id=key, asset_key=key,
            source_exists=source_exists,
            artifact_valid=artifact_valid, artifact_transform=artifact_transform,
            asset_exists=effective_asset_exists, asset_transform=effective_asset_transform,
            visibility=VISIBILITY_IDENTIFIABLE if source_exists else VISIBILITY_OPAQUE,
            desired_transform=desired,
        )

    def _plan_all(self, assets: dict) -> list[AssetDecision]:
        # 旧 key（无任务前缀）先虚拟映射到新 key：存量缓存继续可用，写入走新 key。
        # 状态面板与 upload 都经由这里，保证显示与决策一致
        self._virtualize_legacy_keys(assets)
        decisions = []
        for anchor in self.adapter.anchors:
            decisions.append(plan_material(self._inspect_anchor(anchor, assets)))
        for reference in self.adapter.references:
            if reference.pass_reference_video:
                for index, _ in enumerate(self._segments(reference)):
                    decisions.append(plan_material(self._inspect_reference(reference, assets, index)))
        for reference in self.adapter.references:
            # 不传参考音频（如 motion 模式 / 手动关闭）时音频不会进入提交内容，
            # 无需规划/上传，避免 Status 面板出现无用行和浪费上传
            if not reference.pass_reference_audio:
                continue
            decisions.append(plan_material(self._inspect_audio(reference, assets)))
        return decisions

    def upload(self, provider: str = "auto") -> dict:
        assets = self._load_assets()
        # 旧 key → 新 key 的虚拟映射先落盘（纯复用运行也固化，后续面板/运行直达新 key）
        if self._virtualize_legacy_keys(assets):
            self._save_assets(assets)
        decisions = self._plan_all(assets)
        # 阻断：任何素材不可提交则整体失败
        blocked = [d for d in decisions if not d.can_submit]
        if blocked:
            reasons = "; ".join(f"{d.asset_key}: {d.block_reason}" for d in blocked)
            raise RuntimeError(f"素材无法提交：{reasons}")
        # anchor 走别名资产复用（跨文件夹迁移 / 同文件夹换位）时，先把别名落到名义
        # key 下再继续——submit 阶段统一按名义 key 取 asset_id，不落账会 KeyError
        self._adopt_anchor_aliases(assets, persist=True)
        # 需要重建产物的素材存在 → 执行 prepare（Phase 2 暂保持全局 prepare）
        if any(d.action == BUILD_AND_UPLOAD for d in decisions):
            self.prepare()
            assets = self._load_assets()
            decisions = self._plan_all(assets)
            blocked = [d for d in decisions if not d.can_submit]
            if blocked:
                reasons = "; ".join(f"{d.asset_key}: {d.block_reason}" for d in blocked)
                raise RuntimeError(f"素材无法提交：{reasons}")
        # 需要上传的素材（UPLOAD_EXISTING_ARTIFACT / BUILD_AND_UPLOAD）
        missing = []
        for d in decisions:
            if d.action in (UPLOAD_EXISTING_ARTIFACT, BUILD_AND_UPLOAD):
                if d.asset_key.startswith("anchor_"):
                    missing.append(("anchor", d.asset_key))
                elif d.asset_key.endswith(":audio"):
                    missing.append(("audio", d.asset_key))
                else:
                    # reference_<name>_<idx>
                    missing.append(("reference", d.asset_key))
        if not missing:
            return assets
        self._progress("tunnel", "正在启动或复用素材隧道")
        state = tunnel.start(provider)
        total = len(missing)
        for position, (kind, key) in enumerate(missing, 1):
            if kind == "anchor":
                anchor = next((a for a in self.adapter.anchors if self._anchor_asset_key(a) == key), None)
                if anchor is None:
                    continue
                path = self.adapter.task_dir / anchor.file
                name = f"video_{_safe(self.adapter.name)}_{_safe(anchor.key)}"
                asset_type = "Image"
            elif kind == "audio":
                reference = next((r for r in self.adapter.references if self._audio_asset_key(r) == key), None)
                if reference is None:
                    continue
                path = Path(reference.audio_file_url) if reference.audio_file_url else self._reference_audio(reference)
                name = f"video_{_safe(self.adapter.name)}_{_safe(reference.name)}_audio"
                asset_type = "Audio"
            else:
                # reference_<name>_<idx>：用 _reference_asset_key 精确匹配（name 本身可含下划线）
                reference = None
                index = None
                for r in self.adapter.references:
                    for i, _ in enumerate(self._segments(r)):
                        if self._reference_asset_key(r, i) == key:
                            reference, index = r, i
                            break
                    if reference is not None:
                        break
                if reference is None:
                    continue
                path = self._reference_segment(reference, index)
                name = f"video_{_safe(self.adapter.name)}_{_safe(reference.name)}_{index:02d}"
                asset_type = "Video"
            # 记录该素材的期望 transform，供后续 plan 判断 asset 是否仍匹配
            if kind == "anchor":
                transform = {"kind": "anchor"}
            elif kind == "audio":
                transform = self._resolve_transform("audio", reference)
            else:
                transform = self._resolve_transform("segment", reference, index)
            self._progress("uploading", f"正在上传素材 {position}/{total}", completed=position - 1, total=total)
            last_error = None
            for attempt in range(3):
                try:
                    url = tunnel.public_url(state["base_url"], path)
                    assets[key] = self.client.create_asset(name, url, asset_type)
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        self._progress("uploading", f"素材上传失败（尝试 {attempt + 1}/3），重建隧道重试...")
                        state = tunnel.start(provider)
                        import time as _time
                        _time.sleep(3)
            else:
                raise last_error
            assets[f"{key}__source"] = _fingerprint(path)
            assets[f"{key}__transform"] = transform
            self._save_assets(assets)
            # 上传成功即入台账（append-only，永不删除）：记录被覆盖后仍可据此找回 asset_id
            self._append_asset_ledger(key, path, assets)
        self._progress("uploading", "素材上传完成", completed=total, total=total)
        return assets

    def _state(self, run_id: str) -> RunState:
        return RunState(self.adapter.output_dir / run_id / "run.json", {
            "task": self.adapter.name,
            "kind": self.adapter.kind,
            "run_id": run_id,
            "status": "created",
            "jobs": [],
        })

    def _prompt_for(self, anchor: AnchorSpec, requested: str | None) -> PromptVariant:
        name = anchor.prompt_variant or requested
        if name and name != "all":
            return next(prompt for prompt in self.adapter.prompts if prompt.name == name)
        return self.adapter.prompts[0]

    def _log_job_decisions(self, anchor: AnchorSpec, ref: ReferenceSpec, prompt: PromptVariant, content: list[dict], duration: int) -> None:
        """记录每个 (anchor, reference, prompt) 组合的关键决策，便于排查。

        覆盖：参考视频/音频是否传入、pad_mode、素材角色类型、prompt variant。
        """
        roles = [item.get("role") for item in content]
        pad_mode = getattr(ref, "pad_mode", "back")
        segments = self._segments(ref)
        original_total = segments[0][3] if segments else 0.0
        timestamp_offset = 0.0
        if pad_mode == "front":
            timestamp_offset = max(0.0, math.ceil(original_total) - original_total)
        logger.info(
            "job-decisions task=%s anchor=%s ref=%s variant=%s pad_mode=%s "
            "pass_video=%s pass_audio=%s audio_passed_to_seedance=%s roles=%s "
            "duration=%ss original_total=%.2fs timestamp_offset=%.2fs",
            self.adapter.name,
            anchor.key,
            ref.name,
            prompt.name,
            pad_mode,
            ref.pass_reference_video,
            ref.pass_reference_audio,
            bool(ref.audio_file_url),
            roles,
            duration,
            original_total,
            timestamp_offset,
        )

    def submit(self, run_id: str, candidates: int | None = None, variant: str | None = None, provider: str = "auto") -> RunState:
        errors = self.validate()
        if errors:
            raise ValueError("Invalid video task:\n- " + "\n- ".join(errors))
        assets = self.upload(provider)
        state = self._state(run_id)
        # 运行快照：记录本次提交实际使用的 asset_id（含 transform），写入 run.json。
        # 之后 assets.json 记录被覆盖/清理，每次生成用的是什么资产仍有据可查
        state.update(assets_used={
            key: {"asset_id": value, "transform": assets.get(f"{key}__transform")}
            for key, value in assets.items()
            if not key.endswith("__source") and not key.endswith("__transform")
        })
        count = candidates or self.adapter.candidate_policy.count
        existing = {job["id"] for job in state.jobs()}
        total = len(self.adapter.anchors) * len(self.adapter.references) * count
        self._progress("submitting", f"准备提交 {total} 个候选", completed=len(existing), total=total)

        job_specs = []
        for anchor in self.adapter.anchors:
            prompt = self._prompt_for(anchor, variant)
            for ref in self.adapter.references:
                duration = self._segments(ref)[0][2]
                content = [
                    {"type": "text", "text": prompt.first_prompt},
                    {"type": "image_url", "image_url": {"url": f"asset://{assets[self._anchor_asset_key(anchor)]}"}, "role": "reference_image"},
                ]
                # 传参考视频（非纯口型模式）
                if ref.pass_reference_video:
                    content.append({"type": "video_url", "video_url": {"url": f"asset://{assets[self._reference_asset_key(ref, 0)]}"}, "role": "reference_video"})
                audio_asset_key = self._audio_asset_key(ref)
                if ref.audio_file_url and audio_asset_key in assets:
                    content.append({"type": "audio_url", "audio_url": {"url": f"asset://{assets[audio_asset_key]}"}, "role": "reference_audio"})
                self._log_job_decisions(anchor, ref, prompt, content, duration)
                for candidate in range(1, count + 1):
                    job_id = f"{_safe(anchor.key)}__{_safe(ref.name)}__{_safe(prompt.name)}__{candidate:02d}"
                    if job_id in existing:
                        continue
                    payload = {
                        "model": self.adapter.model,
                        "ratio": self.adapter.ratio,
                        "resolution": self.adapter.resolution,
                        "duration": duration,
                        "generate_audio": self.adapter.generate_audio,
                        "watermark": self.adapter.watermark,
                        "output_format": self.adapter.output_format,
                        "content": content,
                    }
                    job_specs.append((job_id, anchor, ref, prompt, candidate, payload))

        def _submit_one(spec):
            job_id, anchor, ref, prompt, candidate, payload = spec
            task_id = self.client.submit(payload)
            return {"id": job_id, "anchor": anchor.key, "anchor_label": anchor.label, "reference": ref.name, "variant": prompt.name, "candidate": candidate, "prompt": prompt.first_prompt, "task_id": task_id, "status": "submitted"}

        with ThreadPoolExecutor(max_workers=4) as executor:
            for job in executor.map(_submit_one, job_specs):
                state.jobs().append(job)
                existing.add(job["id"])
                state.save()
                self._progress("submitting", f"已提交 {len(existing)}/{total} 个候选", completed=len(existing), total=total)

        state.update(status="submitted")
        return state

    def _finish_job(self, state: RunState, job: dict) -> None:
        if job.get("status") == "done" and Path(job.get("final", "")).is_file():
            return
        job_dir = state.path.parent / job["anchor"] / f"candidate-{job['candidate']:02d}"
        result = job_dir / "result.mp4"
        self._progress("generating", f"正在等待候选 {job['id']}")
        self.client.poll_and_download(job["task_id"], result)
        self._progress("downloading", f"候选 {job['id']} 已下载")
        try:
            reference = next(item for item in self.adapter.references if item.name == job["reference"])
        except StopIteration:
            raise ValueError(f"reference '{job['reference']}' not found in task references") from None
        final = job_dir / "final.mp4"
        # 根据 pad_mode 裁掉 padding，再回灌原始音频
        segments = self._segments(reference)
        pad_mode = "back"
        original_total = 0.0
        seedance_duration = 0
        if segments and len(segments) == 1:
            _, _, seedance_duration, original_total, pad_mode = segments[0]
        video_source = result
        import subprocess
        if pad_mode == "front":
            # 前面补的：裁掉前面 (seedance_duration - original_total)
            trim_front = seedance_duration - original_total
            if trim_front > 0.1:
                self._progress("trimming", f"正在为候选 {job['id']} 裁掉前面 {trim_front:.1f}s 补齐")
                trimmed = job_dir / "trimmed.mp4"
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(trim_front), "-i", str(result),
                     "-c", "copy", "-avoid_negative_ts", "make_zero", str(trimmed)],
                    check=True, capture_output=True,
                )
                video_source = trimmed
        elif pad_mode == "back":
            # 后面补的：mux 时用 -shortest 自动裁掉
            pass
        # none: 不需要裁
        self._progress("muxing", f"正在为候选 {job['id']} 回灌音频")
        mux_audio(video_source, self._reference_audio(reference), final)
        if video_source != result:
            video_source.unlink(missing_ok=True)
        with self._state_lock:
            job.update(status="done", result=str(result), final=str(final))
            state.save()

    def poll(self, run_id: str) -> RunState:
        state = self._state(run_id)
        pending = [job for job in state.jobs() if job.get("status") != "done"]
        with ThreadPoolExecutor(max_workers=self.adapter.candidate_policy.poll_workers) as executor:
            futures = {executor.submit(self._finish_job, state, job): job for job in pending}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    with self._state_lock:
                        futures[future].update(status="failed", error=str(exc))
                        state.save()
                done = sum(job.get("status") == "done" for job in state.jobs())
                self._progress("generating", f"候选完成 {done}/{len(state.jobs())}", completed=done, total=len(state.jobs()))
                # 每完成一个候选即增量写入 manifest，使审核页面可实时预览
                manifest_path = write_manifest(self.adapter, run_id, state.jobs())
                self._progress("generating", f"候选完成 {done}/{len(state.jobs())}", completed=done, total=len(state.jobs()), manifest=str(manifest_path))
        status = "done" if all(job.get("status") == "done" for job in state.jobs()) else "failed"
        state.update(status=status)
        self._progress("completed" if status == "done" else "failed", "运行完成" if status == "done" else "部分候选失败")
        return state

    def run(self, run_id: str | None = None, candidates: int | None = None, variant: str | None = None, provider: str = "auto", submit_only: bool = False) -> RunState:
        run_id = run_id or datetime.now().strftime("run_%Y%m%d_%H%M%S")
        state = self.submit(run_id, candidates, variant, provider)
        return state if submit_only else self.poll(run_id)

    def resume(self, run_id: str) -> RunState:
        return self.poll(run_id)

    def status(self, run_id: str) -> dict:
        return self._state(run_id).data
