from __future__ import annotations

import json
import mimetypes
import re
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from idolmv_pipeline.image_tasks.prompts import build_anchor_prompt, preset_options
from idolmv_pipeline.image_tasks.models import AnchorTask
from idolmv_pipeline.review.publisher import Publisher, safe_name
from idolmv_pipeline.seedance.media import extract_audio
from idolmv_pipeline.video_tasks.factory import adapter_from_task
from idolmv_pipeline.video_tasks.prompts import build_prompt
from idolmv_pipeline.video_tasks.planner import ASSET_AVAILABLE
from idolmv_pipeline.video_tasks.runner import VideoTaskRunner

STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

_SAFE_FILENAME = re.compile(r"[\\/:*?\"<>|\s]+")


def safe_filename(value: str) -> str:
    """下载文件名安全化：保留中文、字母数字、下划线、连字符，替换路径分隔符等非法字符。"""
    return _SAFE_FILENAME.sub("_", value).strip("_") or "candidate"

# ── Route Registry ───────────────────────────────────────────────────────────

_ROUTES: dict[str, list[tuple[str, callable]]] = {"GET": [], "POST": [], "DELETE": []}


def _register(method: str, path: str):
    """Decorator / factory: register a handler for ``method`` + ``path``.

    ``path`` can be:
    - an exact path like ``"/api/tasks"``
    - a prefix path like ``"/api/anchor-tasks/"`` (matches ``/api/anchor-tasks/<id>``)
    - a multi-segment prefix like ``"/api/anchor-runs/"``
    """
    def decorator(func):
        _ROUTES[method].append((path, func))
        return func
    return decorator


def dispatch(handler: BaseHTTPRequestHandler, method: str, path: str) -> bool:
    """Try every registered handler; return True if one consumed the request.

    Routes are tried longest-prefix-first so that ``/api/tasks`` is matched
    before the catch-all ``/`` route.
    """
    routes = sorted(_ROUTES.get(method, []), key=lambda r: -len(r[0]))
    for prefix, func in routes:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            func(handler, path)
            return True
    return False


# ── Simple in-memory TTL helpers ─────────────────────────────────────────────

_INTERMEDIATE_CACHE: dict[str, tuple[float, dict]] = {}
_INTERMEDIATE_CACHE_TTL = 3.0  # seconds — balances freshness vs. filesystem I/O


def _cached_get_intermediate(handler, run_id: str) -> None:
    """Return cached intermediate results if fresh, otherwise re-scan."""
    now = time.monotonic()
    entry = _INTERMEDIATE_CACHE.get(run_id)
    if entry is not None:
        expire_at, result = entry
        if now < expire_at:
            return json_response(handler, 200, result)
    _get_intermediate_for_run(handler, run_id)

