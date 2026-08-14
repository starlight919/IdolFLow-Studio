"""API configuration used by the portable video workspace."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(os.getenv("VIDEO_PROJECT_ROOT", Path(__file__).resolve().parents[2])).resolve()

ASSET_GROUP_ID: str = os.getenv("ASSET_GROUP_ID", "")

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

DEFAULT_SAMPLE_RATE = 16000
LRC_TOLERANCE = 2.0

GPT_IMAGE_API_ROOT = os.getenv("SEEDANCE_API_BASE", "")
GPT_IMAGE_API_KEY = os.getenv("SEEDANCE_API_KEY", "")
GPT_IMAGE_MODEL = "gpt-image-2"
