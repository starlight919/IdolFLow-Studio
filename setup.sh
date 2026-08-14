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
  # 按操作系统给出对应的安装命令
  case "$(uname -s)" in
    Darwin)
      echo "macOS 安装方法:"
      echo "  brew install ffmpeg openssh"
      ;;
    Linux)
      # 尝试识别具体发行版
      if command -v apt-get >/dev/null 2>&1; then
        echo "Ubuntu/Debian 安装方法:"
        echo "  sudo apt-get update && sudo apt-get install -y ffmpeg openssh-client"
      elif command -v dnf >/dev/null 2>&1; then
        echo "Fedora/RHEL 安装方法:"
        echo "  sudo dnf install -y ffmpeg openssh-clients"
      elif command -v yum >/dev/null 2>&1; then
        echo "CentOS 安装方法:"
        echo "  sudo yum install -y epel-release && sudo yum install -y ffmpeg openssh-clients"
      elif command -v pacman >/dev/null 2>&1; then
        echo "Arch Linux 安装方法:"
        echo "  sudo pacman -S ffmpeg openssh"
      else
        echo "请手动安装: ffmpeg ffprobe openssh-client"
      fi
      ;;
    *)
      echo "请手动安装: ffmpeg ffprobe ssh"
      ;;
  esac
  exit 1
fi

echo ""

# 检查 pip 是否可用（Debian/Ubuntu 可能需要单独安装 python3-pip）
if ! python3 -m pip --version >/dev/null 2>&1; then
  echo "❌ 错误: python3-pip 未安装" >&2
  case "$(uname -s)" in
    Darwin) echo "  macOS: 已随 Python 自带，或重装 python3" >&2 ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        echo "  Ubuntu/Debian: sudo apt-get install -y python3-pip python3-venv" >&2
      else
        echo "  请手动安装 python3-pip" >&2
      fi
      ;;
  esac
  exit 1
fi

echo ""

# 检查可选依赖：ngrok（素材隧道 fallback 用，缺失仅警告不阻断）
echo "📌 检查可选依赖（素材隧道）..."
if command -v ngrok >/dev/null 2>&1; then
  echo "  ✅ ngrok（已安装，可作 Pinggy 失败时的回退方案）"
else
  echo "  ⚠️  ngrok 未安装（可选）。素材隧道默认用 Pinggy，失败时需 ngrok 回退。"
  echo "      安装方法（多平台，不依赖 Homebrew）:"
  echo ""
  echo "        # macOS / Linux 通用（官方脚本，自动识别架构）"
  echo "        curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok-agent.sh | bash"
  echo ""
  echo "        # 或 macOS 用 Homebrew"
  echo "        brew install ngrok"
  echo ""
  echo "        # 或手动下载: https://ngrok.com/download"
  echo ""
  echo "      安装后配置 token（或直接在 .env 填 NGROK_AUTHTOKEN）:"
  echo "        ngrok config add-authtoken <YOUR_TOKEN>"
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
  echo "     bash scripts/start.sh"
else
  echo "✅ .env 已配置"
  echo ""
  echo "启动服务:"
  echo "  bash scripts/start.sh          # 前台运行"
  echo "  bash scripts/start-daemon.sh   # 后台运行"
fi

echo ""