def json_response(handler, status: int, data) -> None:
    body = json.dumps(data, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def read_json(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(length) or b"{}")


def serve_file(handler, path: Path, content_type: str | None = None,
               download_name: str | None = None, root: Path | None = None) -> None:
    resolved = path.resolve()
    if root is not None:
        root = root.resolve()
        if root not in resolved.parents and resolved != root:
            raise FileNotFoundError(path)
    if not resolved.is_file():
        raise FileNotFoundError(path)
    size = resolved.stat().st_size
    start, end = 0, size - 1
    range_header = handler.headers.get("Range")
    status = 200
    if range_header and range_header.startswith("bytes="):
        bounds = range_header[6:].split("-", 1)
        start = int(bounds[0] or 0)
        end = min(int(bounds[1]) if bounds[1] else end, end)
        if start < 0 or start >= size or end < start:
            handler.send_response(416)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.end_headers()
            return
        status = 206

    handler.send_response(status)
    # 前端 JS/CSS/HTML 用 no-store 强制每次加载最新（避免浏览器缓存旧 JS 导致功能不生效）；
    # 素材文件（图片/音频/视频）保留 no-cache，允许按需重新验证
    if resolved.suffix.lower() in (".js", ".css", ".html", ".htm"):
        handler.send_header("Cache-Control", "no-store")
    else:
        handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Content-Type",
                        content_type or mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    if download_name:
        handler.send_header("Content-Disposition",
                            f"attachment; filename*=UTF-8''{quote(download_name)}")
    handler.end_headers()
    if handler.command == "HEAD":
        return

    remaining = end - start + 1
    try:
        with resolved.open("rb") as source:
            source.seek(start)
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _is_video_file(path: Path) -> bool:
    mt, _ = mimetypes.guess_type(str(path))
    return mt is not None and mt.startswith("video/")


def _is_audio_file(path: Path) -> bool:
    mt, _ = mimetypes.guess_type(str(path))
    return mt is not None and mt.startswith("audio/")


def _extract_audio_response(handler, source: Path, data_root: Path) -> None:
    if _is_audio_file(source):
        audio_path = source
    elif _is_video_file(source):
        audio_dir = source.parent / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"{source.stem}.mp3"
        if not audio_path.exists():
            extract_audio(source, audio_path)
    else:
        return json_response(handler, 400, {"error": "file is neither video nor audio"})

    try:
        relative = audio_path.relative_to(data_root).as_posix()
    except ValueError:
        relative = audio_path.name
    json_response(handler, 200, {
        "audio_file": relative,
        "audio_url": f"/api/files?root=data_root&path={quote(relative)}",
    })


def _extract_audio_by_path(handler) -> None:
    data = read_json(handler) or {}
    rel = (data.get("file") or "").strip().lstrip("/")
    if not rel:
        return json_response(handler, 400, {"error": "file is required"})
    source = handler.app.config.resolve_inside("data_root", rel)
    if not source.is_file():
        return json_response(handler, 404, {"error": f"missing file: {rel}"})
    _extract_audio_response(handler, source, handler.app.config.data_root)


def _extract_task_audio(handler, task_id: str) -> None:
    data = read_json(handler) or {}
    task = handler.app.store.get(task_id)
    refs = task.get("references", [])
    if not refs:
        return json_response(handler, 400, {"error": "task has no references"})
    index = int(data.get("reference_index", 0))
    if index < 0 or index >= len(refs):
        return json_response(handler, 400, {"error": "invalid reference_index"})
    ref = refs[index]
    task_dir = Path(task["task_dir"])
    # 用 store._asset_path 定位：兼容 file 相对 task_dir 或相对 data_root 两种写法
    try:
        source = handler.app.store._asset_path(task_dir, ref["file"])
    except ValueError:
        return json_response(handler, 404, {"error": f"missing reference file: {ref['file']}"})
    _extract_audio_response(handler, source, handler.app.config.data_root)


def _get_lyrics_timestamps(handler, task_id: str) -> None:
    task = handler.app.store.get(task_id)
    json_response(handler, 200, {"lyrics_timestamps": task.get("lyrics_timestamps", [])})


def _save_lyrics_timestamps(handler, task_id: str) -> None:
    data = read_json(handler) or {}
    task = handler.app.store.get(task_id)
    task["lyrics_timestamps"] = data.get("lyrics_timestamps", [])
    task.pop("id", None)
    handler.app.store.save(task)
    json_response(handler, 200, {"lyrics_timestamps": task["lyrics_timestamps"]})


def find_candidate(manifest: dict, candidate_id: str) -> dict:
    for candidate in manifest["candidates"]:
        if candidate["id"] == candidate_id:
            return candidate
    raise KeyError(candidate_id)


# ── Handlers: Static & File ──────────────────────────────────────────────────

@_register("GET", "/static/")
def handle_static(handler, path: str):
    serve_file(handler, STATIC_DIR / path.removeprefix("/static/"), root=STATIC_DIR)


@_register("GET", "/")
@_register("GET", "/tasks")
@_register("GET", "/runs")
@_register("GET", "/review")
def handle_index(handler, path: str):
    serve_file(handler, STATIC_DIR / "index.html", "text/html; charset=utf-8")


@_register("GET", "/api/settings/public")
def handle_public_settings(handler, path: str):
    json_response(handler, 200, handler.app.config.public_dict())


@_register("GET", "/api/file-preview")
def handle_file_preview(handler, path: str):
    parsed = urlparse(handler.path)
    query = parse_qs(parsed.query)
    root_name = query.get("root", ["data_root"])[0]
    if root_name not in {"data_root", "upload_root"}:
        raise ValueError("invalid root")
    filepath = handler.app.config.resolve_inside(root_name, query.get("path", [""])[0])
    serve_file(handler, filepath)


@_register("GET", "/api/files")
def handle_list_files(handler, path: str):
    parsed = urlparse(handler.path)
    _list_files(handler, parsed)


@_register("GET", "/api/intermediate/")
def handle_intermediate_results(handler, path: str):
    parts = path.strip("/").split("/")
    run_id = parts[2]
    try:
        _cached_get_intermediate(handler, run_id)
    except Exception as exc:
        json_response(handler, 404, {"error": str(exc)})


def _list_files(handler, parsed) -> None:
    query = parse_qs(parsed.query)
    root_name = query.get("root", ["data_root"])[0]
    if root_name not in {"data_root", "upload_root"}:
        raise ValueError("invalid root")
    target = handler.app.config.resolve_inside(root_name, query.get("path", [""])[0])
    # path 指向文件时，直接返回文件内容（供 audio/video 播放，支持 Range）
    if target.is_file():
        serve_file(handler, target)
        return
    if not target.is_dir():
        raise FileNotFoundError(target)
    root = getattr(handler.app.config, root_name)
    items = [{
        "name": item.name, "path": item.relative_to(root).as_posix(), "directory": item.is_dir(),
        "size": item.stat().st_size if item.is_file() else None,
    } for item in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())) if not item.name.startswith(".")]
    json_response(handler, 200, {"root": root_name, "path": target.relative_to(root).as_posix(), "items": items})


@_register("POST", "/api/extract-audio")
def handle_extract_audio(handler, path: str):
    _extract_audio_by_path(handler)


@_register("POST", "/api/folders")
def handle_folder_create(handler, path: str):
    data = read_json(handler)
    root_name = data.get("root", "data_root")
    if root_name not in {"data_root", "upload_root"}:
        return json_response(handler, 400, {"error": "invalid root"})
    parent = handler.app.config.resolve_inside(root_name, data.get("parent", ""))
    if not parent.is_dir():
        return json_response(handler, 404, {"error": "parent not found"})
    name = str(data.get("name", "")).strip()
    if not name or "/" in name or "\\" in name:
        return json_response(handler, 400, {"error": "invalid folder name"})
    new_dir = parent / name
    if new_dir.exists():
        return json_response(handler, 409, {"error": "folder already exists"})
    new_dir.mkdir(parents=True)
    # 自动创建约定子目录，引导素材落到固定位置（图片 → anchors/，音视频 → references/）
    (new_dir / "anchors").mkdir(exist_ok=True)
    (new_dir / "references").mkdir(exist_ok=True)
    root = getattr(handler.app.config, root_name)
    json_response(handler, 201, {"name": name, "path": new_dir.relative_to(root).as_posix()})


