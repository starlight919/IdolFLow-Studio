from __future__ import annotations

import json
import shutil
from pathlib import Path

from idolmv_pipeline.image_tasks.models import AnchorTask
from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig


def _safe_dir_name(value: str) -> str:
    """Normalize a data directory name for filesystem use.

    Keeps unicode letters/digits, replaces others with '-'. The same logic as
    ``normalize_task_id`` in video_tasks.store — keeping a local copy to avoid
    a circular import.
    """
    import re
    return re.sub(r"[^\w\-]+", "-", str(value or "").strip(), flags=re.UNICODE).strip("-") or "task"


class AnchorTaskStore:
    """Anchor task storage rooted at ``data/<data_dir>/anchors/``.

    Each data directory can have at most one anchor task. The ``task_id`` used
    throughout the API is simply the data directory name (e.g. ``马路风``).
    """

    def __init__(self, config: VideoWorkspaceConfig):
        self.config = config
        self.root = config.data_root

    # ── listing ───────────────────────────────────────────────────────────

    def list(self) -> list[dict]:
        result = []
        if not self.root.is_dir():
            return result
        for path in sorted(self.root.glob("*/anchors/anchor-task.json")):
            try:
                task = json.loads(path.read_text())
                data_dir = path.parent.parent.name
                task["data_dir"] = data_dir
                task["id"] = data_dir  # anchor task id = data dir
                result.append(task)
            except (OSError, json.JSONDecodeError):
                continue
        return result

    def list_orphaned(self) -> list[dict]:
        """Find data dirs with ``anchors/anchor-references/`` images but no ``anchor-task.json``."""
        result = []
        if not self.root.is_dir():
            return result
        for d in sorted(self.root.iterdir()):
            if not d.is_dir():
                continue
            # Skip the legacy standalone anchor-xxx dirs that have no other content
            anchor_dir = d / "anchors"
            task_file = anchor_dir / "anchor-task.json"
            if task_file.is_file():
                continue
            ref_dir = anchor_dir / "anchor-references"
            if not ref_dir.is_dir():
                continue
            images = sorted(
                p.name for p in ref_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
            )
            if not images:
                continue
            result.append({
                "task_id": d.name,
                "task_name": d.name,
                "reference_count": len(images),
                "reference_files": images,
            })
        return result

    # ── CRUD ──────────────────────────────────────────────────────────────

    def get(self, data_dir: str) -> dict:
        path = self._path(data_dir)
        if not path.is_file():
            raise KeyError(data_dir)
        task = json.loads(path.read_text())
        task["data_dir"] = data_dir
        task["id"] = data_dir
        return task

    def load(self, data_dir: str) -> AnchorTask:
        return AnchorTask.from_dict(self.get(data_dir))

    def save(self, data: dict) -> dict:
        # Determine data_dir — the directory under data_root that holds this task
        explicit_dir = data.get("data_dir")
        if explicit_dir:
            data_dir = _safe_dir_name(str(explicit_dir))
        else:
            # Fall back to id or name (legacy callers)
            raw_id = str(data.get("id") or data.get("name", ""))
            data_dir = _safe_dir_name(raw_id)
        if not data_dir:
            raise ValueError("could not determine anchor task data_dir")

        # Inject normalized id so AnchorTask.from_dict is happy
        data = dict(data)
        data["id"] = data_dir
        data["data_dir"] = data_dir
        if not data.get("name"):
            data["name"] = data_dir

        task = AnchorTask.from_dict(data)
        anchors_dir = self.task_dir(data_dir)
        anchors_dir.mkdir(parents=True, exist_ok=True)
        normalized = task.to_dict()
        normalized["data_dir"] = data_dir

        # Copy reference images into anchor-references/ if they live elsewhere
        normalized_references = []
        for reference in task.references:
            path = self._reference_source(data_dir, reference.file)
            if not path.is_file():
                raise ValueError(f"missing anchor reference: {reference.file}")
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError(f"unsupported anchor reference: {reference.file}")
            if anchors_dir not in path.parents:
                reference_dir = anchors_dir / "anchor-references"
                reference_dir.mkdir(parents=True, exist_ok=True)
                destination = reference_dir / path.name
                if destination.exists() and destination.resolve() != path:
                    destination = reference_dir / f"{reference.id}{path.suffix.lower()}"
                if not destination.exists():
                    temporary_copy = destination.with_suffix(".tmp")
                    shutil.copy2(path, temporary_copy)
                    temporary_copy.replace(destination)
                file = destination.relative_to(anchors_dir).as_posix()
            else:
                file = path.relative_to(anchors_dir).as_posix()
            normalized_references.append({
                "id": reference.id,
                "file": file,
                "bindings": [
                    {
                        "aspect": binding.aspect,
                        "content": binding.content,
                        "constraint": binding.constraint,
                    }
                    for binding in reference.bindings
                ],
                "note": reference.note,
                "remove_watermark": reference.remove_watermark,
            })
        normalized["references"] = normalized_references

        path = self._path(data_dir)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        temporary.replace(path)
        return normalized

    def delete(self, data_dir: str) -> None:
        """Delete the anchor task (anchors/ subdir) but keep the data directory."""
        anchors_dir = self.task_dir(data_dir)
        if anchors_dir.is_dir():
            shutil.rmtree(anchors_dir)

    def recover(self, data_dir: str) -> dict:
        """Reconstruct a minimal anchor-task.json from an orphaned directory."""
        anchors_dir = self.task_dir(data_dir)
        ref_dir = anchors_dir / "anchor-references"
        if not ref_dir.is_dir():
            raise ValueError(f"no reference images found for: {data_dir}")
        images = sorted(
            p for p in ref_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if not images:
            raise ValueError(f"no reference images found for: {data_dir}")

        references = []
        for i, img in enumerate(images):
            references.append({
                "id": f"ref-{i + 1}",
                "file": img.relative_to(anchors_dir).as_posix(),
                "bindings": [{"aspect": "identity_face", "content": "", "constraint": ""}],
                "note": "",
                "remove_watermark": False,
            })

        data = {
            "id": data_dir,
            "name": data_dir,
            "data_dir": data_dir,
            "description": "",
            "negative": "",
            "size": "1024x1792",
            "resolution": "2K",
            "candidates": 4,
            "model": "gpt-image-2",
            "aspects": [
                {"key": "identity_face", "description": "same_person", "priority": "required", "label": ""}
            ],
            "references": references,
        }
        return self.save(data)

    # ── path helpers ──────────────────────────────────────────────────────

    def task_dir(self, data_dir: str) -> Path:
        """Return ``data/<data_dir>/anchors/`` — the anchor workspace."""
        normalized = _safe_dir_name(data_dir)
        return self.config.resolve_inside("data_root", f"{normalized}/anchors")

    def data_root_dir(self, data_dir: str) -> Path:
        """Return ``data/<data_dir>/`` — the parent data directory."""
        normalized = _safe_dir_name(data_dir)
        return self.config.resolve_inside("data_root", normalized)

    def asset_path(self, data_dir: str, relative: str) -> Path:
        root = self.task_dir(data_dir)
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError("anchor reference escapes task directory")
        return path

    def _reference_source(self, data_dir: str, relative: str) -> Path:
        task_path = self.asset_path(data_dir, relative)
        if task_path.is_file():
            return task_path
        # Try data dir root (e.g. user put images directly in data/<dir>/)
        shared = self.data_root_dir(data_dir) / relative
        if shared.is_file():
            return shared
        # Global fallback
        global_path = self.config.resolve_inside("data_root", relative)
        if global_path.is_file():
            return global_path
        return task_path

    def generated_dir(self, data_dir: str, run_id: str) -> Path:
        return self.asset_path(data_dir, f"generated/{run_id}")

    def selected_dir(self, data_dir: str) -> Path:
        return self.asset_path(data_dir, "selected")

    def _path(self, data_dir: str) -> Path:
        normalized = _safe_dir_name(data_dir)
        return self.config.resolve_inside("data_root", f"{normalized}/anchors/anchor-task.json")
