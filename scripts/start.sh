#!/usr/bin/env bash
# IdolFlow Studio - 前台启动（按 Ctrl+C 停止）

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 检查 .env 文件
if [[ ! -f .env ]]; then
  echo "❌ 错误: .env 文件不存在" >&2
  echo "" >&2
  echo "请先配置:" >&2
  echo "  1. cp .env.example .env" >&2
  echo "  2. 编辑 .env 填写必需的配置" >&2
  exit 1
fi

# 加载环境变量
set -a
. "$ROOT/.env"
set +a

# 验证必需的环境变量
missing=()
for var in SEEDANCE_API_KEY ASSET_GROUP_ID VIDEO_SUBMIT_HASH; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done

if (( ${#missing[@]} )); then
  echo "❌ 错误: .env 缺少必需的配置: ${missing[*]}" >&2
  exit 1
fi

# 确保 ffmpeg 可被发现（兼容 Intel / Apple Silicon Homebrew 路径）
for _bindir in /usr/local/bin /opt/homebrew/bin; do
  if [[ -d "$_bindir" && ":${PATH:-}:" != *":$_bindir:"* ]]; then
    export PATH="$_bindir:$PATH"
  fi
done
unset _bindir

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "❌ 错误: 未找到 ffmpeg，请先安装" >&2
  echo "   macOS: brew install ffmpeg" >&2
  echo "   Ubuntu/Debian: sudo apt install ffmpeg" >&2
  exit 1
fi

# 设置项目变量
export VIDEO_PROJECT_ROOT="$ROOT"
export VIDEO_WORKSPACE_CONFIG="$ROOT/video-workspace.json"

echo "🚀 启动 IdolFlow Studio..."
echo ""

# 前台运行
exec python3 "$ROOT/run.py" video web --config "$ROOT/video-workspace.json" "$@"
