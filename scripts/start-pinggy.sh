#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PORT="${1:-8913}"

# 读取 .env 里的 PINGGY_TOKEN（用于固定 URL；缺失时提示，因为匿名模式不可用）
TOKEN=""
if [[ -f "$ROOT/.env" ]]; then
  TOKEN="$(grep -E '^PINGGY_TOKEN=' "$ROOT/.env" | head -1 | cut -d= -f2 | tr -d ' \r')"
fi

if [[ -z "$TOKEN" ]]; then
  echo "❌ 错误: 未配置 PINGGY_TOKEN（在 .env 中设置）" >&2
  echo "   匿名模式不可用，需带 token 才能建立隧道。" >&2
  exit 1
fi

ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -p 443 -R0:127.0.0.1:"$PORT" "${TOKEN}@a.pinggy.io"
