# Changelog

所有值得注意的项目更改都将记录在此文件中。

## [2026-08-14] - 素材管理交互优化、纯音频修复

### 🗂 素材管理交互
- Anchor 获取方式重构为「选择文件 / 现场生成」两个同级操作，现场生成仅针对 Anchor，参考音视频、歌词、约束始终显示
- 现场生成采用「先说明（GPT Image 2）再跳转」的两步交互，跳转后回到 Anchor 页面顶部
- 任务文件夹前置校验：未填写时提示「请先选择任务文件夹」并禁用上传；缺素材时按「图片 / 音视频」分别给出引导
- 空目录提示的操作入口做成**可点击跳转**：「去现场生成」「去上传」直接滚动到对应区域并高亮闪烁，一步到位（不再只是文字说明）
- 「选择文件」默认进入约定子目录（`anchors/`、`references/`），子目录不存在时自动逐级回退到任务根目录
- 选参考音视频时自动过滤 Anchor 图片目录；选 Anchor 时只显示图片
- 选参考音视频后根据所选文件自动切换标签页：全音频 → 🎵 音频，含视频 → 📹 视频
- **切换任务文件夹会清空已选素材、歌词和附加约束，并先弹窗确认**（避免上一个文件夹的内容残留到新文件夹）；确认用自定义弹窗（原生 confirm 在部分环境不显示）
- 编辑纯音频任务自动切 🎵 音频标签页并正确回填

### 📦 文件位置约定
- 上传素材固定落点：图片 → `anchors/`，音视频 → `references/`
- 手动放置素材：任务目录根目录、`anchors/` 或 `references/` 子目录均可被识别（后端按相对路径灵活解析）
- 任务 `file` 字段统一存「相对任务数据目录的路径」，可带子目录前缀或直接是根目录文件名

### 📥 审核下载
- 候选审核说明文案更新为「点视频右下角的 ⋯ 即可下载到本地」，引导用户用播放器自带的下载功能（不再单独加下载按钮）

### 🐛 修复
- 纯音频任务（`pass_reference_video=false`）不再对音频文件执行视频切片（修复 ffmpeg exit 234）
- 空文件夹提示 `hidden` 被 CSS `display:flex` 覆盖导致「请先选择任务文件夹」与「缺少素材」同时显示的 bug
- 提示条初始化未触发检测的 bug（页面加载时正确显示/隐藏提示）
- 文件夹选择器 `folderPickerTarget` 状态残留导致切换任务文件夹失效的 bug
- Prompt 预览区增加关闭按钮 + toggle，修复展开后无法收起；修复浅色模式下预览文字不可见

## [2026-08-13] - 歌词时间戳、深浅色主题、素材选择重构

### 🎤 歌词时间戳（滚动歌词制作）
- 歌词区域新增「制作滚动歌词 >」入口，打开滚动歌词编辑器弹窗
- 支持播放音视频、逐句打时间点（点「添加时间点」或键盘空格播放/暂停、Enter 打点、↑/↓ 切换行、Esc 关闭）
- 音频来源：上传音频直接用；上传视频则自动分离音频（无论「添加音频」是否勾选）
- 后端新增接口：
  - `POST /api/tasks/{id}/extract-audio` — 从任务 references 分离/定位音频
  - `POST /api/extract-audio` — 按文件路径分离音频（不依赖任务是否保存）
  - `GET/POST /api/tasks/{id}/lyrics-timestamps` — 读写歌词时间戳
- 时间戳数据格式：`[{ "text": "歌词", "time": 1.234 }]`，`time` 为播放秒数，未打点为 `null`
- 时间戳已集成到 prompt 生成（`build_prompt` 新增 `lyrics_timestamps` 参数）：无有效时间戳走普通歌词；全部有时间逐句输出 `时间+歌词`；部分有时间先写完整歌词再列已标注时间点
- 未保存任务也可打点，时间戳暂存内存，随任务保存一并写入
- `models.py`/`store.py` 支持 `lyrics_timestamps` 字段透传
- 歌词编辑器交互：
  - 弹窗内固定头部（播放器 + 「添加时间点」），歌词列表独立滚动
  - 播放时自动定位到当前时间对应的已打点句子，滚动到第二行
  - 点击已打点句子 → 跳转定位（不清空）；每句右侧「↺」重打按钮 → 只重打该句（清空该句时间点）
  - 「↺」重打时从上一句开始播放（留缓冲），高亮定位到该句；第一句从音频开头播放
  - 打点只覆盖当前句时间点，不影响其它句
  - 顶部帮助 tips 分条展示，说明打点/跳转/重打操作
  - 「添加时间点」未播放时点击 = 打当前时间点（如第一句 0s）+ 自动播放，播放中点击 = 打点并跳下一句

