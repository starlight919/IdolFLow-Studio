# Changelog

所有值得注意的项目更改都将记录在此文件中。

## [2026-08-16] - 路线图收敛为保守版 + 前后端逻辑漏洞修复

### 🗺️ 路线图收敛（`Asset_Library_Roadmap.md` v2）
- **放弃近期实施全局素材库重构**：不引入 SQLite / `data/_asset_library/` / LocationResolver / `revision_id`，**不重设计 location、不迁移任何数据路径**——现有 `data/<文件夹>/` + `runtime/work` + `runtime/outputs` 布局与文档一致、运行良好，全局库划不来，改为远期可选方向
- 新路线：修 bug（本次）→ 不动布局的小增强（按需）→ 只读素材总览页（按需）

### 🐛 后端修复
- **`adapter_from_task` 解析 task_dir 用 task id 而非 data_dir**：`id != data_dir` 的任务会找错素材目录（`factory.py`）
- **`clear_assets` 子串匹配误伤**：`category in k` 会连带删除含相同子串的其他键（如 reference 名含 "audio"），改为精确匹配主键 + `__source/__transform` 边车键（`store.py`）
- **`list()` 排序 stat 竞态**：glob 与排序之间任务文件被删除会让任务列表 500，`_safe_mtime` 兜底（`store.py`）
- **`pass_reference_audio=false` 仍规划/上传音频**：motion 模式或手动关闭时不传音频却仍上传（浪费且面板出现无用行），`_plan_all` 跳过（`runner.py`）
- **音频源缺失时残留过期指纹标记**：源不存在时清掉 `audio.src.json`，避免残留指纹误判缓存有效（`runner.py`）

### 🐛 前端修复（`task.js`）
- **独立音频按索引配对错位（最重要）**：`editTask` 回填 `audio_file` 时 `filter(Boolean)` 丢空位、`formTask` 按行号配对 → 编辑再保存会把音频挂到错误的视频；现按 reference 顺序生成含空行占位的 `#audio-refs`，`formTask` 用原始行配对，音频多于视频时报错而非静默丢弃；chips 移除音频也改为空行占位保持对齐
- **嵌套任务文件夹被截断**：`editTask` 用 `data_dir`（末级目录名）回填 `#task-dir`，嵌套路径保存后任务跑错位置；改为从 `task_dir` 剥 `data_root` 前缀还原完整相对路径
- **更新任务先删后存可能丢数据**：改为先保存新任务成功再删旧任务，校验失败不再连带丢旧任务
- **`resetForm` 残留音频 tab**：上次编辑纯音频任务后新建，表单停留音频 tab 导致误存纯音频任务；重置时切回视频 tab
- **「启动」遇改名断头路**：`_pendingStart` 此前没人接住；保存方式弹窗成功后接续 `requestStart`
- **素材选择覆盖 vs 上传追加不一致**：`confirmAssetSelection` 统一为合并去重（音频优先填空占位行），不再覆盖丢已有项
- **`checkMissingAssets` 吞错**：服务异常时显示「检测失败」横幅而非静默消失
- **切换任务文件夹残留编辑态**：清空素材后同步清 `currentTask` / `originalPadMode`，重置按钮与保存弹窗行为一致

### 🐛 音频复用误判修复（`runner.py`）
- **`_inspect_audio` 源标记按产物选择**：判断音频产物是否有效时，源标记按「实际要上传的产物」选择——补齐时长（`audio_padded`）读 `audio_padded.src.json`，否则读 `audio.src.json`。修复中途临时切源（如用某视频提取音频）污染 `audio.src.json` 后改回原音频源，却被误判产物失效、要求重新上传的问题（冻结-街道风场景）

### ✨ 交互体验增强
- **上传类型自动归类**：选完文件后「上传类型」下拉框按文件类型自动切换（音视频→参考音视频，图片→Anchor 图片），不再等点「上传素材」才变
- **选择文件弹窗类型标签**：参考音视频列表每个文件带类型标签（🎵 音频 / 🎬 视频），一眼分辨归位，选完自动切 tab
- **统一音频扩展名判断**：新增 `AUDIO_EXTENSIONS` + `isAudioName`，补 `aiff/opus/wma`、兼容大写扩展名，消除 upload/confirm/browse 三处正则不一致
- **补齐 disabled 逻辑**：任务列表缺素材禁「运行」、Anchor 未选目录禁上传、`#upload-category` 随目录禁用、智能解析结果失效复位「应用解析结果」、添加时间点缺歌词禁用、`openAssetPicker` 未选目录不打开
- **歌词必填校验**：`lip_sync` / `dance_lip_sync` 启动生成前校验歌词，未填立即提示、不进生成（保存草稿不强制）
- **disabled 控件加 title 提示**：禁用时悬浮显示原因（「请先选择任务文件夹」等），操作指南同步补充

### 📄 文档
- `Asset_Design.md` 升至 V1.4：设计边界新增「不传参考音频则不规划音频资产」「清缓存按键精确匹配」「音频源标记按产物选择」
- `Video_Task_Workflow.md` / `Singing_Video_Guide.md`：补充上传自动归类、类型标签、歌词必填、disabled 前置校验、任务列表运行禁用等交互说明

## [2026-08-15] - Asset 面板源文件变化标记 / 可编辑 Prompt / 参考音视频预览 / 排序优化

