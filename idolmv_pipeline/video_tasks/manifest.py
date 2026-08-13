from __future__ import annotations

import json
from pathlib import Path

from idolmv_pipeline.video_tasks.models import VideoTaskAdapter


def build_manifest(adapter: VideoTaskAdapter, run_id: str, jobs: list[dict]) -> dict:
    candidates = []
    for job in jobs:
        final = job.get("final")
        if not final or not Path(final).is_file():
            continue
        final_path = Path(final).resolve()
        candidates.append({
            "id": job["id"],
            "task": adapter.name,
            "kind": adapter.kind,
            "run_id": run_id,
            "anchor": job["anchor"],
            "anchor_label": job["anchor_label"],
            "reference": job["reference"],
            "variant": job["variant"],
            "candidate": job["candidate"],
            "status": job["status"],
            "path": str(final_path.relative_to(adapter.task_dir.resolve())) if adapter.task_dir.resolve() in final_path.parents else str(final_path),
            "file": str(final_path),
        })
    return {
        "task": adapter.name,
        "kind": adapter.kind,
        "run_id": run_id,
        "publish": {
            "repo": str(adapter.publish.repo),
            "subdirectory": adapter.publish.subdirectory,
            "filename_prefix": adapter.publish.filename_prefix,
        },
        "candidates": candidates,
    }


def write_manifest(adapter: VideoTaskAdapter, run_id: str, jobs: list[dict]) -> Path:
    path = adapter.output_dir / run_id / "review_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(build_manifest(adapter, run_id, jobs), indent=2, ensure_ascii=False))
    temporary.replace(path)
    return path