### 🌗 深浅色主题
- 顶部导航栏新增主题切换按钮（🌙/☀️），点击即时切换深浅色，选择存入 `localStorage`
- 颜色方案从 `@media(prefers-color-scheme:dark)` 改为 `html[data-theme="dark"]`，首次打开跟随系统偏好
- 深色模式补全：导航栏选项、`.text-button`、`.help-tip` 问号、歌词列表、歌词弹窗等元素的颜色适配

### 📦 素材选择重构
- Anchor 与参考音视频从「可编辑 textarea」改为「标签 chips + 预览」展示
- 每个已选文件支持「✕」取消选中（chips 和预览图两处均可），只移除列表、不删除磁盘文件
- 「选择参考视频」默认进入 `references/` 子目录，标题改为「选择参考音视频」，过滤补充音频格式（mp3/wav/m4a/aac/flac/ogg）
- 预览区区分音频（`<audio>`）/视频（`<video>`）
- 任务列表卡片新增配置 chips：模式、时长对齐、音视频传入、时间戳句数、候选数，核心配置直观展示

### 🐛 修复
- **上传素材**：`X-Task-Id` 中文编码问题（`encodeURIComponent` + `unquote`），修复中文任务文件夹上传落错目录（乱码目录）
- **上传状态**：上传成功后清空文件选择框、状态「完成」3 秒后自动清空，支持连续上传
- **保存/提交校验**：保存任务允许 anchor/参考音视频为空，校验移到「启动生成」时（前端 + 后端 `runner.validate()` 双重校验）
- **编辑同名任务**：`saveTask` 修复编辑已有任务（未改名）时误报「同名任务已存在」，现正确走更新逻辑
- **审核页下载按钮**：去掉重复的自定义下载按钮，仅保留 `<video controls>` 原生下载
- **Anchor 优化面板**：`<details>` 折叠改普通 div，说明直接显示，消除 toggle 错位
- **UI 修复**：歌词区/「智能解析」按钮与输入框重叠、`.help-btn` 未定义的 `--border` 变量、`flex:1` 导致 textarea 高度失控

### ⏱ 时间戳 offset 与时长对齐（设计：Prompt_Design.md V2.2）
- `build_prompt` 新增 `timestamp_offset` 参数：仅 `pad_mode=front` 且未超时长时，时间戳需加 `ceil(total)-total` 的偏移
- `_timestamp_offset()`（factory.py）：offset 只在前补齐时需要；`none`/`back` 为 0；超时长（> max_duration）必为 0
- 超时长归一化（runner.py `_segments`）：视频超模型上限时，`pad_mode` 归一为 `none`，直接截断，不再走补齐逻辑
- 「补齐 → offset → 裁剪」三处共用同一量 `Δ = seedance_duration - original_total`，逻辑自洽（详见 Prompt_Design.md §2.4.1）

### 🔍 生成决策日志
- 新增 `job-decisions` 日志（runner.py）：记录每个 (anchor, ref, prompt) 的 pad_mode、pass_video/pass_audio、`audio_passed_to_seedance`（音频是否真正传给 Seedance）、素材角色 roles、duration、timestamp_offset
- 新增 `timestamp-offset` 日志（factory.py）：记录 pad_mode、原始时长、seedance_duration、最终 offset
- 便于排查「传了视频没勾音频是否误传音频」「pad_mode/offset 计算是否正确」等决策问题

## [2026-08-12] - 提交密码 HMAC 化、凭据清理、文档完善

### 🔐 提交密码机制改造
- 明文密码 `VIDEO_SUBMIT_PASSWORD` 改为 `VIDEO_SUBMIT_SECRET` + `VIDEO_SUBMIT_HASH`（HMAC-SHA256）
- 新增 `scripts/gen_password.py`：输入明文密码，生成盐+哈希写入 `.env`，`.env` 不存明文
- `config.py` 新增 `verify_submit_password()`，用 `hmac.compare_digest` 恒时比对
- 未配置密钥时返回明确错误提示，而非模糊的"密码错误"
- 密码定位：防误触 + 防没有 `.env` 权限的访问者；两层授权（.env 部署权限 + 密码提交权限）

### 🔒 凭据安全
- `credentials.py` 移除硬编码的真实 API Key，强制从 `.env` 读取，缺 key 抛错
- `client.py` 的 `_select_api_key` 增加缺 key 校验
- 清理文档中的真实提交密码（QUICK_REFERENCE、docs/README）

### 📄 文档完善
- README 新增「核心设计概念」章节（三层数据组织、Anchor 设计、三种模式、时长对齐、Prompt 架构）+ 具体文档引用
- DEPLOYMENT 补充提交密码机制说明，修正过时的 `PHANROUTER_API_KEY`
- 修正 CHANGELOG 错误日期（2024-12 → 2026-08）
- Pinggy 文档澄清：素材隧道自动按需启动，`start-pinggy.sh` 仅用于暴露工作台网页