### ✍️ 可编辑 Prompt
- 「预览 Prompt」由只读 `<pre>` 改为可直接编辑的 `<textarea>`：未编辑即自动模式（按七层架构自动生成，附加约束仍追加在末尾）；手动编辑即视为「自定义 Prompt」，保存/生成时整段使用用户文本，不再叠加歌词、时间戳、附加约束等自动拼接内容
- 预览框顶部新增模式徽标（自动生成 / 自定义）+「恢复自动生成」按钮，一键放弃自定义回到系统生成版本
- **引导文案优化**：模式徽标带悬浮说明；预览框下方提示条按当前模式动态显示——自动模式讲清「任务附加约束（追加小补）」与「直接编辑框（整段重写）」两种方式及二选一关系；自定义模式提示整段覆盖的后果与恢复方法
- **「任务附加约束」重新定位为「追加小补」**：help-tip 明确它与预览框编辑的区别（追加末尾 vs 整段重写），placeholder 同步引导
- **修复编辑预览框不切换自定义模式的 bug**：`markPromptEdited` / `resetPromptToAuto` 未加入 `Object.assign(window, …)`，inline `oninput` /「恢复自动生成」按钮失效，现补上
- 后端 `VideoTaskAdapter` 新增 `custom_prompt` 字段：`adapter_from_task` 优先使用自定义 prompt，否则走 `build_prompt`；`store.validate` 在自定义时跳过 `build_prompt` 校验（用户文本无法程序校验）；`/api/prompt-preview` 识别 `custom_prompt` 直接回显
- 前端 `formTask` 仅当用户在预览框手动编辑过（`store.customPromptDirty`）才提交 `custom_prompt`；编辑任务自动回填已保存的自定义 prompt

### 🔀 任务排序交互优化
- 主任务列表与 Anchor 任务列表的「单个三态排序按钮」拆分为四个独立按钮并列：`时间 ↓`（最新在前）/ `时间 ↑`（最早在前）/ `名字 A-Z` / `名字 Z-A`，点击即选中高亮（主题色），一眼看清当前排序
- 排序逻辑新增 `name-desc`（名字字母降序）；state.js 注释同步

### 📄 文档
- `Prompt_Design.md` 升至 V2.3，新增「13.1 可编辑 Prompt（自定义覆盖）」
- `Video_Task_Workflow.md` 补充 `custom_prompt` 可选字段说明
- **参考音频三种输入场景说明**：`Asset_Design.md` 升至 V1.1，§4.1 新增三种输入场景（① 视频+视频提取音频、② 纯音频、③ 视频+独立音频=不提供）的来源/处理/提交差异表，说明传视频时音频以视频提取为准、音频 tab 独立音频被覆盖的切换边界；`Video_Task_Workflow.md`、`Singing_Video_Guide.md` 同步补充
- **修复「视频 + 独立音频」被前端误填充**：`formTask` 视频分支去掉 `audio_file` 生成，传视频时音频恒从视频提取；`switchRefTab` 切到视频 tab 时若音频 tab 有残留音频给出 toast 提示「将被视频提取音频覆盖」，避免两类音频来源混淆
- **修复上传/选择音视频的归位不一致**：此前上传只按「当前 tab」决定写入视频还是音频字段（视频 tab 上传音频会误写进视频字段、音频 tab 上传视频会误写进音频字段），而「选择文件」是按文件类型自动切 tab——现统一为按**文件类型**归位：音频→🎵 音频 tab、视频→📹 视频 tab；选择文件时若混选（视频+音频）则只保留视频进视频 tab 并提示「音频以视频提取为准」，避免音频污染视频字段导致生成时把音频当视频切片
- **明确「打时间戳」独立于「传参考音频」勾选，且优先用传的音频本身**：`pass_reference_audio` 只控制是否把提取的音频上传给 Seedance 用于生成；打时间戳（前端本地流程）的音频来源优先级为「音频 tab 传的纯音频 → 用音频本身；否则用参考视频 → 从视频提取」，不受勾选影响。代码 `_resolveAudioSource` 调整优先级 + 文档（`Video_Task_Workflow.md`、`Singing_Video_Guide.md`）补充说明
- **恢复「视频 + 独立音频」对口型**：同时传视频（📹 tab）与独立音频（🎵 tab）时，音频作为**独立对口型源**保存并生效（视频模仿动作、音频对口型），生成时用独立音频而不是从视频提取。`formTask` 恢复 `audio_file` 生成；`editTask` 回填 `audio_file` 到音频字段（编辑可见、可改）；「选择文件 / 上传」改为按**当前 tab** 归位（不丢弃、不自动切 tab），视频与音频可共存；移除此前「传视频时音频以视频提取为准、独立音频被覆盖」的 toast 提示
- **传独立音频时置灰「传参考音频」**：用户上传了独立音频（对口型源）时，视频 tab 的「传参考音频」（从视频提取）**置灰禁用**并提示「已用独立音频对口型，视频音频不适用」——避免两个音频来源混淆；`formTask` 在有 `audio_file` 时 `pass_reference_audio` 强制为 `true`（上传独立音频对口型）
- **修复资产面板 `asset_id` 残留误导**：`_task_assets` 的 `asset_id` 仅在「存在有效资产可复用」（`asset_state=AVAILABLE`）时返回，资产缺失/需重传（`MISSING`）时返回空——避免 UI 显示旧 asset id（如「重建并上传」却仍显示 asset-xxx）造成困惑
- **处理无效 asset id 导致提交失败**：`data/街道风/seedance/assets.json` 中 `anchor_anchor-1` 残留了一个无效的资产 id（`asst_1`，非真实 Seedance 资源），被 planner 误判可复用，提交时 Seedance 报 `asset asst_1 is not found`。已清理该无效资产记录，提交时重新上传真实 asset
- **上传/选择参考音视频按文件类型自动切 tab**：上传音频文件（或选择文件时选中音频）自动切到「🎵 音频」tab 并写入音频字段，上传/选择视频自动切到「📹 视频」tab 写入视频字段（按文件类型归位），两个 tab 内容可共存（视频 + 独立音频对口型）；上传时**按文件类型自动归类 category**（音视频→参考音视频、图片→Anchor 图片），即使下拉框停在「Anchor 图片」也能正确上传，并同步下拉框选中值；静态前端 JS 改 `Cache-Control: no-store` 强制刷新最新代码，避免浏览器缓存旧 JS 导致交互不生效
- **修复音频资产 `seedance_duration`/`kind` 误判「未上传」**：`_resolve_transform("audio")` 此前只依赖 `_segments`（视频/首个 media 时长）算 seedance_duration 与 kind，未区分「纯音频任务的独立音频 / 独立上传音频」与「视频提取音频」——当音频源自身时长与视频不同（如 21.1s 音频 vs seedance_duration 22），或音频源短于 seedance_duration 需 pad（audio_padded）时，desired transform 与已上传资产不匹配，导致已上传的音频资产反复显示「未上传」并重传。现改为基于**音频源自身时长**（`audio_file` 或纯音频的 `file`）计算 seedance_duration，并按「音频源时长 < seedance_duration」推断 `kind=audio_padded`，使 status 面板（未 prepare）与 prepare 后产物一致
- **修复「复用已上传资源」误判：资产必须对应当前产物、且产物必须对应当前源才复用**：`_inspect_reference` / `_inspect_audio` 此前只凭「本地产物有效」或「资产 __source 匹配当前产物」就判定复用云端资产，未校验两件事：
  1. 资产上传时的产物指纹（`__source`）/ `__transform` 是否与当前产物一致（产物重建后旧资产会残留）；
  2. **产物本身是否对应当前源视频**（`artifact_valid`，即 marker 签名匹配当前源）——否则即使 work 目录残留旧切片 + 资产 __source 匹配旧切片，也可能被误判复用（如「街道风/冻结」从未真正生成对应当前 frozen.mov 的切片，却显示 ✓ 复用）。
  现改为「有效资产」= 资产存在 + 资产对应当前产物（`__transform` 匹配 或 `__source` 指纹匹配）+ `artifact_valid` 三者同时满足才复用；任一不满足则走重建/重传（`UPLOAD_EXISTING_ARTIFACT` / `BUILD_AND_UPLOAD`）

