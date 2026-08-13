from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

from idolmv_pipeline.seedance.credentials import PINGGY_TOKEN

_START_LOCK = threading.Lock()

PROJECT_ROOT = Path(os.getenv("VIDEO_TUNNEL_ROOT", os.getenv("VIDEO_PROJECT_ROOT", Path(__file__).resolve().parents[2]))).resolve()
TUNNEL_STATE = PROJECT_ROOT / ".seedance_tunnel.json"
HTTP_PORT = int(os.getenv("VIDEO_TUNNEL_PORT", "8906"))
TUNNEL_TTL = 60 * 60  # Pinggy 隧道 60 分钟过期，期内可复用


def configure(root: Path, port: int = 8906) -> None:
    global PROJECT_ROOT, TUNNEL_STATE, HTTP_PORT
    state = status()
    resolved = root.resolve()
    if state.get("running") and (Path(state.get("root", "")).resolve() != resolved or state.get("port") != port):
        raise RuntimeError("a tunnel is already running with a different root or port")
    PROJECT_ROOT = resolved
    TUNNEL_STATE = PROJECT_ROOT / ".seedance_tunnel.json"
    HTTP_PORT = port


def public_url(base_url: str, path: Path) -> str:
    relative = path.resolve().relative_to(PROJECT_ROOT.resolve())
    return f"{base_url.rstrip('/')}/{quote(relative.as_posix(), safe='/')}"


def check_url(url: str) -> None:
    with requests.get(url, stream=True, timeout=30) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Public URL returned HTTP {response.status_code}: {url}")


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status() -> dict:
    if not TUNNEL_STATE.exists():
        return {"running": False}
    state = json.loads(TUNNEL_STATE.read_text())
    created = state.get("created_at", 0)
    expired = (time.time() - created) > TUNNEL_TTL
    has_url = bool(state.get("base_url"))
    # 隧道未过期且 URL 存在即可复用（进程死了由 start() 负责重启）
    state["running"] = not expired and has_url
    state["http_alive"] = _alive(state.get("http_pid"))
    state["tunnel_alive"] = _alive(state.get("tunnel_pid"))
    return state


def _stop_processes(state: dict) -> None:
    for key in ("tunnel_pid", "http_pid"):
        pid = state.get(key)
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)


def stop() -> None:
    state = status()
    _stop_processes(state)
    TUNNEL_STATE.unlink(missing_ok=True)


def _start_http() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "http.server", str(HTTP_PORT), "--bind", "0.0.0.0", "--directory", str(PROJECT_ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _start_pinggy(log_path: Path) -> tuple[subprocess.Popen, str]:
    log = log_path.open("w")
    process = subprocess.Popen(["ssh", "-p", "443", f"-R0:localhost:{HTTP_PORT}", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30", f"{PINGGY_TOKEN}@a.pinggy.io"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    pattern = re.compile(r"https://[A-Za-z0-9.-]+(?:free\.pinggy\.net|run\.pinggy-free\.link|a\.free\.pinggy\.link)")
    for attempt in range(60):
        time.sleep(1)
        if log_path.exists():
            content = log_path.read_text(errors="ignore")
            match = pattern.search(content)
            if match:
                return process, match.group(0)
        if process.poll() is not None:
            break
    final_log = log_path.read_text(errors="ignore") if log_path.exists() else "No log file"
    process.terminate()
    raise RuntimeError(f"Pinggy did not provide a public HTTPS URL within 60 seconds. Log: {final_log[:500]}")


def _start_ngrok(log_path: Path) -> tuple[subprocess.Popen, str]:
    log = log_path.open("w")
    process = subprocess.Popen(["ngrok", "http", str(HTTP_PORT), "--log", "stdout"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(30):
        time.sleep(1)
        try:
            for item in requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2).json().get("tunnels", []):
                if item.get("public_url", "").startswith("https://"):
                    return process, item["public_url"]
        except requests.RequestException:
            pass
    process.terminate()
    raise RuntimeError("ngrok did not provide a public HTTPS URL")


def _reachable(url: str, timeout: int = 5) -> bool:
    """Check if the tunnel URL is actually reachable."""
    import urllib.request
    try:
        req = urllib.request.Request(f"{url}/", method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def start(provider: str = "auto") -> dict:
    with _START_LOCK:
        current = status()
        if current.get("running"):
            base_url = current["base_url"]
            # URL 未过期但不可达 → 清理旧状态，走全新启动
            if not _reachable(base_url):
                _stop_processes(current)
                TUNNEL_STATE.unlink(missing_ok=True)
                current = {"running": False}
            else:
                # 复用：URL 可达，只重启死掉的进程
                http_pid = current.get("http_pid")
                tunnel_pid = current.get("tunnel_pid")
                if not current.get("http_alive", False):
                    http = _start_http()
                    http_pid = http.pid
                if not current.get("tunnel_alive", False):
                    log_path = Path("/tmp/seedance_tunnel.log")
                    tunnel, _ = _start_pinggy(log_path)
                    tunnel_pid = tunnel.pid
                state = {**current, "http_pid": http_pid, "tunnel_pid": tunnel_pid, "running": True}
                TUNNEL_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
                return state
        # 全新启动（或重建）
        http = _start_http()
        log_path = Path("/tmp/seedance_tunnel.log")
        last_error = None
        for attempt in range(3):
            try:
                tunnel, base_url = _start_pinggy(log_path)
                state = {"provider": "pinggy", "base_url": base_url, "http_pid": http.pid, "tunnel_pid": tunnel.pid, "port": HTTP_PORT, "root": str(PROJECT_ROOT), "created_at": time.time(), "running": True}
                TUNNEL_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
                return state
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(5)
        http.terminate()
        raise last_error
