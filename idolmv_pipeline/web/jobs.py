from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig
from idolmv_pipeline.video_tasks.factory import adapter_from_task
from idolmv_pipeline.video_tasks.runner import VideoTaskRunner
from idolmv_pipeline.video_tasks.store import TaskStore


class JobManager:
    def __init__(self, config: VideoWorkspaceConfig, store: TaskStore):
        self.config = config
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=config.max_concurrent_runs)
        self.jobs: dict[str, dict] = {}
        self.lock = threading.RLock()
        self.state_dir = config.output_root / ".web-runs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._load()
        self._discover_manifests()

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
        """Check if a failed run can be resumed (run.json exists on disk)."""
        if job.get("status") != "failed":
            return False
        task_id = job.get("task_id", "")
        run_id = job.get("run_id", "")
        if not task_id or not run_id:
            return False
        data_dir = task_id.split("__")[0] if "__" in task_id else task_id
        run_state = self.config.output_root / data_dir / run_id / "run.json"
        return run_state.is_file()

    def submit(self, task_id: str, candidates: int | None = None) -> dict:
        task = self.store.get(task_id)
        run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
        job = {
            "run_id": run_id, "task_id": task_id, "task_name": task["name"],
            "stage": "queued", "message": "等待运行", "status": "queued",
            "completed": 0, "total": len(task["anchors"]) * len(task["references"]) * (candidates or task["candidates"]),
            "stage_completed": 0, "stage_total": 0,
            "created_at": datetime.now().isoformat(timespec="seconds"), "error": "",
        }
        with self.lock:
            self.jobs[run_id] = job
            self._save(job)
        self.executor.submit(self._run, run_id, task, candidates)
        return dict(job)

    def _run(self, run_id: str, task: dict, candidates: int | None) -> None:
        try:
            self._update(run_id, status="running", stage="validating", message="正在校验任务")
            adapter = adapter_from_task(task, self.config, self.store)
            runner = VideoTaskRunner(adapter, progress=lambda **values: self._update(run_id, **values))
            state = runner.run(run_id, candidates)
            self._update(
                run_id, status="completed" if state.data["status"] == "done" else "failed",
                stage="completed" if state.data["status"] == "done" else "failed",
                message="全部候选已完成" if state.data["status"] == "done" else "部分候选失败",
                manifest=str(adapter.output_dir / run_id / "review_manifest.json"),
                completed=self.jobs[run_id]["total"], total=self.jobs[run_id]["total"],
            )
        except Exception as exc:
            self._update(run_id, status="failed", stage="failed", message="运行失败", error=str(exc))

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

    def _discover_manifests(self) -> None:
        patterns = (
            self.config.output_root.glob("*/*/review_manifest.json"),
            self.config.data_root.glob("*/outputs/*/review_manifest.json"),
        )
        for manifest_path in (path for paths in patterns for path in paths):
            try:
                manifest = json.loads(manifest_path.read_text())
                run_id = manifest["run_id"]
                if run_id in self.jobs:
                    continue
                # manifest["task"] may be a legacy single-part id (e.g. "nini")
                # or a composite id (e.g. "nini__nini"). Normalise to composite.
                raw_task = str(manifest.get("task", ""))
                if "__" not in raw_task:
                    # Derive data_dir from the parent of the run directory
                    run_dir = manifest_path.parent
                    data_dir = run_dir.parent.name
                    task_id = f"{data_dir}__{raw_task}" if raw_task else data_dir
                else:
                    task_id = raw_task
                # Look up the task name if it still exists
                task_name = raw_task.split("__")[-1] if "__" in raw_task else raw_task
                try:
                    task = self.store.get(task_id)
                    task_name = task.get("name", task_name)
                except (KeyError, ValueError):
                    pass
                self.jobs[run_id] = {
                    "run_id": run_id,
                    "task_id": task_id,
                    "task_name": task_name,
                    "stage": "completed",
                    "message": "历史生成结果",
                    "status": "completed",
                    "completed": len(manifest.get("candidates", [])),
                    "total": len(manifest.get("candidates", [])),
                    "stage_completed": 0,
                    "stage_total": 0,
                    "created_at": datetime.fromtimestamp(manifest_path.stat().st_mtime).isoformat(timespec="seconds"),
                    "error": "",
                    "manifest": str(manifest_path),
                }
            except (OSError, KeyError, json.JSONDecodeError) as exc:
                logger.warning("Skipping manifest %s: %s", manifest_path, exc)

    def delete(self, run_id: str, remove_files: bool = False) -> bool:
        """Delete a run record from memory and disk. Returns True if found.

        If remove_files is True, also deletes the run output directory
        (runtime/outputs/<data_dir>/<run_id>) and work directory.
        File cleanup failures are logged but do not prevent record deletion.
        """
        data_dir = ""
        with self.lock:
            if run_id not in self.jobs:
                raise KeyError(run_id)
            job = self.jobs[run_id]
            task_id = job.get("task_id", "")
            data_dir = task_id.split("__")[0] if "__" in task_id else task_id
            del self.jobs[run_id]
            state_path = self.state_dir / f"{run_id}.json"
            if state_path.is_file():
                state_path.unlink()
        if remove_files and data_dir:
            try:
                self._remove_run_dirs(data_dir, run_id)
            except Exception as exc:
                logger.warning("Failed to clean up files for run %s: %s", run_id, exc)
        return True

    def _remove_run_dirs(self, data_dir: str, run_id: str) -> None:
        import shutil
        output_dir = self.config.output_root / data_dir / run_id
        work_dir = self.config.work_root / data_dir / run_id
        for d in (output_dir, work_dir):
            if d.is_dir():
                try:
                    shutil.rmtree(d)
                except OSError as exc:
                    logger.warning("Failed to remove %s: %s", d, exc)

    def _load(self) -> None:
        to_resume = []
        for path in self.state_dir.glob("*.json"):
            try:
                job = json.loads(path.read_text())
                if job.get("status") in {"queued", "running"}:
                    task_id = job.get("task_id", "")
                    run_id = job.get("run_id", "")
                    # Check if run.json exists (meaning Seedance tasks were already submitted)
                    data_dir = task_id.split("__")[0] if "__" in task_id else task_id
                    run_state = self.config.output_root / data_dir / run_id / "run.json"
                    if run_state.is_file():
                        # Seedance tasks exist, keep running and resume polling
                        job.update(stage="generating", message="服务重启，正在恢复轮询...")
                        to_resume.append(run_id)
                    else:
                        # Never submitted, mark as failed
                        job.update(status="failed", stage="failed", message="服务重启，任务未提交已中止", error="")
                self.jobs[job["run_id"]] = job
            except (OSError, KeyError, json.JSONDecodeError) as exc:
                logger.warning("Skipping state file %s: %s", path, exc)
        # Resume polling for runs with existing Seedance tasks
        for run_id in to_resume:
            try:
                self._resume_from_state(run_id)
            except Exception as exc:
                logger.error("Failed to resume run %s on load: %s", run_id, exc)
                self._update(run_id, status="failed", stage="failed", message=f"恢复失败: {exc}", error=str(exc))

    def _resume_from_state(self, run_id: str) -> None:
        """Re-submit a run for polling from saved state (after restart)."""
        job = self.jobs[run_id]
        task_id = job.get("task_id", "")
        if not task_id:
            raise ValueError(f"No task_id in job {run_id}")
        task = self.store.get(task_id)
        # resume 仅继续轮询已提交的候选，不再重新提交，因此无需校验 anchors 图片，
        # 仅需 references（音视频）用于下载后的裁剪与回灌音频
        adapter = adapter_from_task(task, self.config, self.store, require_anchors=False)
        runner = VideoTaskRunner(adapter, progress=lambda **values: self._update(run_id, **values))
        self.executor.submit(self._resume_run, run_id, runner)

    def _resume_run(self, run_id: str, runner: VideoTaskRunner) -> None:
        """Resume polling from existing run.json state."""
        try:
            self._update(run_id, status="running", stage="generating", message="正在恢复轮询...")
            state = runner.resume(run_id)
            self._update(
                run_id, status="completed" if state.data["status"] == "done" else "failed",
                stage="completed" if state.data["status"] == "done" else "failed",
                message="全部候选已完成" if state.data["status"] == "done" else "部分候选失败",
                manifest=str(runner.adapter.output_dir / run_id / "review_manifest.json"),
                completed=self.jobs[run_id]["total"], total=self.jobs[run_id]["total"],
            )
        except Exception as exc:
            self._update(run_id, status="failed", stage="failed", message="恢复运行失败", error=str(exc))