### 🔊 参考音视频点击预览
- 「素材 → 参考音视频」缩略图支持点击预览：**音频**（♪ 图标）点击弹出 lightbox 内嵌 `<audio controls autoplay>` 播放器；**视频**缩略图点击弹出 `<video controls>` 播放器（此前视频仅静音缩略图、音频无任何播放能力）
- 复用并扩展原有图片 lightbox 为通用媒体预览：`#lightbox-media` 按类型动态渲染 img / audio / video；点击遮罩背景关闭，点击播放器本体不关闭（可操作进度条等）；关闭时自动暂停并清空媒体
- 修复点击缩略图误触操作控件：预览委托排除 `.asset-remove` / `.chip-remove`，删除按钮仍正常响应
- **修复点击缩略图意外跳 tab**：素材缩略图位于 `<label>` 内，浏览器默认行为会激活 label 内第一个按钮（"Anchor 文件"→"现场生成"、"参考音视频"→"📹 视频"），导致点击图片跳「现场生成」tab、点击音频跳「视频」tab；现预览委托对缩略图点击统一 `preventDefault() + stopPropagation()`，彻底阻断该默认激活
- **修复 lightbox 图片不能再点关闭**：图片预览恢复「点击图片本身关闭」的 toggle 习惯；音频/视频播放器本体点击不关闭（便于操作进度条），仅点击遮罩背景/空白处关闭
- 后端 `file-preview` 已支持 Range/206 流式播放，音频可拖进度条

### 📦 Asset 面板源文件变化标记
- **核心改进**：让用户清楚看到哪些素材会被自动重传、哪些会复用。素材上传采用文件指纹（`path + size + mtime_ns`）实现自动复用，但用户难以直观判断"我编辑了源文件后，下次提交会不会重传"
- 后端 `_task_assets` 接口扩展：对比"当前源文件指纹"与"上次 prepare 时的源文件指纹"，返回 `current_source`（当前指纹）和 `changed`（是否变化）
  - **Anchor 图片**：缓存 `__source` 即源图指纹，直接对比源图
  - **视频切片 / 音频**：读取 prepare 写入的 marker 文件（`segment_XX.src.json` / `audio.src.json`），用其中的源文件指纹与当前源文件对比
- 前端 Asset 面板为每个素材增加状态徽标：
  - 🟢 `✓ 指纹未变 · 将复用`（绿色，正常复用已上传的 Seedance 资源）
  - 🟠 `⚠️ 源文件已修改 · 下次提交将重新上传`（橙色 + 行高亮 + 左侧橙色边线，提示用户这个素材会被自动重新上传）
