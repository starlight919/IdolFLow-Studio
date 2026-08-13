# 视频任务完整工作流

> 最后更新：2026-08-12

## 概述

IdolFlow Studio 的视频生成以「数据目录」为中心。同一数据目录可创建多个不同任务（如「唱歌版」「跳舞版」），共享 Anchor 精选图和原始素材。

## 启动服务

```bash
bash scripts/start.sh         # 前台（开发）
bash scripts/start-daemon.sh  # 后台
bash scripts/stop.sh          # 停止
bash scripts/status.sh        # 查看状态
```

Web 工作台：**http://127.0.0.1:8913/**

提交密码保护付费 API 操作（生成），浏览/审核/下载不需要密码。

## 任务结构

```
data/<数据目录>/
├── anchors/                  # Anchor 模块
│   ├── anchor-references/    # 参考图片
│   ├── generated/<run_id>/   # 生成候选
│   └── selected/             # 精选图（Video 任务引用）
├── tasks/                    # 每个 .json 文件一个任务
│   ├── 唱歌版.json
│   └── 跳舞版.json
└── 原始素材文件               # .mov, .jpg, .txt 等
```

任务 ID 格式：`数据目录__任务名称`（如 `马路风__唱歌版`）

## 三种模式

| 模式 | 用途 | 传视频 | 传音频 | 需要歌词 |
|------|------|--------|--------|----------|
| `lip_sync` | 纯对口型 | 可选 | 可选 | 是 |
| `motion` | 纯动作模仿 | 强制 | 不传 | 否 |
| `dance_lip_sync` | 口型+动作 | 强制 | 可选（默认传） | 是 |

### 关于音频/视频传入

**`lip_sync`（纯对口型）** 支持三条驱动路径：

| 传视频 | 传音频 | 驱动方式 | 说明 |
|--------|--------|----------|------|
| ✅ | ❌ | 视频驱动 | 只传参考视频，Seedance 从视频中学习口型+画面 |
| ❌ | ✅ | 音频驱动 | 只传音频，Seedance 纯音频对口型（无参考画面） |
| ✅ | ✅ | 音视频驱动 | 传视频 + 从视频提取的音频，口型精度最高 |

**`motion`（纯动作模仿）**：必须传参考视频，不涉及音频。Seedance 模仿视频中的动作。

**`dance_lip_sync`（口型+动作）**：必须传参考视频，音频可选（默认勾选）。视频用于模仿动作，勾选后从视频提取音频一并上传以提升口型精度。

> **注意**：无论是否传音频给 Seedance，mux 阶段始终会用原始音频回灌到 `final.mp4`。`pass_reference_audio` 只控制是否将音频传给 Seedance 用于生成过程。

## 创建任务

在 Web 工作台「视频任务」面板：

1. 选择生成模式
2. 填写任务名称 + 选择数据文件夹
3. 设置候选数（默认 4）
4. 填写参考视频文件（每行一个），通过 📹/🎵 标签页可切换填写独立音频文件
5. 选择时长对齐模式（默认"原始时长"，可选"前面补齐"或"后面补齐"）
6. `lip_sync` 模式可选"传参考视频"/"传参考音频"；`dance_lip_sync` 视频强制、音频可选；`motion` 不显示音频选项
7. 对口型模式填写歌词
8. 可选填写额外约束（如"减小动作幅度，不要笑"）
9. 保存任务 → 提交生成

### 任务配置示例

```json
{
  "id": "马路风__唱歌版",
  "name": "唱歌版",
  "data_dir": "马路风",
  "mode": "dance_lip_sync",
  "candidates": 4,
  "references": [
    {
      "name": "reference-1",
      "file": "zengzeng2.mov",
      "duration": 15,
      "pass_reference_audio": true,
      "pad_mode": "back"
    }
  ],
  "lyrics": "啦啦啦 啦啦啦 啦啦啦啦啦",
  "constraints": "保持人物身份、服装和背景一致"
}
```

## 生成流程

提交后系统自动完成：

