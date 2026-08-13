# 快速参考卡片

## 🚀 启动服务

```bash
bash scripts/start.sh
# 打开 http://127.0.0.1:8913/
```

## 📹 生成的视频在哪里？

```bash
runtime/outputs/<数据目录>/<运行ID>/anchor-X/candidate-XX/final.mp4
```

**快速查找所有视频**:
```bash
find runtime/outputs -name "final.mp4"
```

## 🔐 提交密码

用脚本生成盐+哈希（`.env` 不存明文密码）：

```bash
python3 scripts/gen_password.py <你的密码>
# 把输出的 VIDEO_SUBMIT_SECRET / VIDEO_SUBMIT_HASH 写入 .env
```

启动生成时在网页输入你设的明文密码即可。防止误触和没有 `.env` 权限的人乱点消耗额度。

## 🌐 公网访问（工作台网页）

> **素材隧道是自动的**：上传素材给 Seedance 时会自动按需启动/复用/重建隧道，无需手动操作。
> 这里的 `start-pinggy.sh` 只用于把**工作台网页**暴露到公网，让外部浏览器访问 UI（可选）。

```bash
bash scripts/start-pinggy.sh
```

## 👀 查看生成进度

```bash
# 获取运行列表
curl http://127.0.0.1:8913/api/runs | jq

# 查看中间结果
curl http://127.0.0.1:8913/api/runs/<运行ID>/intermediate | jq
```

## 📂 重要目录

| 目录 | 用途 |
|------|------|
| `data/<目录>/anchors/` | Anchor 任务配置、参考图、生成候选、精选图 |
| `data/<目录>/tasks/` | Video 任务配置（同一目录可多个，如 `唱歌版.json`） |
| `runtime/outputs/<数据目录>/` | **生成的视频** ✅（按数据目录而非任务名组织） |
| `runtime/work/<数据目录>/` | 临时中间文件 |
| `.env` | 环境变量配置（不提交 Git） |

> **任务 ID 格式**：Anchor 任务 ID = 数据目录名（如 `马路风`）；Video 任务 ID = `数据目录__任务名称`（如 `马路风__唱歌版`）。同一数据目录的 Anchor 精选图和 Video 任务共享素材。

## 🔧 常用命令

### 服务管理
```bash
# 启动服务
bash scripts/start.sh

# 后台启动
bash scripts/start-daemon.sh

# 停止服务
bash scripts/stop.sh

# 查看状态
bash scripts/status.sh

# 查看日志
tail -f workspace.log
```

### 视频管理
```bash
# 查看所有运行
ls -la runtime/outputs/

# 查看特定数据目录的运行
ls -la runtime/outputs/<数据目录>/

# 列出所有最终视频
find runtime/outputs -name "final.mp4"

# 复制所有视频到桌面
mkdir -p ~/Desktop/all_videos
find runtime/outputs -name "final.mp4" -exec cp {} ~/Desktop/all_videos/ \;

# 查看磁盘占用
du -sh runtime/outputs/
```

### API 测试
```bash
# 健康检查
curl http://127.0.0.1:8913/api/settings/public

# 获取任务列表
curl http://127.0.0.1:8913/api/tasks | jq

# 获取运行列表
curl http://127.0.0.1:8913/api/runs | jq

# 查看运行详情
curl http://127.0.0.1:8913/api/runs/<运行ID> | jq

# 查看中间结果
curl http://127.0.0.1:8913/api/runs/<运行ID>/intermediate | jq
```

## 🆘 问题排查

### 服务启动失败
```bash
# 检查 .env 文件
cat .env

# 检查端口占用
lsof -i :8913

# 手动运行（查看详细错误）
python run.py video web
```

### 提交密码错误
```bash
# 确认密码已设置
grep VIDEO_SUBMIT_HASH .env

# 重启服务使配置生效
bash scripts/stop.sh && bash scripts/start-daemon.sh
```

### Pinggy tunnel 启动失败
```bash
# 确认 token 已配置
grep PINGGY_TOKEN .env

# 手动测试 Pinggy
ssh -p 443 -R0:localhost:8913 -L4300:localhost:4300 a.pinggy.io
```

### 找不到生成的视频
```bash
# 检查输出目录
ls -la runtime/outputs/

# 检查运行状态
curl http://127.0.0.1:8913/api/runs | jq '.[] | {run_id, status, stage}'

# 查看运行详情（包含错误信息）
curl http://127.0.0.1:8913/api/runs/<运行ID> | jq
```

## 📚 完整文档

- **../README.md** - 项目主页和快速开始
- **guides/VIDEO_LOCATIONS.md** - 视频位置详细说明
- **DEPLOYMENT.md** - 完整部署指南
- **guides/Prompt_Design.md** - Prompt 设计文档
- **CHANGELOG.md** - 更新日志

## 🔗 Web 界面

```
http://127.0.0.1:8913/
```

