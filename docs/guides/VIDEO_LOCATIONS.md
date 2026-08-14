# 生成视频位置说明

## 快速定位

### 默认路径
所有生成的视频都在（按「数据目录」组织，非任务名）：
```
./runtime/outputs/<数据目录>/<运行ID>/
```

### 示例
如果你的数据目录是 `ruins`，运行 ID 是 `run_20260810_225617_306897`，视频在：
```
./runtime/outputs/ruins/run_20260810_225617_306897/
```

## 目录结构详解

### 完整结构
```
runtime/outputs/<数据目录>/<运行ID>/
├── review_manifest.json          # 审核清单（包含所有候选视频信息）
├── run.json                       # 运行状态和元数据
├── anchor-1/                      # 第一个 Anchor 的结果
│   ├── candidate-01/              # 候选视频 1
│   │   ├── final.mp4             # ✅ 最终视频（带音频）
│   │   └── result.mp4            # 原始生成视频
│   ├── candidate-02/              # 候选视频 2
│   │   ├── final.mp4
│   │   └── result.mp4
│   ├── candidate-03/
│   └── candidate-04/
├── anchor-2/                      # 第二个 Anchor 的结果
│   ├── candidate-01/
│   ├── candidate-02/
│   ├── candidate-03/
│   └── candidate-04/
└── ...
```

### 文件说明

#### 1. final.mp4
- **这是你要的视频文件！**
- 包含完整的音频和视频
- 已经过后处理（如果有音频回灌）
- 可以直接使用、下载或分享

#### 2. result.mp4
- API 返回的原始视频
- 可能不包含音频（取决于生成类型）
- 通常用于调试

#### 3. review_manifest.json
- 包含所有候选视频的元数据
- 包含候选 ID、路径、Anchor 信息等
- Web 界面用这个文件展示候选列表

## 如何查找视频

### 方法 1: Web 界面（推荐）
1. 打开 http://127.0.0.1:8913/
2. 点击"运行记录"标签
3. 找到对应的运行记录
4. 点击"查看候选"或"下载"按钮

### 方法 2: 命令行查找
```bash
# 查看所有运行
ls -la runtime/outputs/

# 查看特定任务的所有运行
ls -la runtime/outputs/<数据目录>/

# 查看特定运行的所有视频
find runtime/outputs/<数据目录>/<运行ID>/ -name "final.mp4"

# 示例：查看 ruins 任务的所有最终视频
find runtime/outputs/ruins/ -name "final.mp4"
```

### 方法 3: 使用 API 查询
```bash
# 获取所有运行列表
curl http://127.0.0.1:8913/api/runs | jq

# 获取特定运行的信息
curl http://127.0.0.1:8913/api/runs/<运行ID> | jq

# 获取运行的清单（包含所有候选视频路径）
curl http://127.0.0.1:8913/api/runs/<运行ID>/manifest | jq
```

## 实际示例

基于你的系统：

### 当前已有的运行
```bash
# ruins 任务有 3 个运行
runtime/outputs/ruins/
├── run_20260810_223315_833530/
├── run_20260810_225542_826050/
└── run_20260810_225617_306897/
```

### 最新运行的视频位置
```bash
runtime/outputs/ruins/run_20260810_225617_306897/
├── anchor-1/
│   ├── candidate-01/final.mp4  ✅
│   ├── candidate-02/final.mp4  ✅
│   ├── candidate-03/final.mp4  ✅
│   └── candidate-04/final.mp4  ✅
└── anchor-2/
    ├── candidate-01/final.mp4  ✅
    ├── candidate-02/final.mp4  ✅
    ├── candidate-03/final.mp4  ✅
    └── candidate-04/final.mp4  ✅
```

共 8 个视频文件（2 个 Anchor × 4 个候选）

### 快速访问命令
```bash
# 打开视频目录
cd /Users/4paradigm/Downloads/idol-video-studio/runtime/outputs/ruins/run_20260810_225617_306897
open .  # macOS 用 open，Linux 用 xdg-open 或 nautilus

# 列出所有最终视频
find . -name "final.mp4"

# 复制所有视频到桌面
mkdir -p ~/Desktop/ruins_videos
find . -name "final.mp4" -exec cp {} ~/Desktop/ruins_videos/ \;
```

## 配置自定义路径

如果想修改视频输出位置，编辑 `video-workspace.json`：

```json
{
  "output_root": "./runtime/outputs"  # 改成你想要的路径
}
```

例如改成独立磁盘：
```json
{
  "output_root": "/Volumes/ExternalDrive/idol-videos/outputs"
}
```

重启服务后生效。

## 其他相关目录

### 中间文件
```
runtime/work/<数据目录>/
```
- 临时工作文件
- 视频处理中间步骤
- 可以安全删除（完成后）

