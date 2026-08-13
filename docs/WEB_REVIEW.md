# IdolFlow Studio Web 服务评审

> 范围：`idolmv_pipeline/web/`（主工作台）+ `idolmv_pipeline/review/`（审核页）
> 结论：**工程质量扎实的内部工具，代码可读、可编译；但暴露前必须修 1 个高危 + 1 个中危安全问题。**

> **🔧 修复状态（2026-08-12 复检）**：两个安全问题均已修复并验证通过——
> - 🔴 HIGH：`review/server.py` 与 `review/static/index.html` 已删除，`run.py` 中 `review` 子命令及对应 import 一并移除，全仓库无悬空引用。审核能力保留在主工作台。
> - 🟠 MEDIUM：`serve_file` 增加 `root` containment 校验，`/static/` 路由传 `root=STATIC_DIR`，越界返回 404。
> - Python `compileall` 全部通过。当前场景（内部两人使用）无需进一步处理。

---

## 架构

| 服务 | 技术 | 入口 | 端口 |
|------|------|------|------|
| 主工作台 `web/` | Python `http.server` + ES Module SPA | `web/server.py → serve()` | 8913 |
| 审核页 `review/` | Python `http.server` + 单文件 HTML | `review/server.py → serve()` | 8907 |

主工作台用**路由注册表**模式（`handlers.py` 的 `@_register` + 最长前缀匹配），`server.py` 只做薄 HTTP 层；审核页是独立的轻量服务，按 run 的 manifest 启动。

---

## 优点（做得好的地方）

- **后端分层清晰**：`server.py` 薄、`handlers.py` 集中路由、`jobs.py/anchor_jobs.py` 管业务、`cache.py` 管缓存。
- **安全细节到位**：启动任务用 `hmac.compare_digest` 做时序安全密码比对；`/api/files`、`/api/file-preview` 用 `resolve_inside` 做路径 containment；视频支持 `Range` 请求（大文件流式播放）；状态写入用 `.tmp + replace` 原子操作；中间结果有 3s TTL 缓存减少磁盘 I/O。
- **前端工程化**：`app.js` 用 ES Module 拆分 `task/anchor/review/api/state/utils`，事件用**委托** + `window` 暴露给 inline `onclick`，骨架屏、`prefers-color-scheme` 暗色、`:focus-visible`、`backdrop-filter` 都有，交互打磨到位。
- **审核页自包含**：单文件 HTML + 内嵌 CSS/JS，暗色主题、响应式 4 列网格、发布进度轮询，质感不输主站。

---

## 问题与风险（按优先级）

### 🔴 HIGH — review 服务把整个 `runtime/outputs` 当静态目录暴露
`review/server.py` 的 `do_GET` 在匹配完 `/api/*` 后调用 `return super().do_GET()`。
由于 `Handler` 的 `directory` 被设为 `task_root`（即 `runtime/outputs/<数据目录>` 的上两级 = `runtime/outputs`），任何非 API 路径都会由 `SimpleHTTPRequestHandler` 当作静态文件返回。

后果：能访问该端口的人可 `GET /<任意路径>` 直接下载 `runtime/outputs/` 下**所有 run 的视频、manifest、候选图**（含他人的）。服务默认 `0.0.0.0`，若经 Pinggy/公网暴露即数据泄露。

修复：删掉兜底 `super().do_GET()`，未匹配路由统一返回 404。

### 🟠 MEDIUM — 主站 `/static/` 缺少路径 containment
`handlers.py`：`serve_file(handler, STATIC_DIR / path.removeprefix("/static/"))`。
`serve_file` 仅判断 `is_file()`，未校验最终路径仍在 `STATIC_DIR` 内。用原始 `..` 的 HTTP 请求可穿越读取项目内任意文件（浏览器会归一化 `..`，但 `curl --path-as-is`/裸 socket 可绕过）。

修复：在 `serve_file` 开头 `result = path.resolve()`，若 `STATIC_DIR.resolve() not in result.parents` 则 404。

### 🟡 LOW / 建议
- **无全局鉴权**：除"启动生成"有密码外，读任务/看视频/投票/发布（若开启）全开放。内部 LAN 可接受，但上公网前需加一层。
- **两套审核 UI**：主工作台自带 review 视图（`review.js`），`review/` 又是一套独立页面，功能重叠，可考虑合并或明确分工。
- **日志**：`log_message` 只记非 200，正常请求无访问日志，排查问题时盲区较大。

---

## 建议下一步
1. 先修 review server 的 `super().do_GET()` 兜底（1 行改动，高危）。
2. 给 `serve_file` 增加路径 containment 断言。
3. 若计划对外暴露，加一层简单鉴权（反向代理 basic auth 即可）。

> 注：本次仅做静态代码评审，未实际启动服务（需 API key / 工作区配置）。Python `compileall` 与 JS `node --check` 均通过。
