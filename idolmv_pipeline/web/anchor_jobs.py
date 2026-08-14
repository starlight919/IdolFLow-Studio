from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from idolmv_pipeline.image_tasks.runner import AnchorTaskRunner
from idolmv_pipeline.image_tasks.store import AnchorTaskStore
from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig


class AnchorJobManager:
    def __init__(self, config: VideoWorkspaceConfig, store: AnchorTaskStore):
        self.config = config
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=config.max_concurrent_anchor_runs)
        self.jobs: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.state_dir = config.output_root / ".anchor-web-runs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def list(self) -> list[dict]:
        with self.lock:
            result = []
            for job in self.jobs.values():
                item = dict(job)
                item["can_resume"] = self._can_resume(item)
                result.append(item)
            return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def get(self, run_id: str) -> dict:
        with self.lock:
            if run_id not in self.jobs:
                raise KeyError(run_id)
            item = dict(self.jobs[run_id])
            item["can_resume"] = self._can_resume(item)
            return item

    def _can_resume(self, job: dict) -> bool:
        """Check if a failed anchor run can be resumed (run.json exists on disk)."""
        if job.get("status") != "failed":
            return False
        task_id = job.get("task_id", "")
        run_id = job.get("run_id", "")
        if not task_id or not run_id:
            return False
        run_state = self.store.generated_dir(task_id, run_id) / "run.json"
        return run_state.is_file()

    def submit(self, task_id: str, candidates: int | None = None) -> dict:
        task = self.store.load(task_id)
        run_id = datetime.now().strftime("anchor_%Y%m%d_%H%M%S_%f")
        total = candidates or task.candidates
        job = {
            "run_id": run_id, "task_id": task.id, "task_name": task.name, "media_type": "image",
            "stage": "queued", "message": "等待生成", "status": "queued",
            "completed": 0, "total": total,
            "stage_completed": 0, "stage_total": 0,
            "created_at": datetime.now().isoformat(timespec="seconds"), "error": "",
        }
        with self.lock:
            self.jobs[run_id] = job
            self._save(job)
        self.executor.submit(self._run, run_id, task.id, candidates)
        return dict(job)

    def _run(self, run_id: str, task_id: str, candidates: int | None) -> None:
        try:
            self._update(run_id, status="running", stage="validating", message="正在校验 Anchor 任务")
            runner = AnchorTaskRunner(self.store, progress=lambda **values: self._update(run_id, **values))
            state = runner.run(task_id, run_id, candidates)
            status = "completed" if state.data["status"] == "done" else "failed"
            total = self.jobs[run_id]["total"]
            self._update(
                run_id, status=status, stage=status,
                message="Anchor 候选已完成" if status == "completed" else "部分候选失败",
                manifest=state.data.get("manifest", ""),
                completed=total, total=total,
            )
        except Exception as exc:
            self._update(run_id, status="failed", stage="failed", message="Anchor 生成失败", error=str(exc))

    def _update(self, run_id: str, **values) -> None:
        with self.lock:
            job = self.jobs[run_id]
            stage = values.get("stage", job["stage"])
            stage_completed = values.pop("completed", None)
            stage_total = values.pop("total", None)
            job.update(values, stage=stage, updated_at=datetime.now().isoformat(timespec="seconds"))
            if stage_completed is not None:
                job["stage_completed"] = stage_completed
            if stage_total is not None:
                job["stage_total"] = stage_total
            # 只有进入真正的生成/完成阶段才推进整体进度条，
            # 避免提交（submitting）阶段就把进度拉满；
            # failed 阶段不推进，进度条停在已完成数，与视频任务一致
            if stage in {"generating", "completed"} and stage_completed is not None:
                job["completed"] = stage_completed
                if stage_total is not None:
                    job["total"] = stage_total
            self._save(job)

    def _save(self, job: dict) -> None:
        path = self.state_dir / f"{job['run_id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, indent=2, ensure_ascii=False))
        temporary.replace(path)

    def delete(self, run_id: str, remove_files: bool = False) -> bool:
        """Delete an anchor run record from memory and disk. Returns True if found.

        If remove_files is True, also deletes the generated images under
        data/<dir>/anchors/generated/<run_id>/.
        """
        with self.lock:
            if run_id not in self.jobs:
                raise KeyError(run_id)
            job = self.jobs[run_id]
            task_id = job.get("task_id", "")
            del self.jobs[run_id]
            state_path = self.state_dir / f"{run_id}.json"
            if state_path.is_file():
                state_path.unlink()
        if remove_files and task_id:
            try:
                import shutil
                generated_dir = self.store.generated_dir(task_id, run_id)
                if generated_dir.is_dir():
                    shutil.rmtree(generated_dir)
            except Exception as exc:
                logger.warning("Failed to clean up files for anchor run %s: %s", run_id, exc)
        return True

    def _load(self) -> None:
        to_resume = []
        for path in self.state_dir.glob("*.json"):
            try:
                job = json.loads(path.read_text())
                if job.get("status") in {"queued", "running"}:
                    task_id = job.get("task_id", "")
                    run_id = job.get("run_id", "")
                    run_state = self.store.generated_dir(task_id, run_id) / "run.json"
                    if run_state.is_file():
                        job.update(stage="generating", message="服务重启，正在恢复轮询...")
                        to_resume.append(run_id)
                    else:
                        job.update(status="failed", stage="failed", message="服务重启，任务未提交已中止", error="")
                # Fix stale manifest paths from pre-refactor era (task_id used to be anchor-<ts>)
                manifest = job.get("manifest", "")
                if manifest:
                    mp = Path(manifest)
                    if not mp.is_file():
                        task_id = job.get("task_id", "")
                        run_id = job.get("run_id", "")
                        if task_id and run_id:
                            fixed = self.store.generated_dir(task_id, run_id) / "review_manifest.json"
                            if fixed.is_file():
                                job["manifest"] = str(fixed)
                                logger.info("Fixed stale manifest path for %s: %s -> %s", run_id, mp, fixed)
                self.jobs[job["run_id"]] = job
            except (OSError, KeyError, json.JSONDecodeError) as exc:
                logger.warning("Skipping anchor state file %s: %s", path, exc)
                continue
        for run_id in to_resume:
            try:
                self._resume_from_state(run_id)
            except Exception as exc:
                logger.error("Failed to resume anchor run %s on load: %s", run_id, exc)
                self._update(run_id, status="failed", stage="failed", message=f"恢复失败: {exc}", error=str(exc))

    def _resume_from_state(self, run_id: str) -> None:
        """Re-submit an anchor run for polling from saved state (after restart)."""
        job = self.jobs[run_id]
        task_id = job.get("task_id", "")
        if not task_id:
            raise ValueError(f"No task_id in job {run_id}")
        task = self.store.get(task_id)
        runner = AnchorTaskRunner(self.store, progress=lambda **values: self._update(run_id, **values))
        self.executor.submit(self._resume_run, run_id, task_id, runner)

    def _resume_run(self, run_id: str, task_id: str, runner: AnchorTaskRunner) -> None:
        """Resume polling from existing run.json state."""
        try:
            self._update(run_id, status="running", stage="generating", message="正在恢复轮询...")
            state = runner.resume(task_id, run_id)
            self._update(
                run_id, status="completed" if state.data["status"] == "done" else "failed",
                stage="completed" if state.data["status"] == "done" else "failed",
                message="全部 Anchor 候选已完成" if state.data["status"] == "done" else "部分 Anchor 候选失败",
                completed=self.jobs[run_id].get("total", 0),
                total=self.jobs[run_id].get("total", 0),
            )
        except Exception as exc:
            self._update(run_id, status="failed", stage="failed", message="恢复运行失败", error=str(exc))
