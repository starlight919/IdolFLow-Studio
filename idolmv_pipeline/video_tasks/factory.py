from __future__ import annotations

import logging
import math
from pathlib import Path

from idolmv_pipeline.seedance.media import probe_duration
from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig
from idolmv_pipeline.video_tasks.models import (
    AnchorSpec,
    CandidatePolicy,
    PromptVariant,
    PublishSpec,
    ReferenceSpec,
    VideoTaskAdapter,
)
from idolmv_pipeline.video_tasks.prompts import build_prompt
from idolmv_pipeline.video_tasks.store import TaskStore

logger = logging.getLogger(__name__)


def adapter_from_task(task: dict, config: VideoWorkspaceConfig, store: TaskStore | None = None) -> VideoTaskAdapter:
    store = store or TaskStore(config)
    task = store.validate(task)
    task_dir = store.task_dir(task["id"], task.get("task_dir"))
    lyrics = str(task.get("lyrics", "")).strip()
    if task.get("lyrics_file"):
        lyrics = (task_dir / task["lyrics_file"]).read_text().strip()
    mode = task["mode"]
    refs = task.get("references", [])
    has_audio = any(ref.get("pass_reference_audio", True) for ref in refs)
    has_video = any(ref.get("pass_reference_video", True) for ref in refs) if refs else True
    camera_policy = task.get("camera_policy")
    prompt = build_prompt(
        mode,
        lyrics,
        str(task.get("constraints", "")),
        has_audio_ref=has_audio,
        has_video_ref=has_video,
        camera_policy=camera_policy,
        lyrics_timestamps=task.get("lyrics_timestamps"),
        timestamp_offset=_timestamp_offset(task, task_dir),
    )
    # Use data_dir (not task name) for output/work dirs so multiple tasks
    # sharing the same data dir co-locate their outputs.
    dir_key = task.get("data_dir") or task["id"]
    work_dir = _override(task, "work_dir", config.work_root / dir_key, config)
    output_dir = _override(task, "output_dir", config.output_root / dir_key, config)
    publish_repo = Path(task.get("publish_repo", config.publish_repo)).expanduser().resolve()
    return VideoTaskAdapter(
        name=task["id"],
        kind="dance" if mode == "motion" else "singing",
        mode=mode,
        anchors=tuple(AnchorSpec(item["key"], item["file"], item.get("label", item["key"])) for item in task["anchors"]),
        references=tuple(ReferenceSpec(
            item["name"], item["file"], item.get("audio_file"),
            item.get("audio_file_url"),
            item.get("pass_reference_audio", True),
            item.get("pass_reference_video", True),
            int(item.get("duration", 30)),
            crop_filter=item.get("crop_filter"),
            pad_mode=item.get("pad_mode", "back"),
        ) for item in task["references"]),
        prompts=(PromptVariant(mode, prompt),),
        candidate_policy=CandidatePolicy(int(task.get("candidates", 4)), int(task.get("poll_workers", 4))),
        publish=PublishSpec(
            publish_repo,
            task.get("publish_subdirectory", config.publish_subdirectory),
            task.get("filename_prefix", task["id"]),
        ),
        lyrics_file=task.get("lyrics_file"),
        source_root=task_dir.parent,
        task_path=task_dir,
        work_path=work_dir,
        output_path=output_dir,
        model=task.get("model", "sd2.5"),
        ratio=task.get("ratio", "9:16"),
        resolution=task.get("resolution", "720p"),
        metadata={"lyrics_text": lyrics, "anchor_asset_keys": task.get("anchor_asset_keys", {})},
    )


def _override(task: dict, key: str, default: Path, config: VideoWorkspaceConfig) -> Path:
    path = Path(task.get(key, default)).expanduser().resolve()
    allowed = (config.work_root, config.output_root)
    if not any(path == root or root in path.parents for root in allowed):
        raise ValueError(f"{key} is outside configured work/output roots")
    return path


def _timestamp_offset(task: dict, task_dir: Path) -> float:
    """计算歌词时间戳偏移量（秒）。

    仅当 pad_mode="front"（前面补齐）时需要：音频/视频开头补了静音/静止帧，
    歌词实际起唱时间整体后移，prompt 里的人工时间点需加上该偏移。

    偏移量 = seedance_duration - original_total，其中 seedance_duration
    与 runner._segments 保持一致：max(4, min(ceil(total), max_duration))。
    其余 pad_mode（none / back）偏移为 0。probe 失败时兜底为 0（不阻塞生成）。
    """
    refs = task.get("references", [])
    if not refs:
        return 0.0
    ref = refs[0]
    pad_mode = ref.get("pad_mode", "back")
    if pad_mode != "front":
        logger.info(
            "timestamp-offset task=%s pad_mode=%s -> offset=0.00s (无需偏移)",
            task.get("name"), pad_mode,
        )
        return 0.0
    ref_path = task_dir / ref["file"]
    if not ref_path.is_file():
        logger.warning(
            "timestamp-offset task=%s pad_mode=front 但参考文件缺失: %s，offset 兜底为 0",
            task.get("name"), ref["file"],
        )
        return 0.0
    try:
        total = probe_duration(ref_path)
    except Exception as exc:
        logger.warning(
            "timestamp-offset task=%s 探测时长失败(%s)，offset 兜底为 0",
            task.get("name"), exc,
        )
        return 0.0

    # 与 runner._segments 的 seedance_duration 计算保持一致
    model = task.get("model", "sd2.5")
    max_duration = 30 if "sd2.5" in str(model) else 15
    # 超时长：直接截断（_segments 已归一为 none），无补齐，offset 一定为 0
    if total > max_duration:
        logger.info(
            "timestamp-offset task=%s pad_mode=front 但超时长(%.2fs > %ss)，"
            "走截断无补齐，offset=0.00s",
            task.get("name"), total, max_duration,
        )
        return 0.0
    seedance_duration = max(4, min(math.ceil(total), max_duration))
    offset = max(0.0, seedance_duration - total)
    logger.info(
        "timestamp-offset task=%s pad_mode=front original_total=%.2fs "
        "seedance_duration=%ss max_duration=%ss -> offset=%.2fs",
        task.get("name"), total, seedance_duration, max_duration, offset,
    )
    return offset