def _data_dir_usage(handler, data_dir: str) -> dict:
    """统计某个数据目录下关联的任务、运行、Anchor 任务，供删除前强确认展示。

    返回层级信息，便于前端渲染清晰的级联树（目录 → 任务 → 运行产物）。
    """
    tasks = [t for t in handler.app.store.list() if t.get("data_dir") == data_dir]
    anchor_task = next((t for t in handler.app.anchor_store.list() if t.get("data_dir") == data_dir), None)
    video_runs = [r for r in handler.app.jobs.list() if (r.get("task_id") or "").split("__")[0] == data_dir]
    anchor_runs = [r for r in handler.app.anchor_jobs.list() if (r.get("task_id") or "") == data_dir]

    # 每个视频任务的运行数（按 task_id 关联）
    tasks_detail = []
    for t in tasks:
        run_count = sum(1 for r in video_runs if r.get("task_id") == t["id"])
        tasks_detail.append({
            "id": t["id"],
            "name": t.get("name"),
            "run_count": run_count,
        })

    # 参考音视频素材（references/ 下的文件数）
    refs_dir = handler.app.config.resolve_inside("data_root", f"{data_dir}/references")
    ref_count = len([p for p in refs_dir.iterdir() if p.is_file()]) if refs_dir.is_dir() else 0

    # Seedance 缓存是否存在
    seedance_dir = handler.app.config.resolve_inside("data_root", f"{data_dir}/seedance")
    has_seedance = seedance_dir.is_dir()

    return {
        "data_dir": data_dir,
        "tasks": tasks_detail,
        "anchor_task": {
            "id": anchor_task["id"],
            "name": anchor_task.get("name"),
            "run_count": len(anchor_runs),
        } if anchor_task else None,
        "video_runs": len(video_runs),
        "anchor_runs": len(anchor_runs),
        "ref_count": ref_count,
        "has_seedance": has_seedance,
    }


@_register("GET", "/api/data-dirs/")
def handle_data_dir_get(handler, path: str):
    parts = path.strip("/").split("/")
    if len(parts) < 3:
        return json_response(handler, 400, {"error": "data dir is required"})
    data_dir = unquote(parts[2])
    target = handler.app.config.resolve_inside("data_root", data_dir)
    if not target.is_dir():
        return json_response(handler, 404, {"error": f"data dir not found: {data_dir}"})
    json_response(handler, 200, _data_dir_usage(handler, data_dir))


@_register("DELETE", "/api/data-dirs/")
def handle_data_dir_delete(handler, path: str):
    parts = path.strip("/").split("/")
    if len(parts) < 3:
        return json_response(handler, 400, {"error": "data dir is required"})
    data_dir = unquote(parts[2])
    target = handler.app.config.resolve_inside("data_root", data_dir)
    if not target.is_dir():
        return json_response(handler, 404, {"error": f"data dir not found: {data_dir}"})
    if target == handler.app.config.data_root.resolve():
        return json_response(handler, 400, {"error": "cannot delete data root"})

    # 1. 删除该目录下所有视频任务的 run 记录 + 生成产物（runtime/outputs、work）
    for task in list(handler.app.store.list()):
        if task.get("data_dir") != data_dir:
            continue
        task_id = task["id"]
        for run in list(handler.app.jobs.list()):
            if run.get("task_id") == task_id:
                try:
                    handler.app.jobs.delete(run["run_id"], remove_files=True)
                except KeyError:
                    pass

    # 2. 删除该目录下所有 Anchor run 记录 + 生成候选（anchors/generated/<run_id>）
    for run in list(handler.app.anchor_jobs.list()):
        if (run.get("task_id") or "") == data_dir:
            try:
                handler.app.anchor_jobs.delete(run["run_id"], remove_files=True)
            except KeyError:
                pass

    # 3. 删除视频任务定义（tasks/*.json）
    for task in list(handler.app.store.list()):
        if task.get("data_dir") == data_dir:
            try:
                handler.app.store.delete(task["id"])
            except KeyError:
                pass

    # 4. 删除 Anchor 任务（anchors/ 子目录）
    if next((t for t in handler.app.anchor_store.list() if t.get("data_dir") == data_dir), None):
        try:
            handler.app.anchor_store.delete(data_dir)
        except (KeyError, OSError):
            pass

    # 5. 最后删除整个数据目录（含 references/、seedance/、残留 anchors/ 等）
    shutil.rmtree(target, ignore_errors=True)

    json_response(handler, 200, {"ok": True, "data_dir": data_dir})