- 每行额外展示源文件名、大小、最后修改时间（`MM-DD HH:mm`），用户一眼看清编辑时间
- 顶部说明文字更新，讲清自动复用、自动重传、手动 🗑 强制刷新三种场景的区别

### 🛠 Asset 产物缓存修复（Phase 1：Artifact Signature）
- **修复更换对齐策略（pad_mode）产物不重建的 bug**：原 prepare 的缓存判断只看源文件指纹，更换 pad_mode/split/crop 等处理参数而源文件未变时，产物（`audio_padded.mp3`、`segment_XX.mp4`）不重建，asset 复用旧版本，导致生成视频时长/对齐与用户所选不符
- **引入 Artifact Signature**：产物缓存签名 = `hash(源文件指纹 + 处理参数 transform + 处理器版本)`，任一变化 → 产物重建 → asset 自动重传
  - `_artifact_signature()` / `_read_signature()` / `_write_marker()` 辅助函数 + `_PROCESSOR_VERSION=2`
  - 音频补齐 `audio_padded`：签名含 `pad_mode` / `seedance_duration`，marker 升级为 `audio_padded.src.json`
  - 视频切片 `segment_XX`：签名含 `start` / `duration` / `crop_filter` / `pad_mode` / `original_duration`
  - `audio.mp3` 缓存判断保持原状（内容只取决于源文件）
- **向后兼容**：旧格式 marker（仅源指纹）首次会被识别为不匹配 → 重建一次后写入新格式
- **已验证**：签名逻辑（pad_mode back≠front）、幂等（重复跑不重建）、修复生效（pad_mode none→back 触发重建）
- 详细机制与设计见 [guides/Asset_Design.md](guides/Asset_Design.md)

### 🧭 Asset 统一决策引擎（Phase 2：Planner）
- 实现 `AssetPlanner` 统一决策引擎，作为 Runner 与后端 Status API 的**单一决策来源**（设计见 `Asset_Design.md` §7）
- 新增 `video_tasks/planner.py`：
  - `AssetDecision` / `InspectedMaterial` 输入结构
  - ReasonCode：CACHE_HIT / FIRST_UPLOAD / SOURCE_CHANGED / TRANSFORM_CHANGED / SOURCE_MISSING_REMOTE_REUSE / SOURCE_REQUIRED_FOR_REBUILD / REMOTE_ASSET_OPAQUE 等
  - `plan_material()` 决策矩阵：REUSE_REMOTE / UPLOAD_EXISTING_ARTIFACT / BUILD_AND_UPLOAD / NEED_SOURCE_FOR_REBUILD / NEED_MATERIAL_REBIND
- `runner.py`：`upload()` 重构为 **plan → 阻断检查 → prepare(需要时) → 按 action 上传**；新增 `_resolve_transform` / `_inspect_anchor` / `_inspect_reference` / `_inspect_audio` / `_plan_all`；上传成功写入 `__transform`
- `web/handlers.py _task_assets`：改为调用 `_plan_all` 返回统一 Planner Decision（action/reason/各 state/can_submit/block_reason/transform），消除"UI 显示复用、Runner 实际失败"的不一致
- 前端 Asset 面板 `showAssets`：按 action/reason 渲染状态徽标（🔄 将重新生成并上传 / ✓ 复用已上传资源 / ⚠️ 需重新选择等），废弃旧 `changed` 指纹判断
- **已验证**：planner 9 决策场景符合设计矩阵；源文件未变→REUSE 复用、touch 源文件→BUILD_AND_UPLOAD 重传；源删除→NEED_MATERIAL_REBIND 阻断；Status API 返回完整 Decision；面板正确渲染
- **⚠️ 验证中发现并修复 2 个真实 bug**：
  1. **Status API 源删除时返回 error**：`adapter_from_task` 的 `store.validate` 会校验素材文件存在，源缺失时抛 `missing asset`，导致 Asset 面板在源删除时无法显示状态。修复：`adapter_from_task` 新增 `skip_material_check` 参数，Status API 传 `True` 跳过素材文件校验（`store.validate` 增加 `check_materials`），让面板能展示"素材缺失"状态。
  2. **lip_sync 无歌词任务 Status API 报错**：`adapter_from_task` 在构造 prompt 时直接调 `build_prompt`，lip_sync 无歌词抛错，导致 Asset 面板打不开该任务。修复：`skip_material_check=True` 时跳过 prompt 构造（只展示素材状态），同时 `store.validate` 用 `strict=False` 跳过生成期校验。
- **⚠️ 修复「旧资产误判为全部重传」**：Phase 2 引入 `__transform` 后，旧资产（无 `__transform`）会被判定重传，且 `_fingerprint` 含 path 导致源图移动位置（如 `anchors/selected/` → `anchors/`）被误判为"已修改"
  - 新增 `_fingerprint_content_same`：指纹比较忽略 path，只看 `size + mtime_ns`（同一文件移动到不同路径不视为已修改）
  - `_inspect_anchor` / `_inspect_reference`：旧资产（有 `__source` 无 `__transform`）且源/产物指纹一致时，兜底 `asset_transform = desired`，避免误判重传
  - `plan_material`：有源分支在 `artifact` 不匹配时，若 `asset_transform` 匹配（含兜底）仍判定 `REUSE_REMOTE` 复用
  - **验证**：跳舞（4 anchor + 切片误判重传）→ 修复后全部复用，仅剩从未上传过的音频首次上传；冻结/偶尔全部复用；真实替换过的 anchor（size 变化）正确重传
