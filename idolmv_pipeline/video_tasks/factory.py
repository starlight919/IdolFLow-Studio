from __future__ import annotations

from pathlib import Path

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
    prompt = build_prompt(mode, lyrics, str(task.get("constraints", "")), has_audio_ref=has_audio, has_video_ref=has_video, camera_policy=camera_policy)
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