def _get_intermediate_for_run(handler, run_id: str) -> None:
    job = handler.app.jobs.get(run_id)
    task = handler.app.store.get(job["task_id"])
    adapter = adapter_from_task(task, handler.app.config, handler.app.store)
    output_dir = adapter.output_dir / run_id

    if not output_dir.exists():
        return json_response(handler, 200, {"run_id": run_id, "status": job["status"], "intermediates": [], "message": "输出目录尚未创建"})

    intermediates = []
    seedance_dirs = sorted(output_dir.glob("*/seedance"), key=lambda p: p.stat().st_mtime)

    for seedance_dir in seedance_dirs:
        state_file = seedance_dir / "state.json"
        assets_file = seedance_dir / "assets.json"

        state_data = {}
        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        assets_data = {}
        if assets_file.exists():
            try:
                assets_data = json.loads(assets_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        video_files = list(seedance_dir.glob("*.mp4"))
        intermediates.append({
            "job_name": seedance_dir.parent.name,
            "state": state_data.get("status", "unknown"),
            "message": state_data.get("message", ""),
            "assets": assets_data,
            "video_count": len(video_files),
            "videos": [{"path": str(v.relative_to(output_dir)), "name": v.name, "size": v.stat().st_size} for v in video_files],
            "updated_at": state_file.stat().st_mtime if state_file.exists() else None,
        })

    json_response(handler, 200, {
        "run_id": run_id, "status": job["status"], "stage": job["stage"],
        "message": job["message"], "completed": job["completed"], "total": job["total"],
        "intermediates": intermediates,
    })
    # Cache for reuse by frontend polling (avoids repeated filesystem scans)
    _INTERMEDIATE_CACHE[run_id] = (time.monotonic() + _INTERMEDIATE_CACHE_TTL, {
        "run_id": run_id, "status": job["status"], "stage": job["stage"],
        "message": job["message"], "completed": job["completed"], "total": job["total"],
        "intermediates": intermediates,
    })


# ── Handlers: Anchor ─────────────────────────────────────────────────────────

@_register("GET", "/api/anchor-presets")
def handle_anchor_presets(handler, path: str):
    json_response(handler, 200, preset_options())


@_register("POST", "/api/anchor-optimize")
def handle_anchor_optimize(handler, path: str):
    """Optimize natural-language prompt into structured constraints + canonical prompt."""
    from idolmv_pipeline.image_tasks.optimizer import optimize
    data = read_json(handler)
    text = str(data.get("text", "")).strip()
    if not text:
        return json_response(handler, 400, {"error": "请提供图文合成描述"})
    reference_names = data.get("references") if isinstance(data.get("references"), list) else []
    try:
        result = optimize(text, reference_names or None)
        json_response(handler, 200, result)
    except ValueError as e:
        json_response(handler, 400, {"error": str(e)})


@_register("GET", "/api/anchor-tasks/")
def handle_anchor_tasks_list(handler, path: str):
    if path.rstrip("/") == "/api/anchor-tasks":
        return json_response(handler, 200, handler.app.anchor_store.list())
    # GET /api/anchor-tasks/<id>
    task_id = unquote(path.strip("/").split("/")[2])
    json_response(handler, 200, handler.app.anchor_store.get(task_id))


@_register("POST", "/api/anchor-tasks")
def handle_anchor_task_save(handler, path: str):
    # Check for recover sub-action: POST /api/anchor-tasks/<id>/recover
    parts = path.strip("/").split("/")
    if len(parts) >= 4 and parts[3] == "recover":
        task_id = unquote(parts[2])
        try:
            return json_response(handler, 201, handler.app.anchor_store.recover(task_id))
        except (FileNotFoundError, ValueError) as e:
            return json_response(handler, 400, {"error": str(e)})
    # Normal save
    json_response(handler, 201, handler.app.anchor_store.save(read_json(handler)))


@_register("GET", "/api/anchor-tasks/orphaned")
def handle_anchor_tasks_orphaned(handler, path: str):
    json_response(handler, 200, handler.app.anchor_store.list_orphaned())


@_register("DELETE", "/api/anchor-tasks/")
def handle_anchor_task_delete(handler, path: str):
    task_id = unquote(path.strip("/").split("/")[2])
    handler.app.anchor_store.delete(task_id)
    handler.send_response(204)
    handler.end_headers()


@_register("POST", "/api/anchor-prompt-preview")
def handle_anchor_prompt_preview(handler, path: str):
    task = AnchorTask.from_dict(read_json(handler))
    prompt, references = build_anchor_prompt(task)
    json_response(handler, 200, {"prompt": prompt, "references": references})


@_register("GET", "/api/anchor-runs/")
def handle_anchor_runs_get(handler, path: str):
    if path.rstrip("/") == "/api/anchor-runs":
        return json_response(handler, 200, handler.app.anchor_jobs.list())
    # /api/anchor-runs/<run_id>/<action>...
    parts = path.strip("/").split("/")
    run_id = parts[2]
    if len(parts) == 3:
        return json_response(handler, 200, handler.app.anchor_jobs.get(run_id))
    job = handler.app.anchor_jobs.get(run_id)
    manifest_path = _resolve_anchor_manifest(handler, job, run_id)
    manifest = json.loads(manifest_path.read_text())
    action = parts[3]
    if action == "manifest":
        _, state = handler.app.review_state(manifest_path)
        manifest["review_state"] = state
        return json_response(handler, 200, manifest)
    if action in {"media", "download"} and len(parts) == 5:
        candidate = find_candidate(manifest, unquote(parts[4]))
        source = Path(candidate["file"]).resolve()
        generated_root = handler.app.anchor_store.generated_dir(job["task_id"], run_id).resolve()
        if generated_root not in source.parents:
            raise ValueError("candidate file is outside the anchor run")
        download_name = f"{safe_name(job['task_name'])}_{candidate['id']}.jpg" if action == "download" else None
        content_type = "image/jpeg"
        return serve_file(handler, source, content_type, download_name)
    handler.send_error(404)


@_register("POST", "/api/anchor-runs/")
def handle_anchor_runs_post(handler, path: str):
    if path.rstrip("/") == "/api/anchor-runs":
        data = read_json(handler)
        supplied = str(data.pop("password", ""))
        if not handler.app.config.verify_submit_password(supplied):
            return json_response(handler, 403, {"error": "提交密码错误或未配置（请用 scripts/gen_password.py 生成并写入 .env）"})
        return json_response(handler, 202, handler.app.anchor_jobs.submit(data["task_id"], data.get("candidates")))
    # /api/anchor-runs/<run_id>/<action>
    parts = path.strip("/").split("/")
    run_id, action = parts[2], parts[3]
    if action == "resume":
        try:
            handler.app.anchor_jobs._resume_from_state(run_id)
            return json_response(handler, 200, {"ok": True})
        except Exception as exc:
            return json_response(handler, 400, {"error": str(exc)})
    data = read_json(handler)
    job = handler.app.anchor_jobs.get(run_id)
    manifest_path = _resolve_anchor_manifest(handler, job, run_id)
    manifest = json.loads(manifest_path.read_text())
    candidate = find_candidate(manifest, data["id"])
    state_path, state = handler.app.review_state(manifest_path)
    if action == "promote":
        source = Path(candidate["file"]).resolve()
        data_dir = job["task_id"]  # anchor task_id is the data_dir
        # 设为 Anchor 的图直接落到 anchors/ 根目录，与上传的 anchor 图同目录
        anchors_dir = handler.app.anchor_store.task_dir(data_dir)
        anchors_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_name(job['task_name'])}_{safe_name(run_id)}_{candidate['candidate']:02d}.jpg"
        destination = anchors_dir / filename
        if not destination.exists():
            temporary = destination.with_suffix(".tmp")
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        # Relative path from the data directory root, so video tasks can
        # reference it as ``anchors/<filename>``.
        data_root = handler.app.anchor_store.data_root_dir(data_dir)
        relative = destination.relative_to(data_root).as_posix()
        with handler.app.review_lock:
            state["published"][data["id"]] = {"filename": filename, "file": relative}
            handler.app.save_review_state(state_path, state)
        return json_response(handler, 200, state["published"][data["id"]])
    if action == "unpromote":
        with handler.app.review_lock:
            published = state["published"].pop(data["id"], None)
            handler.app.save_review_state(state_path, state)
        # 删除已复制到 anchors/ 的图片文件
        if published and published.get("file"):
            relative = published["file"]
            # 检查是否被视频任务引用，避免误删正在使用的 Anchor 图
            for task in handler.app.store.list():
                if any(a.get("file") == relative for a in (task.get("anchors") or [])):
                    return json_response(handler, 409, {"error": f"该图片正被视频任务「{task.get('name', task.get('id'))}」引用，无法取消 Anchor"})
            data_root = handler.app.anchor_store.data_root_dir(job["task_id"])
            target = (data_root / relative).resolve()
            if target.exists() and target.is_file():
                target.unlink()
        return json_response(handler, 200, {"ok": True})
    handler.send_error(404)


