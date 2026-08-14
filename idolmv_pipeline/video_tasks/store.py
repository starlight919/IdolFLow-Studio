from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig
from idolmv_pipeline.video_tasks.prompts import build_prompt

_ID = re.compile(r"[^\w\-]+", re.UNICODE)
MODES = {"lip_sync", "dance_lip_sync", "motion"}


def normalize_task_id(value: str | None) -> str:
    return _ID.sub("-", str(value or "").strip()).strip("-") or "task"

def composite_id(data_dir: str, task_id: str) -> str:
    """Combine data_dir name and task id into a unique composite key for API use."""
    return f"{data_dir}__{task_id}"

def parse_composite_id(cid: str) -> tuple[str, str]:
    """Split composite id back into (data_dir, task_id)."""
    parts = cid.split("__", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    # Legacy: single-part id means data_dir == task_id
    return cid, cid


class TaskStore:
    def __init__(self, config: VideoWorkspaceConfig):
        self.config = config
        self.root = config.data_root
        self.lock = threading.RLock()

    # ── listing ───────────────────────────────────────────────────────────

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        result = []
        # New scheme: data/<dir>/tasks/<task_id>.json
        for path in sorted(self.root.glob("*/tasks/*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                task = json.loads(path.read_text())
                data_dir = path.parent.parent.name
                task["data_dir"] = data_dir
                task["mtime"] = path.stat().st_mtime
                # 防御脏数据：id 字段若已含 data_dir 前缀（历史手动写入 composite id），循环剥离后再拼接，避免双重前缀
                raw_id = str(task.get("id") or task.get("name", ""))
                prefix = f"{data_dir}__"
                while raw_id.startswith(prefix) and len(raw_id) > len(prefix):
                    raw_id = raw_id[len(prefix):]
                task["id"] = composite_id(data_dir, raw_id)
                result.append(task)
            except (OSError, json.JSONDecodeError):
                continue
        # Legacy migration: data/<dir>/task.json
        for path in sorted(self.root.glob("*/task.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                task = json.loads(path.read_text())
                data_dir = path.parent.name
                task_id = task.get("id") or task.get("name", "")
                # Skip if already migrated
                if any(r.get("id") == composite_id(data_dir, normalize_task_id(task_id)) for r in result):
                    continue
                # Auto-migrate
                task["data_dir"] = data_dir
                self._migrate_from_legacy(path, task)
                task["id"] = composite_id(data_dir, task.get("id", task.get("name", "")))
                task["mtime"] = path.stat().st_mtime
                result.append(task)
            except (OSError, json.JSONDecodeError):
                continue
        return result

    def _migrate_from_legacy(self, legacy_path: Path, task: dict) -> None:
        """Move data/<dir>/task.json → data/<dir>/tasks/<task_id>.json"""
        task_id = normalize_task_id(str(task.get("id") or task.get("name", "")))
        new_dir = legacy_path.parent / "tasks"
        new_dir.mkdir(parents=True, exist_ok=True)
        new_path = new_dir / f"{task_id}.json"
        if not new_path.exists():
            task_dir = task.get("task_dir")
            if not task_dir:
                task["task_dir"] = str(legacy_path.parent)
            new_path.write_text(json.dumps(task, indent=2, ensure_ascii=False))
        legacy_path.unlink(missing_ok=True)

    # ── CRUD ──────────────────────────────────────────────────────────────

    def get(self, composite_id: str) -> dict:
        data_dir, task_id = parse_composite_id(composite_id)
        path = self._resolve_path(data_dir, task_id)
        if not path.is_file():
            raise KeyError(composite_id)
        task = json.loads(path.read_text())
        task["data_dir"] = data_dir
        task["id"] = composite_id
        return task

    def save(self, task: dict) -> dict:
        # 保存草稿时不校验歌词等生成期约束（strict=False），生成时才严格校验
        validated = self.validate(task, strict=False)
        data_dir = validated["data_dir"]
        task_id = validated["id"]  # this is the simple id (not composite yet)
        path = self._resolve_path(data_dir, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(validated, indent=2, ensure_ascii=False))
        temporary.replace(path)
        validated["id"] = composite_id(data_dir, task_id)
        return validated

    def delete(self, composite_id: str) -> None:
        data_dir, task_id = parse_composite_id(composite_id)
        path = self._resolve_path(data_dir, task_id)
        if not path.is_file():
            raise KeyError(composite_id)
        path.unlink()
        # Remove tasks/ directory if empty
        try:
            next(path.parent.iterdir())
        except StopIteration:
            path.parent.rmdir()

    def clear_assets(self, composite_id: str, category: str | None = None) -> list[str]:
        """Delete Seedance asset cache entries. Returns list of removed keys.

        If category is None, clears all. Otherwise only clears matching keys
        (e.g. 'audio' clears keys containing 'audio').
        """
        import logging
        _log = logging.getLogger(__name__)
        data_dir, _ = parse_composite_id(composite_id)
        assets_path = self.config.resolve_inside("data_root", data_dir) / "seedance" / "assets.json"
        if not assets_path.is_file():
            return []
        assets = json.loads(assets_path.read_text())
        removed = []
        for k in list(assets.keys()):
            if category is None or category in k:
                del assets[k]
                removed.append(k)
        if removed:
            if assets:
                assets_path.write_text(json.dumps(assets, indent=2, ensure_ascii=False))
            else:
                assets_path.unlink()
            _log.info("Cleared %d asset entries (%s) from %s", len(removed), category or "all", assets_path)
        return removed

    # ── validation ────────────────────────────────────────────────────────

    def validate(self, task: dict, require_anchors: bool = True, strict: bool = True) -> dict:
        name = str(task.get("name", "")).strip()
        if not name:
            raise ValueError("task name is required")
        task_id = normalize_task_id(str(task.get("id") or name))
        mode = task.get("mode")
        if mode not in MODES:
            raise ValueError(f"invalid mode: {mode}")
        anchors = task.get("anchors") or []
        references = task.get("references") or []

        # Determine data_dir
        task_dir_override = task.get("task_dir")
        if task_dir_override:
            data_dir = normalize_task_id(Path(task_dir_override).name)
        else:
            data_dir = normalize_task_id(task.get("data_dir") or name)
        if not data_dir:
            raise ValueError("could not determine data directory")

        actual_task_dir = self.task_dir(data_dir, task_dir_override)
        # resume 轮询时不需要 anchors（提交阶段才用），仅校验 references（后处理需要）
        required = (anchors if require_anchors else []) + references
        for item in required:
            file = str(item.get("file", ""))
            if not file or not self._asset_path(actual_task_dir, file).is_file():
                raise ValueError(f"missing asset: {file}")

        lyrics = str(task.get("lyrics", "")).strip()
        lyrics_file = task.get("lyrics_file")
        if lyrics_file:
            path = self._asset_path(actual_task_dir, str(lyrics_file))
            if not path.is_file():
                raise ValueError(f"missing lyrics: {lyrics_file}")
            lyrics = path.read_text().strip()
        # 保存草稿（strict=False）时不校验歌词等生成期约束，仅在生成（strict=True）时严格校验
        if strict:
            has_audio = any(ref.get("pass_reference_audio", True) for ref in task.get("references", []))
            camera_policy = task.get("camera_policy")
            build_prompt(mode, lyrics, str(task.get("constraints", "")), has_audio_ref=has_audio, camera_policy=camera_policy, lyrics_timestamps=task.get("lyrics_timestamps"))

        result = dict(task)
        result.update(
            id=task_id,
            name=name,
            data_dir=data_dir,
            mode=mode,
            candidates=max(1, int(task.get("candidates", 4))),
            task_dir=task.get("task_dir") or str(actual_task_dir),
        )
        return result

    # ── path helpers ──────────────────────────────────────────────────────

    def task_dir(self, data_dir: str, override: str | None = None) -> Path:
        if not override:
            return self.config.resolve_inside("data_root", data_dir)
        path = Path(override).expanduser().resolve()
        allowed = [self.config.data_root, self.config.upload_root]
        if not any(path == root or root in path.parents for root in allowed):
            raise ValueError("task directory is outside allowed roots")
        return path

    def _asset_path(self, task_dir: Path, relative: str) -> Path:
        for base in (task_dir, self.root):
            path = (base / relative).resolve()
            if path.is_file() and (self.root in path.parents or path == self.root):
                return path
        raise ValueError(f"missing asset: {relative}")

    def _resolve_path(self, data_dir: str, task_id: str) -> Path:
        return self.config.resolve_inside("data_root", f"{data_dir}/tasks/{task_id}.json")