- **注**：源缺失复用（Snapshot + Remote Only）为后续方向；当前源缺失时 planner 判定阻断（需重选），见 `Asset_Design.md` §11 边界 1

### 💾 时长对齐（pad_mode）改动强制选择保存方式
- 编辑已有任务时若改了「时长对齐」，保存时**强制弹出「保存方式」二选一**（保存为新任务 / 更新原任务 / 取消），并推荐保存为新任务：对齐方式会影响产物重建，保留原任务可避免覆盖
- 弹窗文案带具体变化（从「原始时长」改成「后补齐」等）；保存成功后同步原始 pad_mode，避免后续保存重复弹窗
- 复用现有 `showSaveModeDialog` 交互，`showSaveModeDialog` 支持 `reason='padMode'` 场景；state 新增 `originalPadMode` 记录编辑回填的原始对齐方式

---

## [2026-08-14] - Anchor 页面与逻辑完善

### 🖥 Anchor 前端
- 参考图「补充描述」由 `onchange` 改为 `oninput` 实时保存，切换数据目录或新增图片不再丢失输入
- 参考图操作按钮移至列表顶部：「从数据目录选择」+「本机上传」，并显示已添加张数；参考图改为多列自适应网格，布局更紧凑
- 切换数据目录时清空已选参考图（弹窗确认，取消则保持不变），并同步重置参考点来源下拉框、检测新目录内已有图片
- 画质/风格、禁止项快捷标签修复：编辑任务回填后再保存不会重复累积标签文本；点击标签会实时把「选中标签 + 手动描述」合并显示到备注框，手动描述与标签互不覆盖
- 审核页移除「推荐 / 不推荐」投票，仅保留「下载」「设为 Anchor」与工具栏「按当前配置再生成一批」
- 「设为 Anchor」支持取消：已设为 Anchor 的候选可点击「取消 Anchor」撤销，并自动删除 `anchors/` 中已复制的图片
- 修复「从数据目录选择」参考图列表不加载：`pickAnchorReferences` 打开文件选择弹窗后漏调用 `browseAssets`，现补上，进入 `anchors/anchor-references/` 后能列出该目录已有的参考图
- 修复从数据目录选择的参考图保存时路径丢失 `anchor-references/` 前缀：picker 按 `anchors/anchor-references/` 截断后只剩纯文件名，现统一补回前缀，与上传、后端 `_reference_source` 解析一致（`file` 统一为相对 `anchors/` 的 `anchor-references/<name>`）
- 参考图选择弹窗为每张图显示缩略图预览（此前仅视频任务的 Anchor 图片有缩略图，参考图缺失），预览路径改为用相对 `data_root` 的完整路径，避免与视频任务目录前缀混用
- 修复切换数据目录后参考图缩略图残留：手动在输入框改目录（`oninput`）此前只更新提示条、不清空已选参考图，现引入 `store._anchorDir` 检测目录变化并清空旧参考图；编辑回填、保存、从视频任务跳转等设置目录处同步 `_anchorDir`，避免误清空刚加载的参考图
- 修复「从数据目录选择」弹窗残留上一个文件夹图片：`browseAssets` 的主目录引导逻辑在请求不存在的 `anchor-references/` 目录时未捕获异常，导致列表渲染提前中断、旧文件残留；现给引导请求加 try-catch，目录缺失时跳过引导并正常渲染当前目录（空则显示空状态）

### 🐛 后端与进度
- Anchor 运行进度对齐视频任务：提交（submitting）阶段不再把进度条拉满，仅生成（generating）/完成阶段推进整体进度
- 修复提交失败时 `Cannot read properties of undefined (reading 'id')`：保存失败时不再继续弹提交密码框
- 修复 Anchor 运行「恢复轮询」失效：`_resume_from_state` 构造 runner 与 `_resume_run` 调用 `resume` 的参数签名不匹配，导致服务重启后无法继续轮询
- 修复视频任务「恢复轮询」失效：`resume` 分支此前被误放在 GET handler 中，POST `/api/runs/<id>/resume` 直接 404，现移回 POST handler
- 恢复轮询不再依赖 Anchor 图片：resume 仅继续轮询已提交的候选（凭 task_id 下载），无需重新提交，因此只校验 references 音视频、不再校验 anchors 图片
- 移除 Anchor 审核的 `vote` 动作端点，`promote`（设为 Anchor）保持不变
- 「取消 Anchor」增加引用校验：图片被视频任务引用时拒绝删除（返回 409），避免误删视频任务依赖的 Anchor 图
- 编辑视频任务时检测素材缺失：后端新增 `GET /api/tasks/<id>/missing-assets`，前端编辑任务时对已删除的 Anchor/参考音视频给出明确警告条与「文件已不存在」标记；asset 缓存保留，文件重新选回后可复用无需重传
- 视频任务「选择 Anchor 图片」默认定位到 `anchors/`（与上传、设为 Anchor 同目录），且文件列表为每张图片显示缩略图预览
- 统一 Anchor 图片落点：上传的 Anchor 图与「设为 Anchor」的图都直接落到 `anchors/` 根目录（取消 `anchors/selected/` 子目录），选图、预览、取消 Anchor 均按 `anchors/<filename>` 解析
- 选图引导现场生成候选：Anchor 图片 picker 检测到 `generated/` 目录时，提示「现场生成的候选在 generated/ 里（尚未设为 Anchor）」，进入后说明如何「设为 Anchor」固定到正式目录
- 编辑已保存任务时，顶部「新任务」按钮动态切换为「取消」（放弃修改并清空表单）；Anchor 与视频任务一致
- 上传素材改为采用后端返回的实际相对路径，避免前端自行拼接路径与后端不一致
- 视频候选下载文件名带上「数据目录__任务名」前缀并保留中文，方便区分不同目录下同名任务的候选
- Asset 清单改为显示源文件名（而非完整绝对路径），让 asset key 能对应到具体素材文件
- 保存任务放宽校验：保存草稿时不再强制要求歌词/完整素材（`strict=False`），仅生成时才严格校验；填了任务名和文件夹即可保存
- 修复编辑改名后「更新任务」报 `RequestInit` 类型错误：删除旧任务的 `api(url, 'DELETE')` 误传字符串，改为 `{ method: 'DELETE' }`
- 修复「取消/新任务」后素材残留：显式清空 anchor/音视频字段并重新渲染预览，清空歌词时间戳，取消后显示「请先选择任务文件夹」提示
- 编辑任务后滚动到「素材」区，编辑回顶由平滑滚动改为瞬间跳转、缩略图立即加载，修复滚动黑屏卡顿
- 防御任务 id 双重前缀：`list()` 读取 task.json 时若 `id` 已含 `data_dir__` 前缀则剥离后再拼接，避免历史脏数据产生 `曾曾__曾曾__跳舞` 这类重复前缀
- Asset 清单增加说明：顶部提示「文件指纹自动复用，源文件未变则跳过上传」，每个条目标注素材类型（Anchor 图片/参考视频/参考音频）
- Anchor 生成器选择数据目录后，检测并**分别提示**已有 Anchor 图：「已有 N 张正式 Anchor 图（anchors/ 根目录，可直接在视频任务里使用）」与「另有 M 张生成候选图（generated/，需「设为 Anchor」后固定到正式目录）」，不再把手动上传的正式图与生成候选图混称「已生成」