# ── Handlers: Task ───────────────────────────────────────────────────────────

@_register("GET", "/api/tasks/")
def handle_tasks_get(handler, path: str):
    if path.rstrip("/") == "/api/tasks":
        return json_response(handler, 200, handler.app.store.list())
    parts = path.strip("/").split("/")
    task_id = unquote(parts[2])
    if len(parts) == 4 and parts[3] == "assets":
        return json_response(handler, 200, _task_assets(handler, task_id))
    if len(parts) == 4 and parts[3] == "lyrics-timestamps":
        return _get_lyrics_timestamps(handler, task_id)
    if len(parts) == 4 and parts[3] == "missing-assets":
        return json_response(handler, 200, _missing_assets(handler, task_id))
    json_response(handler, 200, handler.app.store.get(task_id))


@_register("POST", "/api/tasks")
def handle_tasks_post(handler, path: str):
    full = urlparse(handler.path)
    parts = full.path.strip("/").split("/")
    if len(parts) == 4 and parts[3] == "clear-assets":
        task_id = unquote(parts[2])
        category = parse_qs(full.query).get("category", [None])[0]
        removed = handler.app.store.clear_assets(task_id, category=category)
        return json_response(handler, 200, {"ok": True, "removed": removed})
    if len(parts) == 4 and parts[3] == "extract-audio":
        task_id = unquote(parts[2])
        return _extract_task_audio(handler, task_id)
    if len(parts) == 4 and parts[3] == "lyrics-timestamps":
        task_id = unquote(parts[2])
        return _save_lyrics_timestamps(handler, task_id)
    data = read_json(handler)
    json_response(handler, 201, handler.app.store.save(data))


@_register("DELETE", "/api/tasks/")
def handle_tasks_delete(handler, path: str):
    full = urlparse(handler.path)
    task_id = unquote(full.path.strip("/").split("/")[2])
    remove_files = parse_qs(full.query).get("remove_files", ["0"])[0] == "1"
    try:
        handler.app.store.delete(task_id)
        if remove_files:
            # Cascade: delete all runs associated with this task + their output dirs
            data_dir = task_id.split("__")[0] if "__" in task_id else task_id
            for run_id, job in list(handler.app.jobs.jobs.items()):
                if job.get("task_id") == task_id:
                    try:
                        handler.app.jobs.delete(run_id, remove_files=True)
                    except KeyError:
                        pass
        handler.send_response(204)
        handler.end_headers()
    except KeyError:
        json_response(handler, 404, {"error": f"task not found: {task_id}"})


@_register("POST", "/api/prompt-preview")
def handle_prompt_preview(handler, path: str):
    data = read_json(handler)
    # 自定义 prompt：用户在预览框手动编辑后，前端会带上 custom_prompt，直接回显
    custom_prompt = str(data.get("custom_prompt", "")).strip()
    if custom_prompt:
        json_response(handler, 200, {"prompt": custom_prompt, "custom": True})
        return
    references = data.get("references", [])
    has_audio = any(ref.get("pass_reference_audio", True) for ref in references)
    has_video = any(ref.get("pass_reference_video", True) for ref in references)
    camera_policy = data.get("camera_policy")
    json_response(handler, 200, {"prompt": build_prompt(data["mode"], data.get("lyrics", ""), data.get("constraints", ""), has_audio_ref=has_audio, has_video_ref=has_video, camera_policy=camera_policy, lyrics_timestamps=data.get("lyrics_timestamps")), "custom": False})