## [2026-08-12] - 音视频传入重构、帮助系统、表单提交修复、时长对齐

### 🎬 音视频传入逻辑（三种模式）
- `ReferenceSpec` 新增 `pass_reference_video` 字段，支持"只传音频不对口型"（纯音频驱动）
- 三种生成模式的素材传入策略：
  - `lip_sync`（纯对口型）：可选视频/音频。📹 视频 tab = 视频驱动；🎵 音频 tab = 纯音频驱动；勾"传参考音频" = 从视频提取音频，音视频驱动
  - `dance_lip_sync`（口型+动作）：强制传视频，音频可选（从视频提取，默认勾选）
  - `motion`（模仿动作）：强制传视频，不传音频（隐藏音频选项）
- prompt 根据是否有音频/视频参考动态调整约束（`has_video_ref` 参数）
- ref-tabs 交互优化：音频 tab 下隐藏"传参考音频"和"时长对齐"；编辑任务默认切回视频 tab；motion 模式隐藏音频 tab

### ❓ 帮助系统
- 导航栏新增"❓ 帮助"按钮，打开操作指南弹窗（三种模式、对口型驱动方式、时长对齐、运行/审核等）
- 新增通用 `help-tip` 组件（问号图标 + 悬浮 tooltip），加在关键选项旁：生成方向、候选数、传参考音频、时长对齐、提交密码
- 纯 CSS tooltip 实现（`[data-help]:hover::after`），不依赖 JS

### 🔧 表单提交修复
- **修复**：`task-form` / `anchor-form` 的 `type=submit` 按钮未绑定 submit 事件，点击只刷新页面、不触发保存逻辑（新任务和编辑任务都无法真正保存）
- 在 `init()` 中为两个 form 绑定 submit 事件 → `saveTask` / `saveAnchorTask`

### 🎬 时长对齐模式（pad_mode）

### 🎬 时长对齐模式（pad_mode）
- 参考音视频新增"时长对齐"选择器，支持三种模式：
  - `back`（默认）：在视频/音频**后面**补帧/静音到 ceil 时长
  - `front`：在视频/音频**前面**补帧/静音到 ceil 时长
  - `none`：不补齐，使用原始时长提交
- `media.py`：`trim_reference` 和 `pad_audio_to` 统一用 `pad_mode` 参数
- `runner.py`：`_segments` 返回 pad_mode，`_finish_job` 根据 pad_mode 裁掉 padding 再回灌音频
- `models.py`：`ReferenceSpec` 新增 `pad_mode` 字段
- `factory.py`：构造 `ReferenceSpec` 时传入 `pad_mode`

### 🔧 Pinggy 隧道稳定性
- 去掉 `+force` 模式，避免 SSH 被服务端拒绝（`Connection closed`）
- `tunnel.start()` 全新启动时重试 3 次，每次间隔 5 秒
- `runner.upload()` 去掉事前 `_reachable` 检查，改为 `create_asset` 失败后重建隧道重试（3 次）
- `tunnel.start()` 不可达时清理 `TUNNEL_STATE` 文件 + 重置状态，确保全新启动

### 🎨 UI 优化
- 参考音视频区域：ref-tabs 和"选择文件"按钮合并到 `.field-title` 行
- 新增"时长对齐"选择器（pad-mode-row）
- "传参考音频" checkbox 文案修正（原"口型同步"语义不准确）
- 编辑已有任务时不再强制覆盖 `pass_reference_audio`（`updateMode` 去掉 `cb.checked = true`）
- anchor 和参考音视频 textarea 统一 `min-height: 80px`
- 下载按钮改为图标按钮（SVG），去掉文字
- `.ref-tab.active` 和 `.run-resume` 改用蓝色 `#2563eb`，解决深色背景看不清问题
- 审核页面自动选中最近的任务

### 🔒 安全
- `serve_file` 新增 `root` 参数，`/static/` 路径穿越防护
- 删除独立 review 服务（`review/server.py` + `review/static/index.html`）
- 删除 `debug.html`

### 🐛 修复
- Seedance submit 遇到 "asset is still processing" 时自动等待重试（4 次，每次 10 秒）
- 编辑已有任务时 `pass_reference_audio` 被 `updateMode` 覆盖
- `.env.example` 清理旧的 `PHANROUTER_` 前缀变量
- `run.py` 移除 `video review` 子命令

## [2026-08-12] - 实时审核、Prompt 重构、文件整理

