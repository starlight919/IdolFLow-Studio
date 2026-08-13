#!/usr/bin/env bash
# IdolFlow Studio - 安装依赖

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "================================================"
echo "  IdolFlow Studio - 依赖安装"
echo "================================================"
echo ""

# 检查 Python
echo "📌 检查 Python..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ 错误: 未找到 Python 3" >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("❌ 错误: 需要 Python 3.10 或更高版本")
print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY

echo ""

# 检查系统依赖
echo "📌 检查系统依赖..."
missing=()
for cmd in ffmpeg ffprobe ssh; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    missing+=("$cmd")
  else
    echo "  ✅ $cmd"
  fi
done

if (( ${#missing[@]} )); then
  echo ""
  echo "❌ 缺少系统依赖: ${missing[*]}"
  echo ""
  echo "macOS 安装方法:"
  echo "  brew install ffmpeg openssh"
  echo ""
  echo "Ubuntu/Debian 安装方法:"
  echo "  sudo apt-get install ffmpeg openssh-client"
  exit 1
fi

echo ""

# 安装 Python 依赖
echo "📦 安装 Python 依赖..."

# 国内镜像加速：未设置 PIP_INDEX_URL 且检测到网络较慢时，可改用清华镜像
# 用法：PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash setup.sh
PIP_ARGS=()
if [[ -n "${PIP_INDEX_URL:-}" ]]; then
  echo "  📡 使用镜像源: $PIP_INDEX_URL"
  PIP_ARGS=(-i "$PIP_INDEX_URL")
fi

python3 -m pip install --upgrade pip -q "${PIP_ARGS[@]:-}"
python3 -m pip install -r requirements.txt "${PIP_ARGS[@]:-}"

echo ""

# 创建目录
echo "📁 创建必要目录..."
mkdir -p data runtime/work runtime/outputs runtime/publish
echo "  ✅ 目录已创建"

echo ""
echo "================================================"
echo "  ✅ 安装完成！"
echo "================================================"
echo ""

if [[ ! -f .env ]]; then
  echo "⚠️  下一步: 配置环境变量"
  echo ""
  echo "  1. 复制配置模板:"
  echo "     cp .env.example .env"
  echo ""
  echo "  2. 编辑 .env 文件，填写必需的配置:"
  echo "     vi .env"
  echo ""
  echo "  3. 启动服务:"
  echo "     ./start.sh"
else
  echo "✅ .env 已配置"
  echo ""
  echo "启动服务:"
  echo "  ./start.sh          # 前台运行"
  echo "  ./start-daemon.sh   # 后台运行"
fi

echo ""