def _file_fingerprint(path: Path) -> dict | None:
    """与 runner._fingerprint 一致的源文件指纹；文件不存在返回 None。"""
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _task_assets(handler, task_id: str) -> dict:
    """返回每个素材的 Planner Decision。

    使用 AssetPlanner 作为唯一决策引擎，与 Runner 判定一致，
    避免"UI 显示复用、Runner 实际失败"的不一致。设计见 docs/guides/Asset_Design.md。
    """
    task = handler.app.store.get(task_id)
    # skip_material_check=True：面板需展示"素材缺失"状态，不能因缺失而抛错
    adapter = adapter_from_task(task, handler.app.config, handler.app.store, skip_material_check=True)
    path = adapter.assets_file
    assets = json.loads(path.read_text()) if path.is_file() else {}
    # plan 不需要 client（仅 upload 需要），传 None 即可
    runner = VideoTaskRunner(adapter, client=None, progress=lambda **_: None)
    decisions = runner._plan_all(assets)
    # anchor 别名复用（跨文件夹迁移/换位）：仅展示层面落账到名义 key，不写盘
    runner._adopt_anchor_aliases(assets, persist=False)
    items = []
    for d in decisions:
        # asset_id 仅在「存在有效资产（可复用）」时返回；资产缺失/需重传时返回空，
        # 避免旧 asset id 残留导致 UI 显示"已上传"却实际要重建/重传的困惑
        valid_asset = d.asset_state == ASSET_AVAILABLE and assets.get(d.asset_key)
        items.append({
            "key": d.asset_key,
            "asset_id": assets.get(d.asset_key) if valid_asset else None,
            "material_id": d.material_id,
            "action": d.action,
            "reason": d.reason,
            "source_state": d.source_state,
            "artifact_state": d.artifact_state,
            "asset_state": d.asset_state,
            "visibility_state": d.visibility_state,
            "can_submit": d.can_submit,
            "requires_source": d.requires_source,
            "block_reason": d.block_reason,
            "current_transform": d.current_transform,
            "cached_transform": d.cached_transform,
            "preview_url": d.preview_url,
        })
    return {"task_id": task_id, "path": str(path), "items": items}


def _missing_assets(handler, task_id: str) -> dict:
    """Return which referenced files (anchors/references) no longer exist on disk."""
    task = handler.app.store.get(task_id)
    task_dir = handler.app.store.task_dir(task.get("data_dir", ""), task.get("task_dir"))
    missing_anchors = []
    missing_references = []
    for idx, item in enumerate(task.get("anchors") or []):
        file = str(item.get("file", ""))
        if not file:
            continue
        try:
            handler.app.store._asset_path(task_dir, file)
        except ValueError:
            missing_anchors.append({"index": idx, "file": file})
    for idx, item in enumerate(task.get("references") or []):
        file = str(item.get("file", ""))
        if not file:
            continue
        try:
            handler.app.store._asset_path(task_dir, file)
        except ValueError:
            missing_references.append({"index": idx, "file": file})
    return {"task_id": task_id, "missing_anchors": missing_anchors, "missing_references": missing_references}


@_register("POST", "/api/uploads")
def handle_upload(handler, path: str):
    task_id = unquote(handler.headers.get("X-Task-Id", "")).strip()
    filename = Path(unquote(handler.headers.get("X-Filename", ""))).name
    category = handler.headers.get("X-Category", "references")
    if not task_id or not filename or category not in {"anchors", "references", "anchor-references"}:
        raise ValueError("task, filename and valid category are required")
    # Anchor references live under <data_dir>/anchors/anchor-references/, not <data_dir>/ directly.
    # Anchor 图片（视频任务素材）统一落到 anchors/ 根目录，与「设为 Anchor」的图同目录。
    subdir = "anchors/anchor-references" if category == "anchor-references" else category
    root = handler.app.config.resolve_inside("upload_root", task_id)
    destination = (root / subdir / filename).resolve()
    if root not in destination.parents:
        raise ValueError("invalid upload path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{filename}.{uuid.uuid4().hex}.upload")
    remaining = int(handler.headers.get("Content-Length", 0))
    with temporary.open("wb") as output:
        while remaining:
            chunk = handler.rfile.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("upload ended early")
            output.write(chunk)
            remaining -= len(chunk)
    temporary.replace(destination)
    # Return the path relative to the data_dir, prefixed with ``anchors/`` for
    # anchor-references so AnchorTaskStore can resolve them correctly.
    relative = destination.relative_to(root).as_posix()
    json_response(handler, 201, {"file": relative, "size": destination.stat().st_size})