### 🎬 审核实时预览
- Runner 每个 job 完成时增量写入 manifest，审核页面可实时看到已完成的候选视频
- 审核 tab 自动选中第一个可审核 run
- run 卡片点击直接跳转审核页（Anchor run 同理）
- 审核轮询自动检测 run 状态，生成中每 3 秒刷新 manifest

### 🗑️ 删除功能完善
- 自定义确认弹窗（替换原生 confirm），显示任务详情
- 支持"同时删除本地生成文件"选项
- 后端 `remove_files` 参数清理 `runtime/outputs/` 和 `runtime/work/`
- Task 删除支持级联清理关联 runs

### 📝 Prompt 重构
- 五层架构：全局约束 → 一致性 → 视频参考 → 音频参考 → 歌词/自定义
- 新增全局约束：固定镜头、背景稳定性、AI 痕迹
- 参考音频上传改为可选（对口型模式默认开启，纯动作模式隐藏）
- Prompt 设计文档：`docs/guides/Prompt_Design.md`

### 🔄 断点恢复
- 服务重启后自动 resume 已提交到 Seedance 的 run（不再直接标 failed）
- 前端恢复按钮：`can_resume` 检测 `run.json` 是否存在
- `start-daemon.sh` 添加 `/usr/local/bin` 到 PATH（修复 ffprobe 找不到）

### 📂 文档整理
- `docs/` 重组：指南移入 `guides/`，删除过时文档
- `docs/README.md` 索引重写

### 🐛 修复
- 审核页面 race condition（DOM vs store 取值不一致导致视频灰屏）
- 审核轮询覆盖旧数据
- 删除弹窗 DOMContentLoaded 事件在 ES module 中不触发 → 删除按钮失效
- 删除确认弹窗排版、启动弹窗排版、run 卡片"查看审核"提示与进度条重叠
- Anchor 候选图片路径修复（旧 manifest 路径自动修正）
- Pinggy 隧道稳定性：去掉 `+force` 模式避免 SSH 被拒；`start()` 和 upload 阶段均加重试（3 次 + 重建隧道），失败自动恢复

### 🔧 时长对齐
- 视频/音频自动向上取整到整数秒，末尾补帧/补静音保持一致
- 视频用 `tpad=stop_mode=clone` 末尾补帧，音频用 `apad=whole_dur` 补静音
- mux 阶段用原始音频回灌，自然裁回原始长度

### 📦 Asset 管理
- Asset 面板在任务卡片下方内联展开，点击 toggle 开/关
- 每条 asset 可单独清除缓存，避免删除全部
- 参考音视频改为 📹/🎵 标签页切换

### 🎨 审核简化
- 去掉推荐/不推荐投票按钮和发布功能
- 下载按钮改为蓝色圆角样式

---

## [2026-08-11] - Anchor 与 Video 任务架构统一

### 🏗️ 架构重大重构

#### Anchor 任务归属于数据目录
- **之前**：Anchor 任务独立存储在 `data/anchor-xxx/` 目录，与 Video 任务无关联
- **现在**：Anchor 任务归属于数据目录，存储在 `data/<目录>/anchors/anchor-task.json`
- Anchor task_id = 数据目录名（如 `马路风`）
- 生成的候选图和精选图都在同目录下，Video 任务可直接引用

#### 统一的目录结构
```
data/<数据目录>/
├── anchors/                     ← Anchor 模块
│   ├── anchor-task.json         ← Anchor 任务配置
│   ├── anchor-references/       ← 参考图片
│   ├── generated/<run_id>/      ← 生成候选
│   └── selected/                ← promote 后的精选图（Video 任务从这里选）
├── tasks/                       ← Video 任务配置（可有多个）
│   ├── 唱歌版.json
│   └── 跳舞版.json
├── *.mov, *.jpg                 ← 原始素材
└── seedance/assets.json         ← 远程资源 ID（共享）
```

#### promote 流程简化
- **之前**：promote 时需要手动指定 `video_task_id`，跨目录拷贝图片，调用 `append_anchor` 修改视频任务
- **现在**：promote 只需拷贝到 `data/<目录>/anchors/selected/`，Video 任务通过 asset picker 直接从该目录选图

#### Video 任务输出目录用数据目录名
- **之前**：`runtime/outputs/<task_name>/<run_id>/`
- **现在**：`runtime/outputs/<data_dir>/<run_id>/`（同一数据目录的多个任务共享输出路径前缀）

### 🔧 功能改进

#### 1. Anchor 表单新增"数据目录"字段
- 替代原来的"任务 ID"字段，通过文件夹选择器选取
- 任务名称独立保留，用于显示

#### 2. Video 任务选 Anchor 图默认从 `anchors/selected/` 选
- asset picker 检测到 anchors 类别时自动导航到 selected 子目录

