from __future__ import annotations

import json
from pathlib import Path

from idolmv_pipeline.image_tasks.models import AnchorTask


def write_manifest(task: AnchorTask, run_id: str, jobs: list[dict], prompt: str, mapping: list[dict], output_dir: Path) -> Path:
    candidates = [{
        "id": job["id"],
        "candidate": job["candidate"],
        "status": job["status"],
        "file": job["file"],
        "task_id": job.get("task_id", ""),
    } for job in jobs if job.get("status") == "done" and Path(job.get("file", "")).is_file()]
    manifest = {
        "media_type": "image",
        "task": task.id,
        "task_name": task.name,
        "run_id": run_id,
        "model": task.model,
        "size": task.size,
        "resolution": task.resolution,
        "prompt": prompt,
        "references": mapping,
        "candidates": candidates,
    }
    path = output_dir / "review_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    temporary.replace(path)
    return path