def _migrate_reusable_asset_entries(src: Path, src_rel: str, dest: Path, dst_assets_path: Path, config) -> list[str]:
    """跨文件夹复制素材时，把源文件夹 assets.json 里「上传产物就是这份文件」的
    条目迁移到目标文件夹（当前实际命中的是 anchor 条目：它没有独立产物层，
    __source 指纹即源文件指纹；copy2 保留 size+mtime_ns，指纹校验天然成立）。
    segment/audio 条目的 __source 是 runtime/work 产物指纹，不会命中源文件。
    目标已有同名键不覆盖（可能绑定着目标文件夹自己的素材状态）；键名保持源任务
    的位置键，本任务提交时由 runner 按内容指纹认领（_adopt_anchor_aliases）。
    返回迁移的键列表（可为空）。"""
    if "/" not in src_rel:
        return []
    src_dir = config.resolve_inside("data_root", src_rel.split("/")[0])
    src_assets_path = src_dir / "seedance" / "assets.json"
    if not src_assets_path.is_file():
        return []
    try:
        src_assets = json.loads(src_assets_path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    stat = src.stat()
    matches = []
    for key in src_assets:
        if key.endswith("__source") or key.endswith("__transform"):
            continue
        fp = src_assets.get(f"{key}__source")
        if not isinstance(fp, dict):
            continue
        # runtime/work 产物条目（segment/audio）的指纹属于产物文件，不属于被复制的
        # 源素材——即使指纹碰巧相等也不迁移，复用必须可证明内容一致
        if "/runtime/work/" in str(fp.get("path", "")).replace("\\", "/"):
            continue
        if fp.get("size") == stat.st_size and fp.get("mtime_ns") == stat.st_mtime_ns:
            matches.append(key)
    if not matches:
        return []
    dst_assets = {}
    if dst_assets_path.is_file():
        try:
            dst_assets = json.loads(dst_assets_path.read_text())
        except (OSError, json.JSONDecodeError):
            dst_assets = {}
    migrated = []
    for key in matches:
        if key in dst_assets or not src_assets.get(key):
            continue
        dst_assets[key] = src_assets[key]
        new_fp = dict(src_assets.get(f"{key}__source") or {})
        new_fp["path"] = str(dest.resolve())
        dst_assets[f"{key}__source"] = new_fp
        transform = src_assets.get(f"{key}__transform")
        if transform is not None:
            dst_assets[f"{key}__transform"] = transform
        migrated.append(key)
    if migrated:
        dst_assets_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = dst_assets_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(dst_assets, indent=2, ensure_ascii=False))
        temporary.replace(dst_assets_path)
    return migrated


@_register("POST", "/api/files/copy")
def handle_copy_file(handler, path: str):
    """把 data_root 内已有文件复制到指定任务文件夹的类别目录。

    素材弹窗允许浏览到其他任务文件夹，跨文件夹勾选的文件在确认时通过此接口
    复制进当前任务目录（等价于本机上传），保证任务引用的文件始终在本文件夹内。
    源文件保持不动（隔离不动别人），目标同名时默认 409，客户端确认后 overwrite 重试。
    """
    data = read_json(handler)
    src_rel = str(data.get("src", "")).strip()
    task_id = str(data.get("task_id", "")).strip()
    category = data.get("category", "references")
    overwrite = bool(data.get("overwrite"))
    if not src_rel or not task_id or category not in {"anchors", "references", "anchor-references"}:
        raise ValueError("src, task_id and valid category are required")
    src = handler.app.config.resolve_inside("data_root", src_rel)
    if not src.is_file():
        raise FileNotFoundError(src_rel)
    # 目标目录规则与 /api/uploads 完全一致
    subdir = "anchors/anchor-references" if category == "anchor-references" else category
    root = handler.app.config.resolve_inside("upload_root", task_id)
    destination = (root / subdir / src.name).resolve()
    if root not in destination.parents:
        raise ValueError("invalid copy destination")
    if destination.exists() and not overwrite:
        json_response(handler, 409, {"error": f"目标目录已有同名文件: {src.name}", "file": src.name})
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, destination)
    # 复制后迁移可复用的 asset 缓存条目（anchor：指纹即源文件，copy2 保留指纹）
    migrated = _migrate_reusable_asset_entries(
        src, src_rel, destination, root / "seedance" / "assets.json", handler.app.config
    )
    relative = destination.relative_to(root).as_posix()
    json_response(handler, 201, {"file": relative, "size": destination.stat().st_size, "migrated": migrated})


# ── Handlers: Run (Video) ────────────────────────────────────────────────────

@_register("GET", "/api/runs/")
def handle_runs_get(handler, path: str):
    if path.rstrip("/") == "/api/runs":
        return json_response(handler, 200, handler.app.jobs.list())
    parts = path.strip("/").split("/")
    run_id = parts[2]
    if len(parts) == 3:
        return json_response(handler, 200, handler.app.jobs.get(run_id))
    action = parts[3]
    if action == "manifest":
        manifest_path, manifest = handler.app.manifest(run_id)
        _, state = handler.app.review_state(manifest_path)
        manifest["review_state"] = state
        return json_response(handler, 200, manifest)
    if action in {"media", "download"} and len(parts) == 5:
        return _candidate_file(handler, run_id, unquote(parts[4]), action == "download")
    if action == "publish-status":
        return json_response(handler, 200, handler.app.publish_progress.get(run_id, {"running": False, "step": "idle", "message": "尚未发布"}))
    if action == "intermediate":
        return _get_intermediate_for_run(handler, run_id)
    handler.send_error(404)


@_register("DELETE", "/api/runs/")
def handle_runs_delete(handler, path: str):
    full = urlparse(handler.path)
    run_id = unquote(full.path.strip("/").split("/")[2])
    remove_files = parse_qs(full.query).get("remove_files", ["0"])[0] == "1"
    try:
        handler.app.jobs.delete(run_id, remove_files=remove_files)
        handler.send_response(204)
        handler.end_headers()
    except KeyError:
        json_response(handler, 404, {"error": f"run not found: {run_id}"})