#### 3. Anchor 中断状态改为 failed
- 和 Video 任务统一，不再有 `interrupted` 状态
- 移除 Anchor 的 resume 概念

### 📁 文件变更
- `idolmv_pipeline/image_tasks/store.py` — AnchorTaskStore 重写，task_id = data_dir
- `idolmv_pipeline/image_tasks/models.py` — AnchorTask.from_dict 移除 normalize_task_id 依赖
- `idolmv_pipeline/video_tasks/factory.py` — output_dir/work_dir 用 data_dir
- `idolmv_pipeline/web/handlers.py` — promote 逻辑简化
- `idolmv_pipeline/web/anchor_jobs.py` — 中断状态改为 failed
- `idolmv_pipeline/web/static/modules/anchor.js` — 表单/列表/promote 适配
- `idolmv_pipeline/web/static/modules/task.js` — asset picker 默认到 selected/
- `idolmv_pipeline/web/static/index.html` — Anchor 表单字段调整

### 📚 文档更新
- 更新 `docs/VIDEO_LOCATIONS.md`、`docs/guides/Video_Task_Workflow.md`、`docs/DEPLOYMENT.md`
- 更新 `QUICK_REFERENCE.md`、`templates/video_task/README.md`

---

## [2026-08-11] - 任务名称与数据目录解耦

### 🏗️ 重大变更

#### 任务名称独立于文件夹
- **之前**：任务 ID = 任务名称 = 数据文件夹名，三者绑定无法拆分
- **现在**：同一数据目录可创建多个不同任务（如 `马路风/唱歌版`、`马路风/跳舞版`）
- 表单新增独立"任务名称"输入框，与"任务文件夹"字段完全分离
- 任务 ID 采用 `数据目录__任务名称` 组合格式（如 `马路风__唱歌版`）
- 存储路径调整：`data/<目录>/task.json` → `data/<目录>/tasks/<名称>.json`
- 旧格式自动迁移，无需手动操作

### 🔧 功能修复

#### 1. 删除按钮改用 inline onclick
- 任务卡片和运行记录的删除按钮改用 `onclick` 直接绑定，不再依赖事件委托
- 根除模块化后事件委托偶尔不触发的问题

#### 2. 移除"恢复"功能
- 运行中断后直接标记为 `failed`，不再显示无效的"恢复"按钮
- 删除后端 `resume` 路由和 `JobManager.resume()` 方法
- 前端移除 `resumeRun` 函数和恢复按钮 UI

#### 3. nini 运行恢复
- 修复了因服务重启 + ffmpeg PATH 问题导致 mux 音频失败的 8 个候选视频
- 视频已成功下载，补做完音频回灌后全部修复

### 📁 文件变更
- `idolmv_pipeline/video_tasks/store.py` — 支持多任务存储，automatic migration
- `idolmv_pipeline/web/static/index.html` — 新增"任务名称"字段
- `idolmv_pipeline/web/static/modules/task.js` — 适配 name + data_dir 分离
- `idolmv_pipeline/web/jobs.py` — 移除 resume 方法
- `idolmv_pipeline/web/handlers.py` — 移除 resume 路由

### 📚 文档更新
- 更新 `docs/VIDEO_LOCATIONS.md`、`docs/guides/Video_Task_Workflow.md`、`docs/DEPLOYMENT.md` 中的任务存储结构
- 更新 `CHANGELOG.md`

---

## [2026-08-10] - 重要修复和功能增强

### 新增功能 ✨

#### 1. 智能表单自动填充 🆕
- 任务创建表单现在支持智能自动填充
- **只需填写任意一个字段**（任务名称/任务 ID/发布前缀），其他字段自动填充
- 支持手动修改任何字段，修改后该字段不再自动填充
- ID 自动规范化：小写、特殊字符转 `-`、保留中文
- Anchor 生成器同样支持（任务名称 ↔ 任务 ID）
- 详细说明：[docs/UI_IMPROVEMENTS.md](docs/UI_IMPROVEMENTS.md)

**使用示例**:
```
输入"任务名称"：ruins
自动填充：
- 任务 ID: ruins
- 前缀: ruins
```

#### 2. 中间结果实时查看
- 新增 API 端点 `GET /api/runs/{run_id}/intermediate`
- 新增简化访问路径 `GET /api/intermediate/{run_id}`
- 可在生成过程中实时查看：
  - 当前进度 (已完成/总数)
  - 每个子任务的状态和消息
  - 已生成的视频文件列表
  - 视频文件大小和路径信息
- 支持轮询更新，建议间隔 5-10 秒
- 详细文档：[docs/INTERMEDIATE_RESULTS.md](docs/INTERMEDIATE_RESULTS.md)

**使用示例**:
```bash
curl http://127.0.0.1:8913/api/runs/run_20241210_153045/intermediate
```