### 🎬 高级视频设置（Seedance 2.5 参数可配置）
- 视频任务表单新增「高级视频设置」折叠区（默认收起）：分辨率（480p/720p/1080p）、宽高比（9:16/16:9/1:1/4:3/3:4）、生成音频、加水印、输出格式（MP4/WebM）
- 折叠区 summary 直接显示当前默认值（「默认：720p · 9:16 · 无音频 · 无水印 · MP4」），用户无需展开即可判断是否需要调整
- 生成音频/加水印使用 toggle switch 开关样式（与 select 分区显示，上方有分隔线），支持键盘 `focus-visible` 聚焦 outline
- 后端 `VideoTaskAdapter` 新增 `watermark`、`output_format` 字段；`factory.py` 读取任务的 `resolution`/`ratio`/`generate_audio`/`watermark`/`output_format`；`runner.py` 提交 Seedance 时把这些参数完整传入 payload
- 前端 `formTask()` 收集高级设置字段；`editTask()` 回填；`resetForm()` 通过表单 reset 恢复默认值
- 任务 JSON 可选 `resolution`/`ratio`/`generate_audio`/`watermark`/`output_format` 字段，不填用默认值（720p / 9:16 / false / false / mp4）

### 🖼 图片放大预览（Lightbox）
- 点击可放大的图片缩略图弹出大图预览（黑底遮罩），**再点图片或遮罩即关闭**（toggle 交互），也可 ESC / 右上角 × 关闭
- 覆盖范围：视频任务主页面素材图（Anchor 图与参考图）、「从文件夹选择」picker 缩略图、Anchor 参考图卡片、Anchor 候选审核图
- Anchor 参考图卡片：点击图片仅放大预览，不触发展开/收起（展开仍可通过卡片其他区域触发）
- 所有可放大图片鼠标悬停显示 zoom-in 光标，放大后显示 zoom-out 光标

### 🔧 命名统一与交互优化
- 统一术语：Anchor 页「数据目录」→「任务文件夹」，与视频任务页一致；folder picker 标题「选择机器文件夹」→「选择任务文件夹」；参考图按钮「从数据目录选择」→「从文件夹选择」；删除/切换确认弹窗文案同步
- 任务列表排序：视频任务和 Anchor 任务支持三态排序切换（**时间降序**最新在前 → **时间升序**最早在前 → **名字 A-Z**），按钮实时显示当前状态与方向；后端 `list()` 为任务暴露 `mtime`（文件修改时间）字段供前端排序
- 排序按钮修复 dark 模式看不清：改用 `--surface` 背景 + `--text` 文字色，dark 下使用更亮文字和边框
- Lightbox 交互优化：点击图片本身也能关闭（此前需找右上角 ×）；关闭时 `stopPropagation` 防止冒泡触发其他逻辑（修复放大后点击关闭误跳「现场生成」tab）
- Anchor 参考图卡片：去掉缩略图上的展开/收起图标，缩略图点击仅放大预览（lightbox）；展开/收起配置改为点击标题文字触发，标题带 ▾/▴ 提示
- 修复歌词时间戳弹窗保存后页面滚回顶部：打开弹窗时记录 `window.scrollY`，关闭时恢复，保证回到原停留位置
- 修复切换音视频后打歌词仍用旧音频：`_resolveAudioSource` 此前优先用已保存任务的 `references`（编辑回填的旧值），现改为**优先读取表单当前的音视频引用**（`#references`/`#audio-refs`），表单为空时才回退到已保存任务
- 修复纯音频输入（仅音频、`pass_reference_video=false`）的音频处理与视频提取音频不对等：此前纯音频也走 `extract_audio`（从视频提取音频）二次转码，现改为纯音频模式下直接 `shutil.copyfile` 拷贝原音频文件（视频模式仍走 `extract_audio`），两者对等且音频 asset 均正确上传
- 修复切换音视频后沿用旧缓存：`prepare()` 此前用 `audio.exists()`/`segment.exists()` 判断是否重新生成音频/切片，切换音视频后旧 `work_dir` 缓存仍存在导致沿用旧素材；现改为用源文件指纹（`path+size+mtime_ns` 写入 `.src.json` 标记）判断，源文件变化即重新提取音频/拷贝音频/重切视频
- 优化对口型（lip_sync）prompt 的自然律动约束：原「身体主体保持稳定，不主动增加明显手势或大幅身体动作」导致人物僵硬如背景板，现改为「肢体和身体随音乐节奏自然轻微律动、自然融入场景，不能僵硬如背景板，但动作自然克制、以准确口型为核心」
- 修复「预览 Prompt」未随模式更新：`/api/prompt-preview` 此前只传 `has_audio_ref`、漏传 `has_video_ref`（默认 True），纯音频模式下预览仍按视频模式生成（含「视频1嘴形」且约束错误）；现补传 `has_video_ref`，预览与实际提交的 prompt 一致