@_register("POST", "/api/runs/")
def handle_runs_post(handler, path: str):
    if path.rstrip("/") == "/api/runs":
        data = read_json(handler)
        supplied = str(data.pop("password", ""))
        if not handler.app.config.verify_submit_password(supplied):
            return json_response(handler, 403, {"error": "提交密码错误或未配置（请用 scripts/gen_password.py 生成并写入 .env）"})
        return json_response(handler, 202, handler.app.jobs.submit(data["task_id"], data.get("candidates")))
    # /api/runs/<run_id>/<action>
    parts = path.strip("/").split("/")
    if len(parts) < 4:
        return json_response(handler, 400, {"error": "missing action"})
    run_id, action = parts[2], parts[3]
    if action == "resume":
        try:
            handler.app.jobs._resume_from_state(run_id)
            return json_response(handler, 200, {"ok": True})
        except Exception as exc:
            return json_response(handler, 400, {"error": str(exc)})
    data = read_json(handler)
    manifest_path, manifest = handler.app.manifest(run_id)
    if action == "vote":
        find_candidate(manifest, data["id"])
        with handler.app.review_lock:
            state_path, state = handler.app.review_state(manifest_path)
            state["votes"][data["id"]] = data["vote"]
            handler.app.save_review_state(state_path, state)
        return json_response(handler, 200, {"ok": True})
    if action == "publish":
        if not handler.app.config.publish_enabled:
            return json_response(handler, 403, {"error": "当前机器未启用 Git 发布，请直接下载候选视频"})
        return _start_publish(handler, run_id, manifest_path, manifest, data["id"])
    handler.send_error(404)


def _candidate_file(handler, run_id: str, candidate_id: str, download: bool) -> None:
    manifest_path, manifest = handler.app.manifest(run_id)
    candidate = find_candidate(manifest, candidate_id)
    source = Path(candidate.get("file", "")).resolve() if candidate.get("file") else (manifest_path.parents[2] / candidate["path"]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    # 下载文件名带上「数据目录__任务名」，方便区分不同目录下同名任务的候选
    # manifest["task"] 即 adapter.name = store.get 返回的 composite id（如「曾曾__跳舞」），已含数据目录
    filename = "_".join((
        safe_filename(manifest.get("task", "")), safe_filename(candidate["anchor"]),
        safe_filename(candidate["reference"]), safe_filename(candidate["variant"]),
        f"candidate-{int(candidate['candidate']):02d}.mp4",
    ))
    serve_file(handler, source, "video/mp4", filename if download else None)


def _start_publish(handler, run_id: str, manifest_path: Path, manifest: dict, candidate_id: str) -> None:
    progress = handler.app.publish_progress.setdefault(run_id, {"running": False})
    if progress.get("running"):
        return json_response(handler, 409, progress)
    candidate = find_candidate(manifest, candidate_id)
    progress.update(running=True, step="starting", message="准备发布", error="")

    def update(step, message):
        progress.update(step=step, message=message)

    def work():
        try:
            publish = manifest["publish"]
            publisher = Publisher(Path(publish["repo"]), publish["subdirectory"], publish["filename_prefix"], update)
            source = Path(candidate.get("file", "")).resolve() if candidate.get("file") else manifest_path.parents[2] / candidate["path"]
            result = publisher.publish(source, candidate)
            with handler.app.review_lock:
                state_path, state = handler.app.review_state(manifest_path)
                state["published"][candidate_id] = result
                handler.app.save_review_state(state_path, state)
            progress.update(running=False, step="done", message=f"发布成功：{result['filename']}", result=result)
        except Exception as exc:
            progress.update(running=False, step="failed", message="发布失败", error=str(exc))

    threading.Thread(target=work, daemon=True).start()
    json_response(handler, 202, progress)


@_register("DELETE", "/api/anchor-runs/")
def handle_anchor_runs_delete(handler, path: str):
    full = urlparse(handler.path)
    parts = full.path.strip("/").split("/")
    if len(parts) != 3:
        handler.send_error(400)
        return
    run_id = parts[2]
    remove_files = parse_qs(full.query).get("remove_files", ["0"])[0] == "1"
    try:
        handler.app.anchor_jobs.delete(run_id, remove_files=remove_files)
        json_response(handler, 200, {"ok": True})
    except KeyError:
        json_response(handler, 404, {"error": f"anchor run not found: {run_id}"})


# ── Error handling helpers ───────────────────────────────────────────────────

def handle_error(handler, exc: Exception) -> bool:
    """Centralized error-to-response mapping. Returns True if handled."""
    if isinstance(exc, (KeyError, FileNotFoundError)):
        json_response(handler, 404, {"error": str(exc)})
        return True
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        json_response(handler, 400, {"error": str(exc)})
        return True
    import logging
    logging.getLogger("web").error("Unhandled %s %s: %s", handler.command, handler.path, exc, exc_info=True)
    return False


def _resolve_anchor_manifest(handler, job: dict, run_id: str) -> Path:
    """Resolve anchor manifest path, fixing stale paths from pre-refactor era."""
    manifest_path = Path(job.get("manifest", ""))
    if not manifest_path.is_file():
        task_id = job.get("task_id", "")
        if task_id:
            fallback = handler.app.anchor_store.generated_dir(task_id, run_id) / "review_manifest.json"
            if fallback.is_file():
                manifest_path = fallback
                # Update stale path in job record
                with handler.app.anchor_jobs.lock:
                    if run_id in handler.app.anchor_jobs.jobs:
                        handler.app.anchor_jobs.jobs[run_id]["manifest"] = str(fallback)
                        handler.app.anchor_jobs._save(handler.app.anchor_jobs.jobs[run_id])
    if not manifest_path.is_file():
        raise FileNotFoundError("anchor manifest is not available")
    return manifest_path