**返回数据**:
```json
{
  "run_id": "run_20241210_153045",
  "status": "running",
  "stage": "generating",
  "completed": 3,
  "total": 10,
  "intermediates": [
    {
      "job_name": "anchor01_ref01_var01",
      "state": "done",
      "video_count": 2,
      "videos": [...]
    }
  ]
}
```

### 问题修复 🐛

#### 1. BrokenPipeError 错误修复
- **问题**: 浏览器取消预览/下载时服务器日志出现大量 `BrokenPipeError: [Errno 32] Broken pipe` 错误
- **影响**: 污染日志，影响日志可读性
- **修复**: 在 `serve_file()` 方法中捕获 `BrokenPipeError` 和 `ConnectionResetError`
- **效果**: 客户端断开连接时优雅处理，不再输出错误日志
- **文件**: `idolmv_pipeline/web/server.py`

#### 2. Pinggy Tunnel 启动优化
- **问题**: Tunnel URL 匹配超时，启动失败后尝试 ngrok (未安装)
- **影响**: 提交任务时报错 `Unable to start tunnel: [Errno 2] No such file or directory: 'ngrok'`
- **修复**:
  - 增加超时时间从 30 秒到 60 秒
  - 改进正则表达式匹配 Pinggy 域名变体：
    - `*.free.pinggy.net`
    - `*.run.pinggy-free.link`
    - `*.a.free.pinggy.link`
  - 移除 ngrok 后备方案，专注使用 Pinggy
  - 优化错误消息，包含日志输出
- **效果**: Tunnel 启动更快更稳定
- **文件**: `idolmv_pipeline/seedance/tunnel.py`

#### 3. 环境变量自动加载
- **问题**: 需要手动设置环境变量才能使用密码功能
- **影响**: 提交任务时报"提交密码错误"
- **修复**: `start.sh` 现在自动加载 `.env` 文件
- **效果**: 
  - `VIDEO_SUBMIT_PASSWORD` 自动生效
  - `PINGGY_TOKEN` 自动生效
  - 所有 API keys 自动加载
- **文件**: `start.sh`

### 改进 🚀

#### 1. 表单用户体验优化
- 添加智能提示：只需填写任意一个字段
- 更新 placeholder 文本为"自动生成或手动输入"
- 实时反馈自动填充结果
- 保持灵活性：所有字段都可手动修改

#### 2. 启动脚本优化
- **start.sh**:
  - 自动检测并使用当前 conda/virtualenv 环境
  - 自动加载 `.env` 文件（使用 `set -a; . .env; set +a`）
  - 不再创建或激活 `.venv` 虚拟环境
  - 保持向后兼容

- **setup.sh**:
  - 直接在当前环境安装依赖
  - 不再创建虚拟环境
  - 更快的安装过程

### 技术细节 📋

#### 中间结果检测逻辑
1. 扫描任务输出目录：`outputs/{run_id}/`
2. 查找所有 `*/seedance/` 子目录
3. 读取每个目录的：
   - `state.json` - 任务状态
   - `assets.json` - 资源信息
   - `*.mp4` - 视频文件
4. 按修改时间排序，返回汇总结果

#### 目录结构
```
outputs/
└── run_20241210_153045/
    ├── anchor01_ref01_var01/
    │   └── seedance/
    │       ├── state.json
    │       ├── assets.json
    │       ├── output_00.mp4
    │       └── output_01.mp4
    ├── anchor01_ref01_var02/
    │   └── seedance/
    │       └── state.json
    └── review_manifest.json (完成后生成)
```

### 已知问题和注意事项 ⚠️

1. **中间结果 API 性能**
   - 扫描文件系统有开销，不建议频繁调用
   - 推荐轮询间隔：5-10 秒
   - 任务完成后应停止轮询

2. **BrokenPipeError 处理**
   - 已优雅处理，不影响服务器运行
   - 属于正常的客户端断开行为

3. **Pinggy Token**
   - 免费版 token 长期有效
   - URL 会在每次连接时变化
   - 需要在 `.env` 中配置 `PINGGY_TOKEN`

### 文档更新 📚

- 新增：`docs/UI_IMPROVEMENTS.md` - 智能表单自动填充功能说明 🆕
- 新增：`docs/VIDEO_LOCATIONS.md` - 中间结果查看功能详细说明
- 更新：`README.md` - 添加新功能和修复说明
- 新增：`CHANGELOG.md` - 项目变更日志

### 升级指南 ⬆️

如果从旧版本升级：

1. **拉取最新代码**:
   ```bash
   git pull
   ```

2. **确保 .env 文件正确配置**:
   ```bash
   # 检查必需的环境变量
   grep -E "VIDEO_SUBMIT_PASSWORD|PINGGY_TOKEN" .env
   ```