### 任务配置和素材
```
data/<数据目录>/
├── anchors/                 # Anchor 图片（图片唯一落点）
│   ├── anchor-task.json     # Anchor 任务配置
│   ├── anchor-references/   # Anchor 参考图片
│   ├── generated/<run_id>/  # 生成的候选图
│   └── *.jpg                # 上传 / promote 后的正式图（Video 任务从这里选 anchor 图）
├── references/              # 参考音视频（视频 + 音频统一落点）
├── tasks/                   # Video 任务配置（支持同一目录多个任务）
│   ├── 唱歌版.json
│   └── 跳舞版.json
└── seedance/
    └── assets.json          # 已上传资源 ID（同目录共享）
```

> 素材目录约定：图片存放于 `anchors/`，音视频存放于 `references/`，任务目录根目录仅用于内部目录。

Anchor 任务 ID = 数据目录名（如 `马路风`）；Video 任务 ID 格式为 `数据目录__任务名称`（如 `马路风__唱歌版`）。

### Web 运行记录
```
runtime/outputs/.web-runs/
```
- 每个运行的状态 JSON
- 用于 Web 界面显示进度

## 视频下载方式

### 方法 1: Web 界面下载
- 在 Web 界面点击"下载"按钮
- 自动命名为：`<数据目录>__<任务名>_<Anchor>_<参考>_<变体>_candidate-XX.mp4`（含数据目录与任务名，中文保留）

### 方法 2: 直接复制文件
```bash
# 复制单个视频
cp runtime/outputs/ruins/run_20260810_225617_306897/anchor-1/candidate-01/final.mp4 ~/Downloads/

# 复制所有视频到一个文件夹
mkdir -p ~/Downloads/ruins_all_videos
find runtime/outputs/ruins/run_20260810_225617_306897 -name "final.mp4" | \
  xargs -I {} cp {} ~/Downloads/ruins_all_videos/
```

### 方法 3: 使用 API 下载
```bash
# 获取候选列表
curl http://127.0.0.1:8913/api/runs/<运行ID>/manifest | jq '.candidates[].id'

# 下载特定候选
curl -O -J "http://127.0.0.1:8913/api/runs/<运行ID>/download/<候选ID>"
```

## 磁盘空间管理

### 查看占用空间
```bash
# 查看总输出目录大小
du -sh runtime/outputs/

# 查看每个任务的大小
du -sh runtime/outputs/*/

# 查看每个运行的大小
du -sh runtime/outputs/<数据目录>/*/
```

### 清理旧运行

> 推荐优先使用 Web 界面操作，避免手动删除误伤：
> - 删除单条运行：运行列表中的「删除」按钮（可选级联删除生成文件）
> - 删除整个任务：任务卡片的「删除」按钮（可选级联删除生成文件）
> - 删除整个数据目录：文件夹选择器顶层目录旁的「🗑」按钮（级联清理任务、运行、素材与缓存）

```bash
# ⚠️ 小心：删除前请确认已备份需要的视频

# 删除特定运行
rm -rf runtime/outputs/<数据目录>/<运行ID>/

# 删除所有运行（保留最新 3 个）
cd runtime/outputs/<数据目录>/
ls -t | tail -n +4 | xargs rm -rf
```

## 常见问题

### Q: 为什么有两个视频文件（final.mp4 和 result.mp4）？
A: 
- `result.mp4` 是 API 直接返回的原始视频
- `final.mp4` 是经过后处理的最终版本（如音频回灌）
- **使用 final.mp4 即可**

### Q: 如何只下载想要的视频？
A: 
- 在 Web 审核页中，每个候选视频用浏览器原生播放器播放，右键或播放器控制栏即可保存到本地
- 候选视频文件位于 `runtime/outputs/<数据目录>/<运行ID>/<anchor>/<候选>/final.mp4`，也可直接按需拷贝

### Q: 视频生成失败后会有文件吗？
A: 
- 如果完全失败，不会有 `final.mp4`
- 可能会有部分中间文件
- 查看 `run.json` 了解失败原因

### Q: 可以在生成过程中预览吗？
A: 
- 可以！在 Web 审核页面选择正在运行的 run，已完成的候选视频会实时出现
- 或使用 API 查看中间结果：`curl http://127.0.0.1:8913/api/runs/<运行ID>/intermediate`

## 总结

**最重要的位置**:
```
runtime/outputs/<数据目录>/<运行ID>/anchor-X/candidate-XX/final.mp4
```

**快速查找命令**:
```bash
find runtime/outputs -name "final.mp4"
```

**在 Web 界面**:
```
http://127.0.0.1:8913/ → 运行记录 → 选择运行 → 查看/下载
```
