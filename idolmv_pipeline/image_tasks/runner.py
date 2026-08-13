from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from idolmv_pipeline.api.phanimg import PhanImgClient
from idolmv_pipeline.config.settings import GPT_IMAGE_API_KEY, GPT_IMAGE_API_ROOT
from idolmv_pipeline.image_tasks.manifest import write_manifest
from idolmv_pipeline.image_tasks.prompts import build_anchor_prompt
from idolmv_pipeline.image_tasks.store import AnchorTaskStore
from idolmv_pipeline.seedance.state import RunState


def _fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {"file": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


class AnchorTaskRunner:
    def __init__(self, store: AnchorTaskStore, client: PhanImgClient | None = None, progress=None):
        self.store = store
        self.client = client or PhanImgClient(GPT_IMAGE_API_ROOT, GPT_IMAGE_API_KEY)
        self.progress = progress or (lambda **_: None)
        self.lock = threading.Lock()

    def _state(self, task_id: str, run_id: str) -> RunState:
        path = self.store.generated_dir(task_id, run_id) / "run.json"
        return RunState(path, {"task": task_id, "run_id": run_id, "status": "created", "jobs": []})

    def submit(self, task_id: str, run_id: str, candidates: int | None = None) -> RunState:
        self.progress(stage="validating", message="正在校验 Anchor 任务")
        task = self.store.load(task_id)
        prompt, mapping = build_anchor_prompt(task)
        references = [self.store.asset_path(task.id, item.file) for item in task.references]
        state = self._state(task.id, run_id)
        state.data.update(prompt=prompt, references=[dict(item, fingerprint=_fingerprint(references[index])) for index, item in enumerate(mapping)])
        count = candidates or task.candidates
        existing = {job["id"] for job in state.jobs()}
        self.progress(stage="submitting", message=f"准备提交 {count} 个 Anchor 候选", completed=len(existing), total=count)
        for candidate in range(1, count + 1):
            job_id = f"anchor__{candidate:02d}"
            if job_id in existing:
                continue
            provider_id = self.client.create_task(prompt, references, task.size, task.resolution)
            state.jobs().append({"id": job_id, "candidate": candidate, "task_id": provider_id, "status": "submitted"})
            state.save()
            self.progress(stage="submitting", message=f"已提交 {candidate}/{count}", completed=candidate, total=count)
        state.update(status="submitted")
        return state

    def _finish(self, task_id: str, run_id: str, state: RunState, job: dict) -> None:
        if job.get("status") == "done" and Path(job.get("file", "")).is_file():
            return
        destination = self.store.generated_dir(task_id, run_id) / f"candidate-{job['candidate']:02d}.jpg"
        self.client.poll_to_file(job["task_id"], destination)
        with self.lock:
            job.update(status="done", file=str(destination))
            state.save()

    def poll(self, task_id: str, run_id: str) -> RunState:
        task = self.store.load(task_id)
        state = self._state(task.id, run_id)
        pending = [job for job in state.jobs() if job.get("status") != "done"]
        workers = min(self.store.config.image_poll_workers, max(1, len(pending)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self._finish, task.id, run_id, state, job): job for job in pending}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    with self.lock:
                        futures[future].update(status="failed", error=str(exc))
                        state.save()
                done = sum(job.get("status") == "done" for job in state.jobs())
                self.progress(stage="generating", message=f"Anchor 候选完成 {done}/{len(state.jobs())}", completed=done, total=len(state.jobs()))
        status = "done" if state.jobs() and all(job.get("status") == "done" for job in state.jobs()) else "failed"
        prompt = state.data.get("prompt", "")
        mapping = [{key: value for key, value in item.items() if key != "fingerprint"} for item in state.data.get("references", [])]
        manifest = write_manifest(task, run_id, state.jobs(), prompt, mapping, self.store.generated_dir(task.id, run_id))
        state.update(status=status, manifest=str(manifest))
        self.progress(stage="completed" if status == "done" else "failed", message="Anchor 生成完成" if status == "done" else "部分 Anchor 候选失败")
        return state

    def run(self, task_id: str, run_id: str, candidates: int | None = None, submit_only: bool = False) -> RunState:
        state = self.submit(task_id, run_id, candidates)
        return state if submit_only else self.poll(task_id, run_id)

    def resume(self, task_id: str, run_id: str) -> RunState:
        return self.poll(task_id, run_id)

    def status(self, task_id: str, run_id: str) -> dict:
        return self._state(task_id, run_id).data
