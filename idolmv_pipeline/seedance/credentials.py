"""Credentials for local Seedance workflows.

Environment variables override the local defaults so keys remain centralized and
never need to be copied into task adapters.
"""
from __future__ import annotations

import os

API_BASE = os.getenv("SEEDANCE_API_BASE", "")
# 密钥一律从环境变量（.env）读取，不在代码中硬编码。
# 缺少时抛错，避免使用占位/过期密钥静默运行。
SD20_KEY = os.getenv("SEEDANCE_API_KEY", "")
SD25_KEY = os.getenv("SEEDANCE_SD25_API_KEY", "")
ASSET_GROUP_ID = os.getenv("ASSET_GROUP_ID", "")
PINGGY_TOKEN = os.getenv("PINGGY_TOKEN", "")
NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")
