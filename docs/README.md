# IdolFlow Studio 文档索引

## 📂 文档结构

```
docs/
├── README.md (本文件)               # 文档索引
├── CHANGELOG.md                     # 变更记录
├── QUICK_REFERENCE.md               # 日常速查卡片
├── SCRIPTS.md                       # 脚本使用指南
├── DEPLOYMENT.md                    # 部署运维指南
├── api/                             # 外部 API 参考
│   ├── Seedance-2.0-API.md
│   ├── Seedance-2.0-Complete-Guide.md
│   └── seedance-2.5-api.md
├── guides/                          # 工作流与设计指南
│   ├── Video_Task_Workflow.md       # 视频任务完整工作流
│   ├── Dance_Pipeline.md            # 舞蹈视频生成流程
│   ├── Singing_Video_Guide.md       # 演唱视频制作指南
│   ├── Prompt_Design.md             # Seedance Prompt 设计文档
│   ├── VIDEO_LOCATIONS.md           # 视频输出位置与管理
│   ├── ANCHOR_REFERENCE_MAPPING.md  # Anchor 参考图映射设计
│   ├── Asset_Design.md              # Seedance 素材 Asset 缓存/复用设计
│   └── Asset_Library_Roadmap.md     # 素材库重构路线图（待办，未实现）
```

## 🚀 快速入门

| 我想... | 看这里 |
|---------|--------|
| 安装启动 | [../README.md](../README.md) |
| 创建视频任务 | [guides/Video_Task_Workflow.md](guides/Video_Task_Workflow.md) |
| 找到生成的视频 | [guides/VIDEO_LOCATIONS.md](guides/VIDEO_LOCATIONS.md) |
| 审核候选视频 | Web 审核 Tab（自动选中第一个可审核 run） |
| 查看生成进度 | `curl http://127.0.0.1:8913/api/runs/<运行ID>/intermediate` |
| 部署到服务器 | [DEPLOYMENT.md](DEPLOYMENT.md) |
| 日常命令速查 | [QUICK_REFERENCE.md](QUICK_REFERENCE.md) |
| 脚本说明 | [SCRIPTS.md](SCRIPTS.md) |
| Prompt 优化 | [guides/Prompt_Design.md](guides/Prompt_Design.md) |
| 排查问题 | 查看 `workspace.log` + Web 界面运行记录 |

## 📖 文档分类

### 工作流指南 (`guides/`)
- **[Video_Task_Workflow.md](guides/Video_Task_Workflow.md)** — 从创建任务到下载视频的完整流程
- **[Dance_Pipeline.md](guides/Dance_Pipeline.md)** — 舞蹈视频生成专项指南
- **[Singing_Video_Guide.md](guides/Singing_Video_Guide.md)** — 演唱视频制作指南
- **[Prompt_Design.md](guides/Prompt_Design.md)** — Seedance Prompt 七层语义架构设计文档
- **[VIDEO_LOCATIONS.md](guides/VIDEO_LOCATIONS.md)** — 视频输出位置、目录结构、磁盘管理
- **[ANCHOR_REFERENCE_MAPPING.md](guides/ANCHOR_REFERENCE_MAPPING.md)** — Anchor 参考图映射机制
- **[Asset_Design.md](guides/Asset_Design.md)** — Seedance 素材 Asset 缓存/复用设计
- **[Asset_Library_Roadmap.md](guides/Asset_Library_Roadmap.md)** — 素材库重构路线图（**待办，未开始实现**）

### 运维 (`docs/`)
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — 部署、配置、公网访问
- **[SCRIPTS.md](SCRIPTS.md)** — `scripts/` 下所有脚本的详细说明
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** — 常用命令一页速查

### API 参考 (`api/`)
> 以下 API 参考文档为内部资料，仅随私有仓库（dev）提供，不包含在公开仓库中。
- **[Seedance-2.0-API.md](api/Seedance-2.0-API.md)** — API 端点参考
- **[Seedance-2.0-Complete-Guide.md](api/Seedance-2.0-Complete-Guide.md)** — 完整使用指南
- **[seedance-2.5-api.md](api/seedance-2.5-api.md)** — 2.5 版本更新

### 其他
- **[CHANGELOG.md](CHANGELOG.md)** — 项目变更记录
## ❓ 常见问题

**Q: 服务启动失败？**
→ 检查 `.env` 文件，确认 API Key 已配置

**Q: 提交密码错误？**
→ 在 `.env` 中设置 `VIDEO_SUBMIT_SECRET` + `VIDEO_SUBMIT_HASH`（用 `scripts/gen_password.py` 生成）

**Q: 找不到生成的视频？**
→ `find runtime/outputs -name "final.mp4"`，详见 [guides/VIDEO_LOCATIONS.md](guides/VIDEO_LOCATIONS.md)

**Q: 背景漂移/口型不准？**
→ 参考 [guides/Prompt_Design.md](guides/Prompt_Design.md) 调整 prompt 约束

---

最后更新：2026-08-15