- 📝 **视频任务** - 创建和编辑视频任务
- 🧩 **Anchor** - GPT Image 2 生成/审核/推介 Anchor 图片
- 🎬 **运行记录** - 查看生成历史和状态
- 📊 **审核** - 预览和下载候选视频

顶部导航栏右侧有 **🌙/☀️ 主题切换按钮**，点击切换深浅色（选择会记住）。

## 🎤 歌词时间戳（滚动歌词）

对口型/口型+动作任务可为歌词逐句打时间点（可选）：歌词框下方点「打时间戳（可选）>」，播放音视频后逐句打点。快捷键：空格播放/暂停、Enter 打点、↑/↓ 切行、Esc 关闭。不打时间戳也能正常生成。注意：参考视频用「前面补齐」时，时间戳会自动加偏移对齐。详见 [guides/Singing_Video_Guide.md](guides/Singing_Video_Guide.md)。

## 🧩 Anchor 模块快速指南

Anchor 选项卡用于生成、审核和管理 Anchor 角色形象图。

### 操作步骤

**步骤顺序**（共5步）：

1. **数据目录 & 任务名** — 通过文件夹选择器选择「数据目录」（必填，同一目录可放多个视频任务），填写任务名称用于显示
2. **特殊需求** — (可选) 用自然语言描述跨图替换需求，智能解析后应用
3. **参考图片** — 上传/选择参考图（图1, 图2, 图3...），每张图可展开绑定参考点
4. **选择参考点与来源图** — 勾选参考点并为每个选择来源图
5. **补充描述 & 生成** — 点击画质/风格标签、禁止项标签快捷选择，或手动输入

### 快捷标签（步骤5）

- **画质风格**：真实iPhone拍摄、电影级光影、柔光ins风、复古胶片、棚拍商业、极简白底、高定时尚、日系清透
- **禁止项**：不要水印/文字、不要畸形手、不要多余人、不要模糊、不要塑料感、不要噪点、不要裁剪异常、不要曝光过度

> 标签多选叠加，也可手动输入补充文本。点击标签选中/取消，最终自动合并为 prompt。

### 任务管理

| 操作 | 说明 |
|------|------|
| 保存任务 | 「数据目录」必填（通过文件夹选择器选取），任务名称用于显示 |
| 编辑任务 | 在任务列表中点击「编辑」加载已有配置 |
| 删除任务 | 点击红色「删除」按钮，会同时删除关联的所有资产 |
| 生成 | 保存后点击「生成」提交运行 |

### API 端点

```bash
# 查看 Anchor 任务列表
curl http://127.0.0.1:8913/api/anchor-tasks | jq

# 查看 Anchor 运行
curl http://127.0.0.1:8913/api/anchor-runs | jq

# 删除 Anchor 任务
curl -X DELETE http://127.0.0.1:8913/api/anchor-tasks/<数据目录>

# 查看 Anchor 候选（审核用）
curl http://127.0.0.1:8913/api/anchor-runs/{run_id}/candidates | jq

# 投票推荐/不推荐
curl -X POST http://127.0.0.1:8913/api/anchor-runs/{run_id}/vote \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "...", "vote": "up"}'

# 推介为 Anchor
curl -X POST http://127.0.0.1:8913/api/anchor-runs/{run_id}/promote \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "..."}'
```

### CLI 操作

```bash
# 列出所有 Anchor 任务
python run.py anchor list

# 运行 Anchor 生成
python run.py anchor run --task <数据目录> --candidates 4

# 查看运行状态
python run.py anchor status --task <数据目录> --run-id <运行ID>

# 删除 Anchor 任务
python run.py anchor delete --task <数据目录>
```

## 💡 最佳实践

### 1. 定期清理
```bash
# 备份重要视频后删除旧运行
du -sh runtime/outputs/*/  # 查看占用
rm -rf runtime/outputs/<数据目录>/<旧运行ID>/
```

### 2. 监控进度
```bash
# 创建监控脚本
watch -n 5 'curl -s http://127.0.0.1:8913/api/runs | jq ".[] | select(.status==\"running\")"'
```

### 3. 批量下载
```bash
# 下载某个运行的所有视频
RUN_ID="run_20260810_225617_306897"
TASK_ID="ruins"
mkdir -p ~/Downloads/${TASK_ID}_${RUN_ID}
find runtime/outputs/${TASK_ID}/${RUN_ID} -name "final.mp4" -exec cp {} ~/Downloads/${TASK_ID}_${RUN_ID}/ \;
```

## 🎯 快速目标

| 我想... | 看这里 |
|---------|--------|
| 启动服务 | `bash scripts/start.sh` |
| 找到视频 | [guides/VIDEO_LOCATIONS.md](guides/VIDEO_LOCATIONS.md) |
| 审核候选 | Web 审核 Tab（自动选中第一个可审核 run） |
| 公网访问 | `bash scripts/start-pinggy.sh` |
| 排查问题 | 本文档的"问题排查"章节 |

---

💾 **保存本文件到手机或打印出来，随时查阅！**

最后更新：2026-08-13 (歌词时间戳、深浅色主题)
