#!/usr/bin/env bash
# IdolFlow Studio - 停止服务

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/workspace.pid"

echo "🛑 停止 IdolFlow Studio..."
echo ""

stopped=false

# 方法 1: 使用保存的 PID
if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "✅ 服务已停止 (PID: $PID)"
    rm -f "$PID_FILE"
    stopped=true
  else
    rm -f "$PID_FILE"
  fi
fi

# 方法 2: 查找并停止运行中的进程
if [[ "$stopped" == "false" ]]; then
  if pkill -f "run.py video web"; then
    echo "✅ 服务已停止"
    rm -f "$PID_FILE"
    stopped=true
  fi
fi

if [[ "$stopped" == "false" ]]; then
  echo "ℹ️  没有找到运行中的服务"
fi

echo ""
