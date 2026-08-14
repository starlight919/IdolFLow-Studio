from __future__ import annotations

import json
import logging
import math
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


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def _fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


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

    def _reference_audio(self, reference: ReferenceSpec) -> Path:
        return self.adapter.work_dir / reference.name / "audio.mp3"

    def _reference_audio_padded(self, reference: ReferenceSpec) -> Path:
        return self.adapter.work_dir / reference.name / "audio_padded.mp3"

    def _reference_segment(self, reference: ReferenceSpec, index: int = 0) -> Path:
        return self.adapter.work_dir / reference.name / f"segment_{index:02d}.mp4"

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
            audio = self._reference_audio(reference)
            source = self.adapter.task_dir / (reference.audio_file or reference.file)
            # 用源文件指纹判断是否需要重新生成音频缓存，避免切换音视频后沿用旧的 work_dir 缓存
            fingerprint_marker = audio.with_name("audio.src.json")
            current_fp = _fingerprint(source) if source.exists() else None
            cached_fp = None
            if fingerprint_marker.exists():
                try:
                    cached_fp = json.loads(fingerprint_marker.read_text())
                except Exception:
                    cached_fp = None
            audio_refreshed = False
            if not audio.exists() or cached_fp != current_fp:
                if reference.pass_reference_video:
                    # 视频模式：从视频提取音频
                    extract_audio(source, audio)
                else:
                    # 纯音频模式：reference.file 本身就是音频，直接拷贝（对等视频提取音频，不再二次转码）
                    shutil.copyfile(source, audio)
                if current_fp is not None:
                    fingerprint_marker.write_text(json.dumps(current_fp))
                audio_refreshed = True
            pad_mode = segments[0][4] if segments else "back"
            if segments and len(segments) == 1:
                seedance_duration = segments[0][2]
                actual = probe_duration(audio)
                if actual < seedance_duration and reference.pass_reference_audio:
                    padded = self._reference_audio_padded(reference)
                    if not padded.exists() or audio_refreshed:
                        pad_audio_to(audio, padded, seedance_duration, pad_mode=pad_mode)
                    object.__setattr__(reference, 'audio_file_url', str(padded.resolve()))
                elif reference.pass_reference_audio and not reference.audio_file_url:
                    object.__setattr__(reference, 'audio_file_url', str(audio.resolve()))
            elif reference.pass_reference_audio and not reference.audio_file_url:
                object.__setattr__(reference, 'audio_file_url', str(audio.resolve()))
            # 纯口型模式（pass_reference_video=False）下 reference.file 是纯音频文件，
            # 不做视频切片/check frame，只准备音频（上面已处理）。
            if not reference.pass_reference_video:
                continue
            for index, (start, duration, _, original_total, seg_pad_mode) in enumerate(segments):
                segment = self._reference_segment(reference, index)
                seg_source = self.adapter.task_dir / reference.file
                seg_fp = _fingerprint(seg_source) if seg_source.exists() else None
                seg_marker = segment.with_name(f"segment_{index:02d}.src.json")
                seg_cached = None
                if seg_marker.exists():
                    try:
                        seg_cached = json.loads(seg_marker.read_text())
                    except Exception:
                        seg_cached = None
                if not segment.exists() or seg_cached != seg_fp:
                    trim_reference(seg_source, segment, start, duration, reference.crop_filter, pad_mode=seg_pad_mode, original_duration=original_total)
                    if seg_fp is not None:
                        seg_marker.write_text(json.dumps(seg_fp))
                check_frame = segment.with_name(f"segment_{index:02d}_check.jpg")
                if not check_frame.exists():
                    extract_check_frame(segment, check_frame)

    def _load_assets(self) -> dict:
        return json.loads(self.adapter.assets_file.read_text()) if self.adapter.assets_file.exists() else {}

    def _save_assets(self, assets: dict) -> None:
        self.adapter.assets_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.adapter.assets_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(assets, indent=2, ensure_ascii=False))
        temporary.replace(self.adapter.assets_file)

    def _anchor_asset_key(self, anchor: AnchorSpec) -> str:
        return self.adapter.metadata.get("anchor_asset_keys", {}).get(anchor.key, f"anchor_{anchor.key}")

    def _reference_asset_key(self, reference: ReferenceSpec, index: int) -> str:
        return self.adapter.metadata.get("reference_asset_keys", {}).get(f"{reference.name}:{index}", f"reference_{reference.name}_{index:02d}")

    def upload(self, provider: str = "auto") -> dict:
        self.prepare()
        assets = self._load_assets()
        missing = []
        for anchor in self.adapter.anchors:
            key = self._anchor_asset_key(anchor)
            path = self.adapter.task_dir / anchor.file
            reused = key in self.adapter.metadata.get("anchor_asset_keys", {}).values()
            if not assets.get(key) or (not reused and assets.get(f"{key}__source") != _fingerprint(path)):
                missing.append(("anchor", anchor))
        for reference in self.adapter.references:
            # 纯口型模式不传视频，跳过 segment 视频上传
            if not reference.pass_reference_video:
                continue
            for index, _ in enumerate(self._segments(reference)):
                key = self._reference_asset_key(reference, index)
                path = self._reference_segment(reference, index)
                if not assets.get(key) or assets.get(f"{key}__source") != _fingerprint(path):
                    missing.append(("reference", (reference, index)))
        for reference in self.adapter.references:
            if reference.audio_file_url:
                path = Path(reference.audio_file_url)
                key = f"{reference.name}:audio"
                if not assets.get(key) or assets.get(f"{key}__source") != _fingerprint(path):
                    missing.append(("audio", (reference, path)))
        if not missing:
            return assets
        self._progress("tunnel", "正在启动或复用素材隧道")
        state = tunnel.start(provider)
        total = len(missing)
        for position, (kind, value) in enumerate(missing, 1):
            if kind == "anchor":
                anchor = value
                path = self.adapter.task_dir / anchor.file
                key = self._anchor_asset_key(anchor)
                name = f"video_{_safe(self.adapter.name)}_{_safe(anchor.key)}"
                asset_type = "Image"
            elif kind == "audio":
                reference, path = value
                key = f"{reference.name}:audio"
                name = f"video_{_safe(self.adapter.name)}_{_safe(reference.name)}_audio"
                asset_type = "Audio"
            else:
                reference, index = value
                path = self._reference_segment(reference, index)
                key = self._reference_asset_key(reference, index)
                name = f"video_{_safe(self.adapter.name)}_{_safe(reference.name)}_{index:02d}"
                asset_type = "Video"
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
            self._save_assets(assets)
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
                audio_asset_key = f"{ref.name}:audio"
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
