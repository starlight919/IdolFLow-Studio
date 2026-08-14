from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

from idolmv_pipeline.seedance.credentials import NGROK_AUTHTOKEN, PINGGY_TOKEN

_START_LOCK = threading.Lock()

PROJECT_ROOT = Path(os.getenv("VIDEO_TUNNEL_ROOT", os.getenv("VIDEO_PROJECT_ROOT", Path(__file__).resolve().parents[2]))).resolve()
TUNNEL_STATE = PROJECT_ROOT / ".seedance_tunnel.json"
HTTP_PORT = int(os.getenv("VIDEO_TUNNEL_PORT", "8906"))
TUNNEL_TTL = 60 * 60  # 隧道 URL 缓存过期时间（Pinggy 免费版 60 分钟限时，取保守值；付费版固定 URL 重建也无害）


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
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise RuntimeError(
            f"文件不在隧道暴露目录内，无法生成公开 URL: {resolved}\n"
            f"  隧道暴露目录（PROJECT_ROOT/tunnel_root）: {root}\n"
            f"  请检查 VIDEO_TUNNEL_ROOT 配置是否覆盖了素材所在目录。"
        ) from None
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
    if not PINGGY_TOKEN:
        raise RuntimeError("PINGGY_TOKEN is required for Pinggy tunnel. Set it in .env (or use --provider ngrok).")
    log = log_path.open("w")
    # 带 token 登录；URL 稳定性取决于账号类型（免费版随机且限时，付费版固定且稳定）
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


def _ngrok_available() -> str | None:
    """检测 ngrok 是否安装，返回其路径；未安装返回 None。"""
    return shutil.which("ngrok")


def _start_ngrok(log_path: Path) -> tuple[subprocess.Popen, str]:
    ngrok_bin = _ngrok_available()
    if not ngrok_bin:
        raise RuntimeError("ngrok is not installed. Install it from https://ngrok.com/download (or `brew install ngrok`).")
    log = log_path.open("w")
    cmd = [ngrok_bin, "http", str(HTTP_PORT), "--log", "stdout"]
    if NGROK_AUTHTOKEN:
        cmd += ["--authtoken", NGROK_AUTHTOKEN]
    process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    # 从日志 stdout 提取 URL（ngrok v3 日志形如: url=https://xxx.ngrok-free.dev）
    # 不依赖 4040 web API（ngrok v3 下该 API 常因 allow_hosts 返回 502，不可靠）
    pattern = re.compile(r"url=(https://[A-Za-z0-9.-]+(?:ngrok[^\"\s]*))")
    url = None
    for _ in range(30):
        time.sleep(1)
        if log_path.exists():
            content = log_path.read_text(errors="ignore")
            match = pattern.search(content)
            if match:
                url = match.group(1)
                break
        if process.poll() is not None:
            break
    if not url:
        final_log = log_path.read_text(errors="ignore") if log_path.exists() else "No log file"
        process.terminate()
        raise RuntimeError(f"ngrok did not provide a public HTTPS URL. Log: {final_log[:500]}")
    # 校验隧道 URL 确实可达（避免 fallback 到不可用的 ngrok）
    if not _reachable(url):
        process.terminate()
        raise RuntimeError(f"ngrok URL is not reachable: {url}")
    return process, url


def _reachable(url: str, timeout: int = 15) -> bool:
    """Check if the tunnel URL is actually reachable.

    默认 15s：隧道首次访问可能较慢（SSL 握手 + 冷启动），5s 易误判为不可达。
    """
    try:
        # 用 requests（项目依赖）而非 urllib：urllib 对部分域名（如 ngrok-free.dev）SSL 握手不稳定
        requests.head(f"{url}/", timeout=timeout)
        return True
    except requests.RequestException:
        return False


def _launch(provider: str, http: subprocess.Popen, log_path: Path) -> dict:
    """按 provider 启动隧道，返回状态 dict。失败抛异常（供上层重试/回退）。"""
    if provider == "ngrok":
        tunnel, base_url = _start_ngrok(log_path)
    elif provider == "pinggy":
        tunnel, base_url = _start_pinggy(log_path)
    else:
        raise RuntimeError(f"unknown provider: {provider}")
    return {"provider": provider, "base_url": base_url, "http_pid": http.pid, "tunnel_pid": tunnel.pid, "port": HTTP_PORT, "root": str(PROJECT_ROOT), "created_at": time.time(), "running": True}


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
                # 复用：URL 可达，只重启死掉的进程（沿用已记录的 provider）
                http_pid = current.get("http_pid")
                tunnel_pid = current.get("tunnel_pid")
                existing = current.get("provider", "pinggy")
                if not current.get("http_alive", False):
                    http = _start_http()
                    http_pid = http.pid
                if not current.get("tunnel_alive", False):
                    log_path = Path("/tmp/seedance_tunnel.log")
                    tunnel, _ = _start_ngrok(log_path) if existing == "ngrok" else _start_pinggy(log_path)
                    tunnel_pid = tunnel.pid
                state = {**current, "http_pid": http_pid, "tunnel_pid": tunnel_pid, "running": True}
                TUNNEL_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
                return state

        # 全新启动（或重建）
        http = _start_http()
        log_path = Path("/tmp/seedance_tunnel.log")
        failures: list[tuple[str, str]] = []

        # 决定候选 provider 列表
        if provider == "pinggy":
            candidates = ["pinggy"]
        elif provider == "ngrok":
            candidates = ["ngrok"]
        else:  # auto：先 pinggy，失败回退 ngrok
            candidates = ["pinggy", "ngrok"]

        for cand in candidates:
            # pinggy 重试 3 次，ngrok 重试 1 次（避免 ngrok 反复失败拖慢）
            attempts = 3 if cand == "pinggy" else 1
            last_err = None
            for attempt in range(attempts):
                try:
                    state = _launch(cand, http, log_path)
                    TUNNEL_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
                    return state
                except Exception as exc:
                    last_err = exc
                    if attempt < attempts - 1:
                        time.sleep(5)
            failures.append((cand, str(last_err or "unknown error")))

        http.terminate()

        # 汇总所有 provider 的失败原因，给出可操作指引
        detail = "\n".join(f"  - {name}: {msg}" for name, msg in failures)
        hint = ""
        if any(name == "ngrok" for name, _ in failures) or any(name == "pinggy" for name, _ in failures):
            hint = (
                "\n提示: 如需 ngrok 回退，请先安装并配置（多平台）:\n"
                "  curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-agent.sh | bash\n"
                "  ngrok config add-authtoken <YOUR_TOKEN>"
            )
        raise RuntimeError(f"素材隧道启动失败，所有可用方案均未成功:\n{detail}{hint}")
