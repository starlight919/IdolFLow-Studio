#!/usr/bin/env bash
# IdolFlow Studio - 查看状态

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$ROOT/workspace.log"

echo "================================================"
echo "  IdolFlow Studio - 服务状态"
echo "================================================"
echo ""

# 检查服务是否运行
if pgrep -f "run.py video web" > /dev/null; then
  PID=$(pgrep -f "run.py video web")
  
  echo "✅ 状态: 运行中"
  echo "🆔 进程 ID: $PID"
  echo ""
  
  # 显示进程信息
  if command -v ps > /dev/null; then
    echo "📈 进程信息:"
    ps -p "$PID" -o pid,ppid,%cpu,%mem,etime,command 2>/dev/null || true
    echo ""
  fi
  
  # 显示最近日志
  if [[ -f "$LOG_FILE" ]]; then
    echo "📝 最近日志 (最后 5 行):"
    echo "--------------------------------"
    tail -n 5 "$LOG_FILE" 2>/dev/null || echo "  (无日志)"
    echo "--------------------------------"
    echo ""
  fi
  
  echo "📍 访问地址: http://127.0.0.1:8913/"
  echo ""
  echo "常用命令:"
  echo "  bash scripts/stop.sh              # 停止服务"
  echo "  tail -f $LOG_FILE      # 实时查看日志"
  
else
  echo "❌ 状态: 未运行"
  echo ""
  echo "启动服务:"
  echo "  bash scripts/start.sh             # 前台运行"
  echo "  bash scripts/start-daemon.sh      # 后台运行"
fi

echo ""
echo "================================================"
