#!/usr/bin/env bash
# IdolFlow Studio - 后台启动（持久化运行，关闭终端也继续）

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG_FILE="$ROOT/workspace.log"
PID_FILE="$ROOT/workspace.pid"

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

# 检查是否已经在运行
if LC_ALL=C pgrep -f "run.py video web" > /dev/null; then
  echo "⚠️  服务已经在运行中"
  echo ""
  echo "查看状态: bash scripts/status.sh"
  echo "停止服务: bash scripts/stop.sh"
  exit 1
fi

# 设置项目变量
export VIDEO_PROJECT_ROOT="$ROOT"
export VIDEO_WORKSPACE_CONFIG="$ROOT/video-workspace.json"

# 确保 ffmpeg/ffprobe 在 PATH 中（兼容 Intel / Apple Silicon Homebrew 路径）
for _bindir in /usr/local/bin /opt/homebrew/bin; do
  if [[ -d "$_bindir" && ":${PATH:-}:" != *":$_bindir:"* ]]; then
    export PATH="$_bindir:$PATH"
  fi
done
unset _bindir

echo "🚀 启动 IdolFlow Studio (后台模式)..."
echo ""

# 解析端口（优先级：--port 参数 > .env 的 VIDEO_WEB_PORT > 默认 8913）
WEB_PORT="${VIDEO_WEB_PORT:-8913}"
prev=""
for arg in "$@"; do
  case "$arg" in
    --port) prev="--port" ;;
    --port=*) WEB_PORT="${arg#--port=}" ;;
    *) [[ "$prev" == "--port" ]] && WEB_PORT="$arg" ;;
  esac
  prev="$arg"
done

# 后台运行（$@ 保持原样透传给 run.py）
nohup python3 "$ROOT/run.py" video web --config "$ROOT/video-workspace.json" "$@" \
  > "$LOG_FILE" 2>&1 &

# 保存 PID
echo $! > "$PID_FILE"

# 等待启动
sleep 2

# 验证启动成功
if LC_ALL=C pgrep -f "run.py video web" > /dev/null; then
  echo "✅ 服务已启动（后台运行）"
  echo ""
  echo "📍 访问地址: http://127.0.0.1:${WEB_PORT}/"
  echo "📝 日志文件: $LOG_FILE"
  echo ""
  echo "常用命令:"
  echo "  bash scripts/status.sh       # 查看状态"
  echo "  bash scripts/stop.sh         # 停止服务"
  echo "  tail -f $LOG_FILE # 查看日志"
  echo ""
else
  echo "❌ 服务启动失败"
  echo ""
  echo "查看错误: cat $LOG_FILE"
  exit 1
fi