### 🐛 Anchor 候选审核「生成中」状态
- 修复 Anchor 生成中点击运行记录时审核区仍显示旧图：此前 `loadAnchorReview` 一次性加载 manifest，运行中 manifest 未写入会 404 且无 catch，导致旧候选残留
- 现改为轮询加载（运行中每 3 秒刷新），manifest 不可用时显示「生成中，候选图完成后将实时出现在这里…」占位，完成后自动加载候选图
- 运行下拉框纳入「生成中」的运行记录（标注「（生成中）」），切换时清空旧内容、显示对应状态

## [2026-08-14] - 健壮性与体验修复

### 🐛 后端修复
- 参考图映射 off-by-one：第 6 张参考图此前映射到索引 6 导致 `file` 不被替换、保存时抛错，改为正确的索引 5
- `image_poll_workers=0` 会触发 `ThreadPoolExecutor(max_workers=0)` 崩溃，现保证最小为 1
- 身高占位符「身高约{}cm」此前返回字面量、捕获数字被丢弃，现支持 `{}` 填充 group 1
- GPT Image 客户端：`_create_task` 增加 `data` 层解包（与 poll/task 一致）；`_run_with_retry` 捕获 `requests.RequestException`；`poll_to_file` 对网络瞬断重试而非中断
- 配置统一：GPT Image 2 直接复用 `SEEDANCE_API_BASE`/`SEEDANCE_API_KEY`，移除遗留的 `PHANROUTER_*` 中间变量
- 隧道复用路径重建时改用带 fallback 的完整 state，修复 fallback 后 provider/base_url 错位

### 🖥 前端与脚本
- 所有模态框统一支持 ESC 关闭 + 遮罩点击关闭 + Tab 焦点陷阱（无障碍）
- 暗色主题 FOUC 修复：`<head>` 内联主题 bootstrap，首屏不再闪白
- 修正 `escapeAttr`/`escapeHtml` 转义（HTML 属性上下文）
- `start-daemon.sh`/`status.sh` 端口提示动态化（`--port` 参数 / `VIDEO_WEB_PORT` / 默认 8913）
- 移除死代码 `deleteTask()`（删除统一走 `confirmDeleteTask`）

### 🗑 文档
- 删除 `docs/WEB_REVIEW.md`（内部安全评审，不宜公开）

## [2026-08-14] - 素材隧道支持多方案与自动回退

### 🔧 隧道 provider 可配置
- 素材隧道真正支持 `--provider {auto,pinggy,ngrok}` 选择，`auto`（默认）优先 Pinggy（重试 3 次），失败后自动回退 ngrok
- `_start_ngrok` 修复：检测 ngrok 是否安装（未安装给出明确提示）、自动注入 `NGROK_AUTHTOKEN`、URL 可达性校验
- ngrok URL 提取改为从日志 stdout 正则解析（ngrok v3 的 4040 web API 因 `allow_hosts` 返回 502，不可靠）
- `_reachable` 改用 `requests` 且超时提高到 15s（`urllib` 对 ngrok-free.dev 域名 SSL 握手超时；5s 易误判）
- 隧道启动失败时汇总所有 provider 的失败原因，并给出安装/配置指引
- Pinggy 需 `PINGGY_TOKEN`（URL 稳定性取决于账号类型：免费版随机且限时，付费版固定且稳定）；缺失 token 时给出明确提示而非静默失败
- 隧道复用路径按已记录的 provider 重启，不再硬编码 Pinggy

## [2026-08-14] - 环境兼容性改进

### 🖥 多平台安装与启动兼容
- `setup.sh` 系统依赖安装支持多发行版：macOS / Ubuntu / Debian / Fedora / RHEL / CentOS / Arch Linux
- `setup.sh` 新增 `python3-pip` 缺失检查（Debian/Ubuntu 需单独安装），并修正结尾启动命令路径
- `start-daemon.sh` 的 PATH 兼容 Intel / Apple Silicon Homebrew 路径（`/usr/local/bin` + `/opt/homebrew/bin`）
- `start-pinggy.sh` 支持读取 `.env` 的 `PINGGY_TOKEN`（无 token 匿名模式不可用，缺失时明确报错）
- ngrok 安装方式改为多平台（官方脚本，不依赖 Homebrew，兼容 macOS / Linux）

