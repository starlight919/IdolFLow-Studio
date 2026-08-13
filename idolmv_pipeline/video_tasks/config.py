from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class VideoWorkspaceConfig:
    project_root: Path
    data_root: Path
    work_root: Path
    output_root: Path
    upload_root: Path
    publish_repo: Path
    tunnel_root: Path | None = None
    publish_subdirectory: str = "selected"
    host: str = "127.0.0.1"
    port: int = 8913
    tunnel_port: int = 8906
    max_concurrent_runs: int = 2
    max_concurrent_anchor_runs: int = 2
    image_poll_workers: int = 4
    anchor_model: str = "gpt-image-2"
    publish_enabled: bool = False
    submit_secret: str = ""
    submit_hash: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "VideoWorkspaceConfig":
        project = Path(os.getenv("VIDEO_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()
        values = {
            "project_root": project,
            "data_root": project / "data",
            "work_root": project / "runtime" / "work",
            "output_root": project / "runtime" / "outputs",
            "upload_root": project / "data",
            "publish_repo": project / "runtime" / "publish",
            "tunnel_root": project,
        }
        config_path = path or Path(os.getenv("VIDEO_WORKSPACE_CONFIG", project / "video-workspace.json"))
        if config_path.is_file():
            values.update(json.loads(config_path.read_text()))
        env = {
            "project_root": "VIDEO_PROJECT_ROOT",
            "data_root": "VIDEO_DATA_ROOT",
            "work_root": "VIDEO_WORK_ROOT",
            "output_root": "VIDEO_OUTPUT_ROOT",
            "upload_root": "VIDEO_UPLOAD_ROOT",
            "publish_repo": "VIDEO_PUBLISH_REPO",
            "tunnel_root": "VIDEO_TUNNEL_ROOT",
            "publish_subdirectory": "VIDEO_PUBLISH_SUBDIRECTORY",
            "host": "VIDEO_WEB_HOST",
            "port": "VIDEO_WEB_PORT",
            "tunnel_port": "VIDEO_TUNNEL_PORT",
            "max_concurrent_runs": "VIDEO_MAX_CONCURRENT_RUNS",
            "max_concurrent_anchor_runs": "VIDEO_MAX_CONCURRENT_ANCHOR_RUNS",
            "image_poll_workers": "VIDEO_IMAGE_POLL_WORKERS",
            "anchor_model": "VIDEO_ANCHOR_MODEL",
            "publish_enabled": "VIDEO_PUBLISH_ENABLED",
            "submit_secret": "VIDEO_SUBMIT_SECRET",
            "submit_hash": "VIDEO_SUBMIT_HASH",
        }
        for key, variable in env.items():
            if variable in os.environ:
                values[key] = os.environ[variable]
        for key in ("project_root", "data_root", "work_root", "output_root", "upload_root", "publish_repo", "tunnel_root"):
            values[key] = Path(values[key]).expanduser().resolve()
        for key in ("port", "tunnel_port", "max_concurrent_runs", "max_concurrent_anchor_runs", "image_poll_workers"):
            if key in values:
                values[key] = int(values[key])
        if isinstance(values.get("publish_enabled"), str):
            values["publish_enabled"] = values["publish_enabled"].lower() in {"1", "true", "yes", "on"}
        return cls(**values)

    def verify_submit_password(self, password: str) -> bool:
        """用 secret 对 password 做 HMAC-SHA256，和 hash 比对。"""
        if not self.submit_secret or not self.submit_hash:
            return False
        computed = hmac.new(self.submit_secret.encode(), password.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, self.submit_hash)

    def public_dict(self) -> dict:
        data = asdict(self)
        data.pop("submit_secret", None)
        data.pop("submit_hash", None)
        return {key: str(value) if isinstance(value, Path) else value for key, value in data.items()}

    def resolve_inside(self, root_name: str, relative: str = "") -> Path:
        root = getattr(self, root_name).resolve()
        result = (root / relative).resolve()
        if result != root and root not in result.parents:
            raise ValueError(f"path escapes {root_name}")
        return result
