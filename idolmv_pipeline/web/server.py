from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from idolmv_pipeline.seedance import tunnel
from idolmv_pipeline.video_tasks.config import VideoWorkspaceConfig
from idolmv_pipeline.video_tasks.store import TaskStore
from idolmv_pipeline.image_tasks.store import AnchorTaskStore
from idolmv_pipeline.web.jobs import JobManager
from idolmv_pipeline.web.anchor_jobs import AnchorJobManager
from idolmv_pipeline.web.handlers import dispatch, handle_error

STATIC_DIR = Path(__file__).resolve().parent / "static"


class WorkspaceApplication:
    """Holds shared state: config, stores, job managers, review helpers."""

    def __init__(self, config: VideoWorkspaceConfig):
        self.config = config
        tunnel.configure(config.tunnel_root or config.project_root, config.tunnel_port)
        self.store = TaskStore(config)
        self.anchor_store = AnchorTaskStore(config)
        self.jobs = JobManager(config, self.store)
        self.anchor_jobs = AnchorJobManager(config, self.anchor_store)
        self.review_lock = threading.RLock()
        self.publish_progress: dict[str, dict] = {}

    def manifest(self, run_id: str) -> tuple[Path, dict]:
        job = self.jobs.get(run_id)
        path = Path(job.get("manifest", ""))
        if not path.is_file():
            raise FileNotFoundError("review manifest is not available")
        return path, json.loads(path.read_text())

    def review_state(self, manifest_path: Path) -> tuple[Path, dict]:
        path = manifest_path.parent / "review_state.json"
        return path, json.loads(path.read_text()) if path.is_file() else {"votes": {}, "published": {}}

    def save_review_state(self, path: Path, state: dict) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        temporary.replace(path)


class Handler(BaseHTTPRequestHandler):
    """Thin HTTP handler — all route logic lives in handlers.py."""

    app: WorkspaceApplication

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if dispatch(self, "GET", path):
                return
            self.send_error(404)
        except Exception as exc:
            if not handle_error(self, exc):
                self.send_error(500)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if dispatch(self, "POST", path):
                return
            self.send_error(404)
        except Exception as exc:
            if not handle_error(self, exc):
                self.send_error(500)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if dispatch(self, "DELETE", path):
                return
            self.send_error(404)
        except Exception as exc:
            if not handle_error(self, exc):
                self.send_error(500)

    def log_message(self, format: str, *args) -> None:
        # 只记录非 200 请求，避免正常请求刷屏
        if args and len(args) >= 2 and str(args[1]) != "200":
            import logging
            logging.getLogger("web").warning("%s %s %s", args[0], self.command, self.path)


def serve(config: VideoWorkspaceConfig) -> None:
    Handler.app = WorkspaceApplication(config)
    server = ThreadingHTTPServer((config.host, config.port), Handler)
    print(f"Video workspace: http://{config.host}:{config.port}/")
    server.serve_forever()
