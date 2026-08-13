# IdolFlow Studio

Anchor 设计、视频生成、任务运行、候选审核与下载的一体化 API 工作台。

- GPT Image 2 Anchor 生成。
- Seedance 对口型、口型 + 动作、纯动作视频生成。
- 每张 Anchor 参考图可对每个维度分别配置参考内容和约束。
- 支持逐图去水印、批量候选、重新生成、审核和 promote。
- 所有生成使用 API，不需要 GPU、模型权重或 model path。

📖 **快速参考**: [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | 📚 **完整文档**: [docs/README.md](docs/README.md) | 📝 **更新日志**: [docs/CHANGELOG.md](docs/CHANGELOG.md)

完整部署、配置、数据目录、工作流、CLI、Git 管理和排错说明见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 首次启动

### 1. 安装系统依赖

**macOS**（需先安装 Homebrew）：

```bash
# 若尚未安装 Homebrew，可用国内镜像安装：
#   /bin/bash -c "$(curl -fsSL https://gitee.com/ineo6/homebrew-install/raw/master/install.sh)"

brew install python ffmpeg openssh
```

**Ubuntu/Debian**：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ffmpeg openssh-client
```

> 💡 **国内镜像加速**：macOS 上 Homebrew 下载慢时，可替换为清华/中科大镜像源（编辑 `~/.zprofile` 或 `~/.bash_profile`）：
>
> ```bash
> # 清华 Homebrew 镜像
> export HOMEBREW_API_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles/api"
> export HOMEBREW_BOTTLE_DOMAIN="https://mirrors.tuna.tsinghua.edu.cn/homebrew-bottles"
> export HOMEBREW_BREW_GIT_REMOTE="https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/brew.git"
> export HOMEBREW_CORE_GIT_REMOTE="https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-core.git"
> ```
>
> Python 依赖（`pip`）加速：安装时用 `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash setup.sh`，setup.sh 会自动用该镜像安装依赖。

### 2. 准备环境变量

```bash
cd idolflow-studio
cp .env.example .env
```

编辑 `.env`，填写：

```bash
SEEDANCE_API_BASE=https://<your-internal-gateway>/phanrouter
SEEDANCE_API_KEY=...
SEEDANCE_SD25_API_KEY=...
ASSET_GROUP_ID=...
PINGGY_TOKEN=...
NGROK_AUTHTOKEN=...
VIDEO_SUBMIT_SECRET=<用 scripts/gen_password.py 生成>
VIDEO_SUBMIT_HASH=<用 scripts/gen_password.py 生成>
```

`.env` 不进入 Git，需要通过安全渠道在机器间单独交接。

> 🔐 **提交密码**：`VIDEO_SUBMIT_SECRET` 和 `VIDEO_SUBMIT_HASH` 用 `python3 scripts/gen_password.py <密码>` 生成。`.env` 不存明文密码，只存盐+哈希。启动生成时输入密码用于防误触、防没有 `.env` 权限的人乱点消耗额度。详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#提交密码机制防误触防外人)。

### 3. 安装 Python 环境

```bash
chmod +x setup.sh scripts/*.sh
bash scripts/setup.sh
```

### 4. 启动工作台

```bash
bash scripts/start.sh
```

浏览器打开：

```text
http://127.0.0.1:8913
```

监听局域网：

```bash
bash scripts/start.sh --host 0.0.0.0 --port 8913
```

## Pinggy 隧道（自动按需启动）

**无需手动启动 Pinggy**。隧道逻辑已集成到服务中：

- **按需启动**：仅在上传素材给 Seedance（`CreateAsset`）时才自动启动隧道，让 Seedance 能访问你的文件 URL
- **自动复用**：同一会话内隧道状态会被缓存复用，不会每次重复建连
- **自动重建**：隧道失效（Pinggy 服务端重启/断连）时自动检测并重建，上传失败会重试（最多 3 次）
- **用完即弃**：素材上传完成后，submit 用 `asset://` 引用，不再依赖隧道

**唯一前提**：在 `.env` 中正确配置 `PINGGY_TOKEN`。之后整个上传流程全程无需手动干预。

> 📄 传输与上传失败重试详见 [docs/guides/Video_Task_Workflow.md](docs/guides/Video_Task_Workflow.md#素材上传)

## 停止服务

前台启动时按 `Ctrl+C`。

后台启动：

```bash
bash scripts/start-daemon.sh
```

停止：

```bash
bash scripts/stop.sh
```

## 默认数据目录

```text
data/<数据目录>/                  # 素材、任务配置、Anchor 模块
  ├── anchors/                    # Anchor 参考图、生成候选、精选图
  └── tasks/                      # Video 任务配置（可有多个）
runtime/outputs/<数据目录>/        # 生成的视频
runtime/work/<数据目录>/           # 临时文件
```

路径可在 `video-workspace.json` 中修改。

**生成的视频位置**: `runtime/outputs/<数据目录>/<run_id>/anchor-X/candidate-XX/final.mp4`

详细说明见 [docs/guides/VIDEO_LOCATIONS.md](docs/guides/VIDEO_LOCATIONS.md) | 变更历史见 [docs/CHANGELOG.md](docs/CHANGELOG.md)

## 核心设计概念

系统围绕"**Anchor 造角色 → 选模式 → 参考音视频 → 批量生成候选 → 审核挑选**"的工作流设计。核心是把**人物形象（Anchor）**、**生成配置（任务）**、**一次执行（运行）**三层解耦，理解下面几个概念就能掌握整个系统。

### 1. 三层数据组织

| 层级 | 说明 | 例子 |
|------|------|------|
| **数据目录** `data_dir` | 一组相关素材的总目录，跨任务共享 | `马路风` |
| **任务** `task` | 一个具体的生成配置（同一目录可多个） | `马路风__唱歌版` |
| **运行** `run` | 一次实际执行（每点一次启动生成产生一个） | `run_20260812_174354` |

```
data/马路风/                  ← 数据目录
  ├── anchors/                ← Anchor 形象图（GPT Image 2 生成）
  └── tasks/                  ← 视频任务配置
      ├── 唱歌版.json
      └── 跳舞版.json
runtime/outputs/马路风/
  └── run_20260812_174354/    ← 一次运行
      ├── anchor-1/
      │   └── candidate-01/   ← 一个候选视频
      │       └── final.mp4
      └── anchor-2/
```

- **候选（candidate）**：每个 Anchor × 每个参考视频 × 候选数 组合，生成多条视频供挑选。

> 📄 文件目录与产物位置详见 [docs/guides/VIDEO_LOCATIONS.md](docs/guides/VIDEO_LOCATIONS.md)

### 2. Anchor（形象锚点）设计

Anchor 是整个系统的"主角"抽象。它不是一张图，而是一组**可复用的形象参考**，通过 Anchor 生成器（GPT Image 2）批量产出。

**Anchor 的核心思路**：把"人物形象"与"视频任务"解耦。

1. **先造角色，再做视频**：在 Anchor 面板上传参考图（脸、服装、场景），生成多个候选形象图（如"站姿正面""坐姿""全身""特写"），存入目录的 `anchors/` 子目录。
2. **跨任务复用**：同一个数据目录下创建多个视频任务（唱歌版、跳舞版），都引用同一批 Anchor 图，保证不同任务里的主角形象一致。
3. **每个 Anchor 独立出片**：一个任务会把每个 Anchor × 每个参考视频 × 候选数 组合生成视频。比如 2 个 Anchor × 1 个参考视频 × 4 候选 = 8 条候选视频。

| 概念 | 说明 |
|------|------|
| **Anchor 源图** | 用户上传的参考（一张图可绑定多个参考点） |
| **Anchor 参考点** | 生成时绑定的角色属性（脸/身体/服装/场景等） |
| **生成任务** | 一次批量生成，产出多张候选形象图，也可自由文本描述 |
| **产出图** | 生成的形象图，存到 `data/<dir>/anchors/` 供视频任务引用 |

> 📄 参考图绑定与映射机制详见 [docs/guides/ANCHOR_REFERENCE_MAPPING.md](docs/guides/ANCHOR_REFERENCE_MAPPING.md)

### 3. 三种生成模式（mode）

| 模式 | 传视频 | 传音频 | 用途 |
|------|--------|--------|------|
| `lip_sync` 对口型 | 可选 | 可选 | 严格对齐逐字嘴形，**可纯音频驱动** |
| `dance_lip_sync` 口型+动作 | 强制 | 可选 | 同步模仿口型与动作编排 |
| `motion` 模仿动作 | 强制 | 不传 | 舞蹈/手势舞，不约束口型 |

**对口型（lip_sync）的三条驱动路径**，通过参考音视频的「视频/音频」标签页切换：

- 🎵 **音频 tab** = 纯音频驱动：只传音频，Seedance 只做口型
- 📹 **视频 tab + 勾"传参考音频"** = 音视频驱动：画面 + 从视频提取的音频
- 📹 **视频 tab + 不勾** = 视频驱动：只从视频画面学习口型

> 📄 完整创建/运行流程详见 [docs/guides/Video_Task_Workflow.md](docs/guides/Video_Task_Workflow.md)；对口型唱歌详见 [docs/guides/Singing_Video_Guide.md](docs/guides/Singing_Video_Guide.md)；口型+动作管线详见 [docs/guides/Dance_Pipeline.md](docs/guides/Dance_Pipeline.md)

### 4. 时长对齐（pad_mode）

Seedance 的 `duration` 只接受整数秒，原始视频/音频往往是非整数时长。`pad_mode` 决定如何补足：

| 模式 | 做法 | 适用场景 |
|------|------|----------|
| `none` 原始时长 | 不补齐，直接用原始长度 | 不想引入额外帧 |
| `back` 后面补齐 | 视频末尾补最后一帧、音频末尾补静音 | 默认推荐，最稳定 |
| `front` 前面补齐 | 视频开头补第一帧、音频开头补静音 | 缓解口型延迟（前面静止帧"预热"） |

最终输出**都会裁回原始时长**（mux 阶段用原始音频 `-shortest` 或裁掉前面 padding），保证音画对齐。

> 📄 时长对齐的三种模式与设计思路详见 [docs/guides/Video_Task_Workflow.md](docs/guides/Video_Task_Workflow.md#时长处理)

### 5. Prompt 分层架构（V2）

每次生成使用 7 层语义化 prompt：任务定位 → 参考分工 → 表演约束 → 保留要求 → 镜头策略 → 画质 → 自定义约束。系统会根据**是否有视频/音频参考**自动调整表演约束（如纯音频驱动时不依赖视频口型）。

> 📄 7 层架构与约束设计详见 [docs/guides/Prompt_Design.md](docs/guides/Prompt_Design.md)

## 快速健康检查

服务启动后：

```bash
curl -f http://127.0.0.1:8913/api/settings/public
curl -f http://127.0.0.1:8913/api/anchor-presets
```

源码检查：

```bash
python -m compileall -q idolmv_pipeline run.py
node --check idolmv_pipeline/web/static/app.js
```

## Git

该目录适合建立为私有 Git 仓库：

```bash
git init
git add .
git commit -m "Initialize IdolFlow Studio"
```

`.gitignore` 已排除 `.env`、上传数据、运行输出、媒体文件和虚拟环境。不要强行提交 `.env`。
