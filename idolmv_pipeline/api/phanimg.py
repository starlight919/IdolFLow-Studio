"""PhanRouter (PhanImg) API client — GPT-Image-2 generation."""
from __future__ import annotations

import base64
import logging
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

logger = logging.getLogger("phanimg")


class PhanImgClient:
    """Client for PhanRouter Image API (gpt-image-2)."""

    def __init__(self, api_root: str, api_key: str, model: str = "gpt-image-2") -> None:
        self._root = api_root.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        self.model = model
        self._poll_interval = 5
        self._poll_timeout = 900

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def image_to_b64(img: Image.Image, quality: int = 85) -> str:
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def resize_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        img = img.convert("RGB")
        sw, sh = img.size
        target_ratio = target_w / target_h
        source_ratio = sw / sh
        if source_ratio > target_ratio:
            nw = int(sh * target_ratio)
            left = (sw - nw) // 2
            img = img.crop((left, 0, left + nw, sh))
        elif source_ratio < target_ratio:
            nh = int(sw / target_ratio)
            top = (sh - nh) // 2
            img = img.crop((0, top, sw, top + nh))
        return img.resize((target_w, target_h), Image.LANCZOS)

    # ── Task management ────────────────────────────────────────

    def _create_task(self, payload: dict) -> str:
        url = f"{self._root}/v3/images/generations"
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("task_id") or data.get("taskId")
        if not task_id:
            raise RuntimeError(f"Task creation failed: {data}")
        logger.info("Task created: %s", task_id)
        return task_id

    def _poll_task(self, task_id: str) -> Image.Image:
        url = f"{self._root}/v3/images/generations/{task_id}"
        deadline = time.monotonic() + self._poll_timeout
        while time.monotonic() < deadline:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            result = resp.json()
            data = result.get("data") if isinstance(result.get("data"), dict) else result
            status = str(data.get("status", "")).lower() if data else ""
            if status == "succeeded":
                img_url = data.get("url", "")
                if not img_url:
                    raise RuntimeError(f"Task {task_id} succeeded but no url: {data}")
                img_resp = self._session.get(img_url, timeout=60)
                img_resp.raise_for_status()
                return Image.open(BytesIO(img_resp.content)).convert("RGB")
            if status == "failed":
                err = data.get("error") or {}
                raise RuntimeError(f"Task {task_id} failed: {err}")
            logger.info("Task %s status=%s, waiting…", task_id, status)
            time.sleep(self._poll_interval)
        raise TimeoutError(f"Task {task_id} timed out after {self._poll_timeout}s")

    def _run_with_retry(self, payload: dict, max_retries: int = 3) -> Image.Image:
        for attempt in range(max_retries):
            try:
                task_id = self._create_task(payload)
                return self._poll_task(task_id)
            except RuntimeError as e:
                if attempt < max_retries - 1:
                    wait = 10 * (attempt + 1)
                    logger.warning("Attempt %d/%d failed: %s — retrying in %ds", attempt + 1, max_retries, e, wait)
                    time.sleep(wait)
                else:
                    raise

    # ── Public API ───────────────────────────────────────────

    def create_task(
        self,
        prompt: str,
        references: list[Path] | None = None,
        size: str = "1024x1792",
        resolution: str = "2K",
    ) -> str:
        references = references or []
        if len(references) > 16:
            raise ValueError("gpt-image-2 accepts at most 16 reference images")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "resolution": resolution,
        }
        if references:
            encoded = []
            for path in references:
                with Image.open(path) as image:
                    encoded.append(self.image_to_b64(image))
            payload["base64File"] = encoded[0] if len(encoded) == 1 else None
            if len(encoded) > 1:
                payload.pop("base64File")
                payload["base64FileList"] = encoded
        return self._create_task(payload)

    def task(self, task_id: str) -> dict:
        response = self._session.get(f"{self._root}/v3/images/generations/{task_id}", timeout=15)
        response.raise_for_status()
        result = response.json()
        return result.get("data") if isinstance(result.get("data"), dict) else result

    def poll_to_file(self, task_id: str, destination: Path) -> Path:
        deadline = time.monotonic() + self._poll_timeout
        while time.monotonic() < deadline:
            data = self.task(task_id)
            status = str(data.get("status", "")).lower()
            if status == "succeeded":
                url = data.get("url", "")
                if not url:
                    raise RuntimeError(f"Task {task_id} succeeded but no url: {data}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".download")
                with self._session.get(url, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as output:
                        for chunk in response.iter_content(1024 * 1024):
                            if chunk:
                                output.write(chunk)
                with Image.open(temporary) as image:
                    normalized = image.convert("RGB")
                    normalized.save(destination, format="JPEG", quality=95)
                temporary.unlink(missing_ok=True)
                return destination
            if status == "failed":
                raise RuntimeError(f"Task {task_id} failed: {data.get('error') or data}")
            time.sleep(self._poll_interval)
        raise TimeoutError(f"Task {task_id} timed out after {self._poll_timeout}s")

    def generate(
        self,
        prompt: str,
        destination: Path,
        references: list[Path] | None = None,
        size: str = "1024x1792",
        resolution: str = "2K",
    ) -> tuple[str, Path]:
        task_id = self.create_task(prompt, references, size, resolution)
        return task_id, self.poll_to_file(task_id, destination)

    def image_to_image(
        self,
        reference: Image.Image,
        prompt: str,
        size: str = "1792x1024",
    ) -> Image.Image:
        """Generate image from reference image + prompt."""
        b64 = self.image_to_b64(reference)
        return self._run_with_retry({
            "model": self.model,
            "prompt": prompt,
            "base64File": b64,
            "size": size,
        })
