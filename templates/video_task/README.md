# 视频任务模板

将本目录结构复制到 `data/<目录名>/`，素材分别放入 `anchors/` 和 `references/`，再把 `task.example.json` 改名为 `tasks/<任务名>.json`（同一目录可放多个任务），并填写内容。

Anchor 任务配置放在 `data/<目录名>/anchors/anchor-task.json`，生成的正式图（上传 或「设为 Anchor」）会自动存入 `anchors/` 根目录供视频任务使用。

口型模式可增加 `lyrics.txt`（放在任务目录根，与 `tasks/` 同级），或直接在任务 JSON 的 `lyrics` 字段填写歌词。日常也可直接在 Web 工作台新建任务并上传素材。

### 高级视频设置（可选）

任务 JSON 可选以下字段，不填则用默认值。Web 工作台在「高级视频设置」折叠区里也可调整：

| 字段 | 默认值 | 可选值 | 说明 |
|------|--------|--------|------|
| `resolution` | `720p` | `480p` / `720p` / `1080p` | 分辨率，越高越慢 |
| `ratio` | `9:16` | `9:16` / `16:9` / `1:1` / `4:3` / `3:4` | 宽高比 |
| `generate_audio` | `false` | `true` / `false` | 是否让 Seedance 2.5 生成音频 |
| `watermark` | `false` | `true` / `false` | 是否加水印 |
| `output_format` | `mp4` | `mp4` / `webm` | 输出格式 |