## [2026-08-14] - 素材目录统一约定与历史数据迁移

### 🗑 删除数据目录
- 文件夹选择器顶层新增「删除文件夹」入口（每个数据目录旁 🗑 按钮）
- 删除前确认弹窗以**级联树状结构**列出将删除的内容：目录 → 每个视频任务（标注关联运行数）→ Anchor 任务 → 参考音视频 / Anchor 图片 / Seedance 缓存，底部汇总「共 N 个任务 · M 条运行记录 · 不可恢复」
- 级联清理范围：任务定义（`tasks/*.json`）、Anchor 图片/候选（`anchors/`）、参考音视频（`references/`）、Seedance 缓存（`seedance/`）、运行记录与 `runtime/outputs` / `runtime/work` 下的生成产物，最后删除整个 `data/<目录>/`
- 仅对 `data/` 下的一级数据目录生效

### 📦 目录约定统一
- 目录约定：图片存放于 `anchors/`，音视频（视频 + 音频）存放于 `references/`，任务根目录仅用于内部目录
- 「选择文件」默认直接进入约定子目录（Anchor → `anchors/`，音视频 → `references/`）
- 新增**主目录回退引导**：素材放在主目录时，进入空子目录会显示引导条「主目录里有 N 个 → 去主目录」，点击跳转到主目录
- 将散落在根目录 / `audio/` 下的历史数据迁移到 `references/`、图片迁移到 `anchors/`，并同步更新已保存任务的引用路径
- 已迁移历史数据：`冻结`、`马路风`、`ruins` 等目录（`frozen.mov`、`nini.mov`、`zengzeng2.mov` 等视频迁移到 `references/`，`frozen.mp3`、`zengzeng2.mp3` 等音频归入 `references/`）

## [2026-08-14] - 素材管理交互优化、纯音频修复

### 🗂 素材管理交互
- Anchor 获取方式重构为「选择文件 / 现场生成」两个同级操作，现场生成仅针对 Anchor，参考音视频、歌词、约束始终显示
- 现场生成采用「先说明（GPT Image 2）再跳转」的两步交互，跳转后回到 Anchor 页面顶部
- 任务文件夹前置校验：未填写时提示「请先选择任务文件夹」并禁用上传；缺素材时按「图片 / 音视频」分别给出引导
- 空目录提示的操作入口为**可点击跳转**：「去现场生成」「去上传」直接滚动到对应区域并高亮闪烁
- 「选择文件」默认进入约定子目录（`anchors/`、`references/`），子目录不存在时自动逐级回退到任务根目录
- 选参考音视频时自动过滤 Anchor 图片目录；选 Anchor 时只显示图片
- 选参考音视频后根据所选文件自动切换标签页：全音频 → 🎵 音频，含视频 → 📹 视频
- **切换任务文件夹会清空已选素材、歌词和附加约束，并先弹窗确认**（避免上一个文件夹的内容残留到新文件夹）；确认用自定义弹窗（原生 confirm 在部分环境不显示）
- 编辑纯音频任务自动切 🎵 音频标签页并正确回填

### 📦 文件位置约定
- 上传素材固定落点：图片 → `anchors/`，音视频 → `references/`
- 手动放置素材：图片放 `anchors/`、音视频放 `references/`（与上传落点一致）
- 任务 `file` 字段统一存「相对任务数据目录的路径」，带子目录前缀（如 `anchors/xxx.png`、`references/xxx.mov`）

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
- 生成的候选图和正式图都在同目录下，Video 任务可直接引用

#### 统一的目录结构
```
data/<数据目录>/
├── anchors/                     ← Anchor 模块
│   ├── anchor-task.json         ← Anchor 任务配置
│   ├── anchor-references/       ← 参考图片
│   ├── generated/<run_id>/      ← 生成候选
│   └── *.jpg                    ← 上传 / promote 后的正式图（Video 任务从这里选）
├── tasks/                       ← Video 任务配置（可有多个）
│   ├── 唱歌版.json
│   └── 跳舞版.json
├── *.mov, *.jpg                 ← 原始素材
└── seedance/assets.json         ← 远程资源 ID（共享）
```

#### promote 流程简化
- **之前**：promote 时需要手动指定 `video_task_id`，跨目录拷贝图片，调用 `append_anchor` 修改视频任务
- **现在**：promote 只需拷贝到 `data/<目录>/anchors/` 根目录，Video 任务通过 asset picker 直接从该目录选图

#### Video 任务输出目录用数据目录名
- **之前**：`runtime/outputs/<task_name>/<run_id>/`
- **现在**：`runtime/outputs/<data_dir>/<run_id>/`（同一数据目录的多个任务共享输出路径前缀）

### 🔧 功能改进

#### 1. Anchor 表单新增"数据目录"字段
- 替代原来的"任务 ID"字段，通过文件夹选择器选取
- 任务名称独立保留，用于显示

#### 2. Video 任务选 Anchor 图默认从 `anchors/` 根目录选
- asset picker 检测到 anchors 类别时自动导航到 `anchors/` 根目录

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
- `idolmv_pipeline/web/static/modules/task.js` — asset picker 默认到 anchors/ 根目录
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
  - Anchor 审核：设为 Anchor
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