1. **Prepare** — 校验素材、提取音频、截取参考视频、补足时长对齐
2. **Tunnel** — 启动素材隧道
3. **Upload** — 上传 Anchor 图片、参考视频、音频到 Seedance
4. **Submit** — 提交 Seedance 生成任务
5. **Poll** — 轮询等待完成，每完成一个候选立即写入 manifest
6. **Download** — 下载 result.mp4
7. **Mux** — 回灌原始音频 → final.mp4
8. **Manifest** — 生成审核清单

## 时长处理

Seedance API 的 `duration` 参数要求整数秒。系统会自动向上取整（`ceil`），同时根据 `pad_mode` 选择如何补足到整数秒。

### 三种 pad_mode 模式

在参考音视频区域可选择时长对齐策略：

| 模式 | 说明 | 视频处理 | 音频处理 | 回灌处理 |
|------|------|----------|----------|----------|
| `back`（默认） | 末尾补齐 | `tpad=stop_mode=clone` 末尾克隆最后一帧 | `apad=whole_dur` 末尾补静音 | mux 用 `-shortest` 自动裁掉末尾多余部分 |
| `front` | 前面补齐 | `tpad=start_mode=clone` 开头克隆第一帧 | `concat` 开头拼接静音 | 先 `-ss` 裁掉前面的 padding，再 mux |
| `none` | 原始时长 | 不补帧，截取原始时长 | 不补静音 | mux 用 `-shortest` 以原始音频为准 |

### 设计思路

- **`back`（末尾补齐）**：最常用的模式。视频末尾静止帧 + 静音不会影响主体内容，Seedance 生成的视频末尾也会是相对静止的画面，mux 时用原始音频的 `-shortest` 自然裁回原始长度。

- **`front`（前面补齐）**：适用于口型同步场景。有些视频开头就有快速口型变化，末尾补齐可能导致口型延迟（Seedance 需要处理额外的静止帧）。前面补齐让 Seedance 从静止帧开始"预热"，到达真实内容时口型更准确。代价是 mux 后需要先裁掉前面的 padding。

- **`none`（原始时长）**：不补齐，直接用原始时长提交。适合不想引入任何额外帧的场景，但 Seedance 仍要求 `duration` 为整数秒，实际提交的 `seedance_duration` 仍为 `ceil(total)`，视频本身不补帧。

### 示例流程（17.857s 视频，ceil=18s）

```
原始视频: 17.857s

─── back 模式 ───
trim+tpad(末尾补): 18.000s → Seedance → 18.000s → mux(-shortest) → 17.857s

─── front 模式 ───
trim+tpad(前面补): 18.000s → Seedance → 18.000s → 裁前面0.143s → mux → 17.857s

─── none 模式 ───
trim(不补): 17.857s → Seedance(ceil=18) → ~18.000s → mux(-shortest) → 17.857s
```

- Seedance 2.5 上限 30s，非 2.5 上限 15s
- 补帧量 = `ceil(total) - total`（如 17.857s → 补 0.143s）
- mux 阶段始终用原始音频回灌到 `final.mp4`

## 审核

切换到「审核」tab 查看已完成候选视频，点击 ⬇ 下载按钮保存。

## 配置

常用环境变量（`.env`）：

| 变量 | 说明 |
|------|------|
| `VIDEO_DATA_ROOT` | 数据目录根路径 |
| `VIDEO_WORK_ROOT` | 临时工作目录 |
| `VIDEO_OUTPUT_ROOT` | 输出目录 |
| `VIDEO_WEB_PORT` | Web 端口（默认 8913） |
| `VIDEO_MAX_CONCURRENT_RUNS` | 最大并发运行数 |
| `VIDEO_SUBMIT_SECRET` + `VIDEO_SUBMIT_HASH` | 提交密码（HMAC，用 `scripts/gen_password.py` 生成） |
| `VIDEO_PUBLISH_ENABLED` | 是否启用发布 |

API key 和 token 只放在 `.env`，不写入任务 JSON。
