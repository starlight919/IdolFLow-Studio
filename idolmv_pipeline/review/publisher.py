from __future__ import annotations

import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Callable

# 保留 unicode 字符（中文任务名）与字母数字/下划线/连字符，仅替换空格等不安全字符。
# 此前 [^A-Za-z0-9_-] 会把所有中文替换成下划线：不同中文任务名的发布文件
# 全部塌缩成同一个文件名（如 "candidate_…"），在发布仓库里互相覆盖。
_SAFE = re.compile(r"[^\w\-]+", re.UNICODE)


def safe_name(value: str) -> str:
    return _SAFE.sub("_", value).strip("_") or "candidate"


class Publisher:
    def __init__(self, repo: Path, subdirectory: str, prefix: str, progress: Callable[[str, str], None]):
        self.repo = repo.resolve()
        self.destination = (self.repo / subdirectory).resolve()
        if self.repo not in self.destination.parents:
            raise ValueError("publish subdirectory must be inside repository")
        self.prefix = safe_name(prefix)
        self.progress = progress
        self.lock = threading.Lock()

    def publish(self, source: Path, candidate: dict) -> dict:
        with self.lock:
            source = source.resolve()
            if not source.is_file():
                raise FileNotFoundError(source)
            filename = "_".join((
                self.prefix,
                safe_name(candidate["anchor"]),
                safe_name(candidate["reference"]),
                safe_name(candidate["variant"]),
                f"candidate-{int(candidate['candidate']):02d}.mp4",
            ))
            relative = self.destination.relative_to(self.repo) / filename
            target = self.repo / relative
            self.destination.mkdir(parents=True, exist_ok=True)

            self.progress("copying", f"正在复制并重命名为 {filename}…")
            temporary = target.with_name(f".{filename}.{uuid.uuid4().hex}.tmp")
            shutil.copy2(source, temporary)
            temporary.replace(target)

            self.progress("checking", "正在检查 Git 状态…")
            status = self._git("status", "--short", "--", str(relative)).stdout.strip()
            if not status:
                return {"filename": filename, "path": str(target), "message": "文件已存在且没有变化"}

            self.progress("staging", "正在暂存当前入选视频…")
            self._git("add", "--", str(relative))
            self.progress("committing", "正在创建 Git commit…")
            self._git("commit", "-m", f"Add selected {self.prefix} candidate", "--", str(relative))
            commit = self._git("rev-parse", "--short", "HEAD").stdout.strip()
            self.progress("pushing", "正在上传视频到远程仓库…")
            self._git("push")
            return {"filename": filename, "path": str(target), "commit": commit, "message": "推送成功"}

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True)
