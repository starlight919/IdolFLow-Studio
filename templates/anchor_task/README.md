# Anchor 任务模板

Anchor 任务是生成人物形象图的独立任务，产物可被视频任务用作首帧 anchor。

## 目录与文件

将本目录结构复制到 `data/<目录名>/`，素材参考图放入 `anchors/anchor-references/`，再把 `anchor-task.example.json` 改名为 `anchors/anchor-task.json` 并填写内容。

```
data/<目录名>/
├── anchors/
│   ├── anchor-task.json          # Anchor 任务配置（本模板）
│   ├── anchor-references/        # 参考图片（references[].file 指向这里）
│   ├── generated/<run_id>/       # 生成的候选图
│   └── selected/                 # promote 后的精选图（视频任务从这里选 anchor）
├── references/                   # 参考音视频（视频任务用）
└── tasks/                        # 视频任务配置
```

## 字段说明

| 字段 | 说明 |
|------|------|
| `id` | 任务唯一标识，通常与数据目录名一致 |
| `name` | 任务显示名称 |
| `description` | 正向提示（写实人物描述） |
| `negative` | 负向提示（要避免的元素） |
| `size` | 画幅：`1024x1792`（竖屏 9:16）/ `1792x1024`（横屏 16:9）/ `1024x1024`（方形） |
| `resolution` | 清晰度：`2K` / `1K` / `4K` |
| `candidates` | 一次生成的候选图数量 |
| `model` | 生成模型，如 `gpt-image-2` |
| `aspects` | 人物特征维度（如五官、发型），`priority` 为 `locked` / `required` |
| `references` | 参考图片绑定，`file` 指向 `anchors/anchor-references/` 下的图片，`bindings` 声明每个参考图约束哪些特征 |

日常也可直接在 Web 工作台的 Anchor 面板新建任务并上传参考图。
