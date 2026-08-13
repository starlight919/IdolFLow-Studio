from __future__ import annotations

import time
from pathlib import Path

import requests

from idolmv_pipeline.seedance.credentials import API_BASE, ASSET_GROUP_ID, SD20_KEY, SD25_KEY


class SeedanceError(RuntimeError):
    pass


def _select_api_key(model: str | None = None) -> str:
    if model and "sd2.5" in model:
        key = SD25_KEY
    else:
        key = SD20_KEY
    if not key:
        raise SeedanceError("Missing API key: set SEEDANCE_API_KEY / SEEDANCE_SD25_API_KEY in .env")
    return key


class SeedanceClient:
    def __init__(self, poll_interval: int = 15, model: str | None = None):
        self.poll_interval = poll_interval
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {_select_api_key(model)}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _json(response: requests.Response) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            raise SeedanceError(f"API returned non-JSON HTTP {response.status_code}") from exc

    def create_asset(self, name: str, url: str, asset_type: str) -> str:
        for suffix in ("", f"_{int(time.time())}"):
            response = requests.post(
                f"{API_BASE}/open/CreateAsset",
                json={"GroupId": ASSET_GROUP_ID, "Name": f"{name}{suffix}", "URL": url, "AssetType": asset_type},
                headers=self.headers,
                timeout=180,
            )
            data = self._json(response)
            asset_id = data.get("Result", {}).get("Id", "")
            if asset_id:
                time.sleep(12)
                return asset_id
            error = data.get("ResponseMetadata", {}).get("Error", {})
            if "already exists" in error.get("Message", "").lower() and not suffix:
                continue
            raise SeedanceError(f"CreateAsset failed for {name}: {error or data}")
        raise SeedanceError(f"CreateAsset failed for {name}")

    def submit(self, payload: dict) -> str:
        last_error = None
        for attempt in range(4):
            try:
                response = requests.post(
                    f"{API_BASE}/api/v3/contents/generations/tasks",
                    json=payload,
                    headers=self.headers,
                    timeout=120,
                )
                data = self._json(response)
                inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                task_id = data.get("task_id") or data.get("id") or inner.get("id")
                if task_id:
                    return task_id
                # asset 还在处理中，等待后重试
                error = data.get("error", {})
                if "still processing" in str(error).lower():
                    last_error = data
                    time.sleep(10)
                    continue
                last_error = data
            except requests.RequestException as exc:
                last_error = exc
            if attempt < 3:
                time.sleep(10)
        raise SeedanceError(f"Submit failed: {last_error}")

    def task(self, task_id: str) -> dict:
        response = requests.get(
            f"{API_BASE}/api/v3/contents/generations/tasks/{task_id}",
            headers={"Authorization": f"Bearer {_select_api_key(self.model)}"},
            timeout=30,
        )
        data = self._json(response)
        return data.get("data") if isinstance(data.get("data"), dict) else data

    def poll_and_download(self, task_id: str, destination: Path, max_wait: int = 1800) -> None:
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            data = self.task(task_id)
            status = str(data.get("status", "")).lower()
            if status in {"success", "succeeded"}:
                url = data.get("url")
                if not url:
                    raise SeedanceError(f"Task {task_id} succeeded without output URL")
                with requests.get(url, stream=True, timeout=180) as response:
                    response.raise_for_status()
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_suffix(".download")
                    with temporary.open("wb") as output:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                output.write(chunk)
                    temporary.replace(destination)
                return
            if status == "failed":
                raise SeedanceError(f"Task {task_id} failed: {data.get('error', data)}")
            time.sleep(self.poll_interval)
        raise SeedanceError(f"Task {task_id} timed out after {max_wait}s")