3. **重启服务**:
   ```bash
   # 停止旧服务
   pkill -f "run.py video web"
   
   # 启动新服务
   ./start.sh
   ```

4. **验证修复**:
   ```bash
   # 测试健康检查
   curl http://127.0.0.1:8913/api/settings/public
   
   # 测试中间结果 API (需要有正在运行的任务)
   curl http://127.0.0.1:8913/api/runs
   ```

### 贡献者 👥

感谢所有为本次更新做出贡献的人员。

---

## [2026-08-09] - Anchor-based Reference Mapping 架构升级

### 🏗️ 架构重大变更

#### Image Role → Anchor Role 转型
- **之前**：图片被分配固定角色（图1=身份，图2=场景，图3=服装）
- **现在**：每个视觉属性独立映射到来源图，一张图可同时提供多个属性
- 支持 7 大类 Anchor Taxonomy：Subject / Appearance / Environment / Objects / Composition / Photography / Edit
- 支持 7 种操作语义：preserve / transfer / match / remove / replace / add / modify
- 每条 Anchor 携带 source + operation + priority 三元组

### ✨ 新增功能

#### 1. Optimizer 全面重构
- 关键词正则规则增强非贪婪匹配 + 跨分句保护
- identity 锁定机制（priority=critical，source 不可覆盖）
- 自动注入 GLOBAL_DEFAULTS（body_proportion, camera_style, realism）
- 独立物体识别：狗、椅子、手机、吉他、花、包、车等
- 场景物体 + 编辑操作联合解析
- **文件**: `idolmv_pipeline/image_tasks/optimizer.py`

#### 2. 前端映射表展示
- Optimizer 面板新增 Anchor 映射表（按类别分组）
- 操作标签颜色编码（preserve=绿, transfer=蓝, match=黄, remove=红）
- 优先级标签（critical=红, high=黄, medium=灰, low=浅灰）
- 独立物体识别列表展示
- **文件**: `index.html`, `modules/anchor.js`, `app.css`

### 📚 文档新增
- `docs/ANCHOR_REFERENCE_MAPPING.md` — 设计文档（Taxonomy、数据模型、流水线、扩展指南）
- `docs/guides/Optimizer_Guide.md` — 使用指南（关键词模式、操作流程、示例）

---

## [2026-08-11] - UI/UX 全面升级 & 交互修复

### 🔧 关键修复

#### 1. 动态按钮事件绑定修复
- **问题**: 模块化拆分后，所有动态渲染的按钮（任务列表/Anchor列表/审核卡片/工具栏）失去事件绑定，变成"死按钮"
- **修复**: 统一使用 `data-action` 属性 + 事件委托系统，所有按钮恢复正常：
  - 任务列表：Assets / 编辑 / 运行
  - Anchor 任务列表：编辑 / 生成
  - 视频审核：推荐 / 不推荐 / 发布已选
  - Anchor 审核：推荐 / 不推荐 / 设为 Anchor / 批量推介
  - 工具栏：按当前配置再生成一批
- **文件**: `app.js`, `modules/task.js`, `modules/anchor.js`

### ✨ UI 视觉升级

#### 1. 主站 CSS 增强
- 卡片 hover 悬浮效果 (`translateY` + 阴影扩散)
- 视图切换渐入动画 (`opacity` + `translateY` 过渡)
- 按钮 hover/active 微交互反馈
- 进度条 shimmer 流动光泽动画
- 骨架屏 pulse 呼吸加载动画
- 毛玻璃面板增强 (`backdrop-filter: blur(22px)`)
- 选中卡片发光边框效果
- 自定义滚动条样式
- Modal 弹窗渐入动画
- Focus ring 焦点环
- **文件**: `app.css`

#### 2. 审核页视觉统一
- 深色主题与主站风格统一（紫/靛蓝渐变配色）
- 玻璃拟态卡片 + hover 悬浮
- 面包屑过滤按钮（pill 风格）
- 发布按钮绿色突出显示
- Toast 通知渐入动画
- 发布区独立面板
- **文件**: `review/static/index.html`

### 🆕 新增功能

#### 1. 加载状态 & 骨架屏
- `renderSkeleton(type, count)` — 骨架屏渲染（list/video-grid/image-grid）
- `renderEmptyState(icon, msg, hint)` — 空状态引导占位组件
- `showLoading/hideLoading` — 加载状态管理
- **文件**: `modules/utils.js`

#### 2. 空状态优化
- 任务列表/运行记录/Anchor 列表无数据时显示引导性空状态
- 带图标和提示文案，替代单调的灰色文字

### 📁 新增文件
- `idolmv_pipeline/web/cache.py`
- `idolmv_pipeline/web/handlers.py`
- `idolmv_pipeline/web/logging.py`
- `idolmv_pipeline/web/static/modules/` (前端模块化拆分)

### 📚 文档更新
- 更新 `CHANGELOG.md` - 记录 UI/UX 升级
- 更新 `QUICK_REFERENCE.md` - 补充 Anchor 功能说明

---

## [2026-08-11] - Anchor 功能完善 & 交互优化

### 🔧 关键修复

#### 1. 路由分发顺序修复
- **问题**: `dispatch()` 按注册顺序匹配，catch-all "/" 在 API 路由之前，导致所有 API 请求返回 HTML
- **修复**: 路由按路径长度降序排序，确保长路径（`/api/tasks/`）优先于短路径（`"/"`）
- **文件**: `idolmv_pipeline/web/handlers.py`

#### 2. ES Module 导入修复
- **问题**: `onAspectSourceChange` 未从 `anchor.js` 导入，导致 `ReferenceError` 阻断整个页面 JS 执行
- **修复**: 在 `app.js` 的 import 中补充导入
- **文件**: `idolmv_pipeline/web/static/app.js`

#### 3. 步骤3参考图勾选失效
- **问题**: `renderAnchorReferences()` 读取步骤4下拉时额外检查 checkbox 状态，导致未预先勾选的 scene/lighting 被过滤
- **修复**: 移除多余的 `checkbox.checked` 检查，使所有来源图绑定正确回显
- **文件**: `idolmv_pipeline/web/static/modules/anchor.js`

### ✨ 新增功能

#### 1. 画质/风格预设标签 & 禁止项标签
- 步骤5「补充描述」新增两套标签式快捷选择：
  - **画质/风格标签**（8项）：真实iPhone手机拍摄画面、电影级光影大片、柔光ins风、复古胶片风、棚拍商业质感、极简干净白底、高定时尚杂志风、日系清透感
  - **禁止项标签**（8项）：不要水印/文字、不要畸形手/手指、不要多余人/路人、不要模糊/失焦、不要过度修图/塑料感、不要低画质/噪点、不要裁剪异常、不要曝光过度
- 点击标签即选中/取消，多选叠加，最终与手动输入文本合并生成完整 prompt
- **后端**: `prompts.py` 新增 `QUALITY_PRESETS` 和 `NEGATIVE_PRESETS`
- **前端**: 新增 `renderAnchorQualityPresets()`, `renderAnchorNegativePresets()`, `togglePresetTag()`, `buildPresetText()` 函数
- **文件**: `idolmv_pipeline/image_tasks/prompts.py`, `index.html`, `anchor.js`, `app.css`

#### 2. 参考图展开绑定
- 每张参考图卡片可展开（点击箭头图标），展开区显示该图可提供的所有参考点复选框
- 直接在参考图上勾选/取消参考点，自动同步到步骤4的下拉选择
- 新增 `toggleRefExpand()` / `toggleRefAspectBinding()` 函数
- **文件**: `anchor.js`, `app.css`, `index.html`

#### 3. 面板顺序优化
- 将步骤3（原"参考图片上传"）与步骤4（原"选择参考点与来源图"）互换
- 新顺序：先上传参考图 → 再展开绑定参考点，符合直觉操作流程
- **文件**: `index.html`

#### 4. Anchor 任务删除功能
- 支持从任务列表直接删除不需要的 Anchor 任务（含所有关联资产）
- **后端**: `AnchorTaskStore.delete()` + `DELETE /api/anchor-tasks/` 路由
- **前端**: 任务列表添加红色删除按钮 + `deleteAnchorTask()` 函数
- **文件**: `store.py`, `handlers.py`, `api.js`, `anchor.js`, `app.css`

#### 5. 任务ID自动生成
- 任务ID字段改为可选（移除 required），留空时自动生成时间戳ID
- 保存后自动回写生成的ID到表单，确保前端能正确读取
- **文件**: `index.html`, `anchor.js`

#### 6. 保存后自动滚动
- `saveAnchorTask()` 完成后自动滚动到任务列表，让用户确认保存结果
- **文件**: `anchor.js`

#### 7. "头小肩宽"预设
- 在构图/镜头预设中添加 `small_head_wide_shoulders` 选项
- **文件**: `idolmv_pipeline/image_tasks/prompts.py`

### 📚 文档更新
- 更新 `CHANGELOG.md` - 记录 Anchor 功能完善
- 更新 `QUICK_REFERENCE.md` - 补充新功能说明
- 更新 `docs/guides/Optimizer_Guide.md` - 修正步骤顺序、补充预设标签说明

---

## 历史版本

更早的更改未记录。本 CHANGELOG 从 2026-08-10 开始维护。
