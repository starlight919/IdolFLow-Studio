# 素材库重构路线图（整合代办）

> **版本**：Roadmap
> **日期**：2026-08-16
> **状态**：代办路线图，未开始实现
> **关联文档**：
> - `docs/guides/Asset_Design.md`（现有实现：AssetPlanner / InspectedMaterial / assets.json）
> - `docs/guides/Video_Task_Workflow.md`、`docs/guides/Singing_Video_Guide.md`、`docs/guides/VIDEO_LOCATIONS.md`（操作与目录约定）
> - 代码：`idolmv_pipeline/video_tasks/{planner.py,runner.py,store.py,factory.py,models.py}`、`idolmv_pipeline/web/handlers.py`、`idolmv_pipeline/web/static/modules/task.js`

---

## 0. 为什么先写这份路线图

本次重构改动面非常大：从「task_dir / file」决定素材身份，切换到「全局 Library + Content Hash + Variant」。
直接动手实现存在以下风险：

1. **破坏现有运行中的任务**：现有 assets.json 按 data_dir 隔离，任务 JSON 直接存 `file` 路径，Planner 以 `task_dir + file` 为输入。一旦中途改动，正在编辑/提交的任务会失败。
2. **跨模块牵连广**：planner / runner / store / factory / handlers / task.js 全部耦合 `assets.json` 与路径解析。
3. **迁移不可一次完成**：已有大量 data_dir 和 assets.json，全量扫描 Hash 会卡死。
4. **边界容易模糊**：三种参考音频场景、runtime/work 是 Cache、Source 清理后仍需可复用等，重构必须在不破坏这些既有边界的前提下推进。

因此这份文档的作用是：**把重构的目标、与现有代码/文档的映射、分阶段拆解、每阶段的验收点和回滚边界全部固化下来，作为后续所有改动的统一基线。**

---

## 1. 核心结论

### 1.1 新的身份模型

```
Library Item          用户眼中的"一个素材"（名称/标签/封面/搜索）
    │
    ▼
Source Revision       不可变内容版本（content_hash 定义身份）
    │
    ├──── Source Location   一个 Revision 可有多个物理位置
    │      （DATA_DIR / LIBRARY_MANAGED / EXTERNAL）
    │
    ├──── Preview           持久保存，Source 删除后仍可识别
    │
    ▼
Variant               Revision + Transform 的处理版本
    │
    ▼
Remote Asset          上传 Seedance 得到 asset_id（属于 Variant，不属于 Task）
```

任务侧：

```
Task
  └─ Task Material Binding
       ├─ revision_id
       └─ desired transform
```

### 1.2 最重要的几个"不再"

- 不再用 `path` 表示素材身份
- 不再让 `task_dir` 决定 Asset 归属
- 不再让 Task 保存 Seedance `asset_id`
- 不再因跨 data_dir 使用同一素材而复制一份文件
- 不再因跨任务使用同一 Variant 而重复上传
- 不再因 runtime Artifact 被删除而认为 Remote Asset 不可用
- 不再因 Source 被清理就让用户看不到素材是什么
- 不再因文件原路径被覆盖就修改历史 Task 所使用的素材
- 不再让前端自己判断 Asset 能不能复用

### 1.3 三种选择方式最终统一返回 revision_id

```
[当前目录]   [素材库]   [本地导入]
        │         │         │
        └─────────┼─────────┘
                  ▼
            Resolve Revision
                  │
                  ▼
           Task Binding（revision_id + transform）
```

绝对不要出现「Current Dir → file path；Library → library_id；Upload → asset_id」三套 Task 数据。

---

## 2. 现有实现的关键锚点（改造必须保留语义）

### 2.1 现有身份与存储

- **Task JSON** 存 `references[].file` / `anchors[].file`（路径），无 `revision_id`
- **`assets.json`**（每个 data_dir 一份）：`{<key>: asset_id, <key>__source: {path,size,mtime_ns}, <key>__transform: {...}}`
- **Asset key** 基于位置：`anchor_anchor-1`、`reference_reference-1_00`、`reference-1:audio`
- **路径身份**：`source = task_dir / (reference.audio_file or reference.file)`

### 2.2 现有决策引擎（`planner.py`）

`AssetPlanner.plan_material(InspectedMaterial) → AssetDecision`，5 个 Action：

- `REUSE_REMOTE` / `UPLOAD_EXISTING_ARTIFACT` / `BUILD_AND_UPLOAD`
- `NEED_SOURCE_FOR_REBUILD` / `NEED_MATERIAL_REBIND`

重构后的 Planner Action 基本沿用，**变化在 Planner 输入**：从 `task_dir + file` 改为 `revision_id + desired_transform`。`planner.py` 的纯决策逻辑大部分可复用，但 `InspectedMaterial` 字段语义要从「产物指纹」切到「Variant Signature」。

### 2.3 现有 inspect（`runner.py`）

- `_inspect_anchor` / `_inspect_reference` / `_inspect_audio` 负责把磁盘 + assets.json 状态解析成 `InspectedMaterial`
- 已分离「资产是否存在」（显示，不依赖 `artifact_valid`）与「能否复用」（需要 `artifact_valid`）
- `_resolve_transform("audio")` 的 `seedance_duration` 基于**音频源时长**（audio_file 或纯音频 file），不是视频时长

重构后 inspect 要从「读 assets.json + 产物 marker」切到「查 SQLite Library DB 的 Variant + RemoteAsset」。

### 2.4 现有目录约定（`VIDEO_LOCATIONS.md`）

- `data/<任务文件夹>/`：anchors / references / tasks / seedance/assets.json
- `runtime/work/<任务文件夹>/`：临时处理（可清理）
- `runtime/outputs/<任务文件夹>/<run_id>/`：生成结果（不变）

重构新增 `data/_asset_library/`（library.db / sources / previews），不改动 runtime/outputs。

### 2.5 现有三种参考音频场景（`Asset_Design.md` §4.1）

重构目标之一是把参考音频正式改成显式 audio model：

- `audio.mode = "extract_from_video"`
- `audio.mode = "independent"` + `revision_id`
- 纯音频：`video: null` + `audio.mode = "independent"` + `revision_id`

V1.3 的 `pass_reference_video` / `file` / `audio_file` 组合规则在迁移期必须保留兼容。

### 2.6 现有 Status API 与前端

- `GET /api/tasks/{id}/assets` 返回每个素材的 `AssetDecision`
- 前端 `task.js` 按 `action` 渲染状态徽标，不做二次判断
- `formTask` / `editTask` 处理 audio_file 保存/回填、tab 路由、pass_reference_audio 置灰

重构新增 `GET /api/tasks/{id}/materials/status`（返回 revision_id + source_state + desired_variant + action + can_submit），并新增 Library API。

---

## 3. 重构对现有代码/文档的影响清单

### 3.1 代码改造点

| 模块 | 现状 | 重构改造 | 风险 |
|------|------|---------|------|
| `video_tasks/models.py` | `ReferenceSpec.file/audio_file`、`AnchorSpec.file` 路径式 | 新增 `revision_id` 字段；保留 `file` 兼容 legacy migration | Task JSON schema 变化，需双读兼容 |
| `video_tasks/store.py` | `validate` 校验 `file` 路径存在；`task_dir` 解析 | `validate` 支持 `revision_id`（有 revision 视为已绑定，不强制本地 file）；`task_dir` 退化为"工作目录" | 校验放宽可能漏掉真缺失 |
| `video_tasks/factory.py` | `adapter_from_task` 拼路径；`_timestamp_offset` 用 `file` | adapter 优先用 `revision_id` → Library resolve 出 source；`_timestamp_offset` 改为读 Revision source | 改动核心路径，影响所有提交 |
| `video_tasks/planner.py` | `InspectedMaterial` 字段基于产物指纹；`plan_material` 纯决策 | `InspectedMaterial` 字段语义切到 Variant Signature；决策逻辑基本保留；新增 Variant 查询入口 | 输入语义变化最大 |
| `video_tasks/runner.py` | `_inspect_*` 读 assets.json + marker；`upload` 写 assets.json | `_inspect_*` 改为查 Library DB（Variant + RemoteAsset）；`upload` 成功后写 RemoteAsset 表；产物 marker → Variant artifact_state | upload 路径重写 |
| `web/handlers.py` | `_task_assets` 读 assets.json | 改为读 Library DB；新增 `/api/library/*`、`/api/data-dirs/{id}/materials` | API 表面积扩大 |
| `web/static/modules/task.js` | formTask/editTask 处理 file/audio_file | 新增"选择素材"三入口（当前目录/素材库/本地导入）统一返回 revision_id；显示 revision 状态 | 前端交互重写 |
| 新增 `asset_library/` 包 | 不存在 | models/repository/importer/resolver/preview/variants/migration 七个模块 | 全新模块 |

### 3.2 文档改造点

| 文档 | 改造 |
|------|------|
| `Asset_Design.md` | §4 素材来源扩展为 task_dir 或 Library；§6 签名升级为 Variant Signature；§7 新增 SOURCE_MISSING_REMOTE_REUSE 完整实现；§11 边界 5「跨任务文件夹隔离」改写为允许跨文件夹复用 |
| `Video_Task_Workflow.md` | 新增"选择素材"三入口说明；audio 三场景用显式 model 描述 |
| `Singing_Video_Guide.md` | 同步 audio 显式 model |
| `VIDEO_LOCATIONS.md` | 新增 `data/_asset_library/` 目录；删除 data_dir 行为改写（不级联删 Library Managed Source / Remote Assets） |
| `CHANGELOG.md` | 每阶段记录 |

---

## 4. 分阶段路线（必须按顺序，不可跳步）

### Phase 0：Schema 和 LocationResolver（基础层）

**目标**：建立数据库骨架和路径解析，不动任何现有逻辑。

**交付**：
- `video-workspace.json` 增加 `data_root` / `work_root` / `output_root` / `asset_library_root`
- `LocationResolver`：`DATA_ROOT / LIBRARY_ROOT / WORK_ROOT / OUTPUT_ROOT / EXTERNAL` → 真实路径
- SQLite schema：7 张表（library_items / source_revisions / source_locations / previews / variants / remote_assets / task_bindings）
- `asset_library/models.py`、`asset_library/repository.py`、`asset_library/resolver.py`

**验收**：
- DB 可建表、可 CRUD
- LocationResolver 能解析现有 `data/冻结/references/dance.mov`
- 现有任务流程**完全不受影响**（assets.json 继续生效）

**回滚边界**：Phase 0 只新增文件，不改现有代码，零风险回滚。

---

### Phase 1：Library Import（入库层）

**目标**：实现文件 → Revision 的入库链路，但不接入 Task。

**交付**：
- `asset_library/importer.py`：Local File → Fingerprint → Content Hash → Dedup → Revision → SourceLocation → Preview
- Fingerprint（size + mtime_ns）快检测，Content Hash（BLAKE3 或 SHA256）全局身份
- 同一文件导入两次 → 一个 Revision
- Preview：图片 512px WebP / 视频 360p Proxy MP4 或 poster+contact sheet / 音频低码率 MP3
- Preview 原子写入（tmp → validate → rename）

**验收**：
- 同内容文件不同路径 → 命中同一 Revision（新增 SourceLocation，不新建 LibraryItem）
- 不同内容 → 新 Revision
- 覆盖同路径文件 → 创建新 Revision，旧 Revision 不变
- 不影响现有 Task 流程

**回滚边界**：Phase 1 只写 Library DB，不读，不影响现有 assets.json。

---

### Phase 2：Task Binding（Task 侧接入）

**目标**：Task 新增 `revision_id`，三种选择方式统一返回 revision_id。

**交付**：
- `ReferenceSpec` / `AnchorSpec` 新增 `revision_id` 字段（保留 `file` 兼容 legacy）
- `store.validate` 支持 `revision_id`（有 revision 不强制本地 file 存在）
- 前端"选择素材"三入口：
  - 当前目录：轻扫描 data_dir（path/extension/size/mtime/已有 mapping），Lazy Hash
  - 素材库：Preview + 搜索 + 筛选
  - 本地导入：系统文件选择器 → Import → Dedup → Revision
- 三入口统一返回 `revision_id`，Task 保存 `revision_id`（不保存 asset_id）
- Data Dir Browser：`GET /api/data-dirs/{id}/materials` 返回文件与 Library mapping 关系

**验收**：
- 当前目录第一次选文件 → 自动入库并绑定 Revision
- 另一 data_dir 选内容相同文件 → 命中同 Revision
- 素材库直接选已有素材 → 不复制 Source
- 覆盖同路径文件 → 新 Revision，旧 Task 不受影响
- 老 Task（只有 `file` 无 `revision_id`）仍能打开（Lazy Migration 触发）

**回滚边界**：Phase 2 允许 Task 同时有 `file` 和 `revision_id`，退化到 legacy 流程；Planner 仍走旧 assets.json 路径。

---

### Phase 3：Variant Globalization（产物签名升级）

**目标**：把 Task Local 的 Artifact Signature 升级为 Revision + Transform 的全局 Variant。

**交付**：
- `asset_library/variants.py`：`Variant Signature = hash(Revision.content_hash + normalized_transform + processor_version)`
- Variant 表：`signature` UNIQUE 索引
- Variant 状态：`BUILDING / READY / FAILED`
- 同 Revision + 同 Transform → 同 Variant Signature → 跨任务复用
- Variant Preview（高级详情用）

**验收**：
- 同 Revision + 同 Transform → 复用同 Variant
- 同 Revision + 新 Transform → 新建 Variant
- 删除 runtime/work → 已有 Remote Variant 正常复用（Variant Identity 不依赖 runtime/work）

**回滚边界**：Phase 3 只升级签名层，Planner 仍可退化到读 assets.json（assets.json 作为 fallback）。

---

### Phase 4：Planner Integration（Planner 接入 Library）

**目标**：Planner 输入从 `task_dir + file` 改为 `revision_id + desired_transform`。

**交付**：
- `InspectedMaterial` 字段语义切到 Variant Signature
- `_inspect_*` 改为查 Library DB（Variant + RemoteAsset）
- `plan_material` 输入 = `revision_id + transform` → Variant Signature → 查 Variant → 决策
- 完整 4 分支：
  - Variant + Remote Asset 存在 → `REUSE_REMOTE`
  - Variant 存在，Remote 不存在，Artifact 还在 → `UPLOAD_EXISTING_ARTIFACT`
  - Variant 不存在，Source 存在 → `BUILD_AND_UPLOAD`
  - Variant 不存在，Source 不存在 → `NEED_SOURCE_FOR_REBUILD`
- `GET /api/tasks/{id}/materials/status` 新接口

**验收**：
- Source Missing + Variant 已上传 → 正常复用（REUSE_REMOTE，REASON_SOURCE_MISSING_REMOTE_REUSE）
- Source Missing + 请求新 Variant → 阻断（NEED_SOURCE_FOR_REBUILD）
- 两任务并发构建同 Variant → 只产生一个 Variant / Remote（signature UNIQUE + BUILDING 状态锁）
- Upload 失败 → 不破坏已有 RemoteAsset

**回滚边界**：Phase 4 是关键切换点。必须保证 assets.json 仍可读（作为 legacy fallback），Planner 优先查 Library DB，DB miss 时退化到 assets.json。

---

### Phase 5：Legacy Asset Migration（旧 assets.json 迁入）

**目标**：把现有 assets.json 的 asset 接入 Library DB 的 Variant / RemoteAsset，不重传。

**交付**：
- `asset_library/migration.py`：Lazy Migration
- 打开旧 Task（只有 `file` 无 `revision_id`）→ resolve legacy file → register/dedup revision → 写 revision_id
- 已有 assets.json 且 asset 有效 → 直接创建 Variant + RemoteAsset，绑定旧 asset_id
- 三种 Legacy 情况：
  - Source ✅ + Asset ✅ → 完整迁移（Hash Source → Revision → Transform → Variant → Existing Asset）
  - Source ❌ + Artifact ✅/❌ + Asset ✅ → 建 Revision Metadata（Source=MISSING）+ 从 Artifact 生成 Preview + 标 `LEGACY_IDENTITY`
  - Source ❌ + Artifact ❌ + Preview ❌ + Asset ✅ → `OPAQUE_LEGACY_ASSET`，进"需修复"列表，禁止盲用
- 不一次迁移全部 data，按需触发 + 手动批量工具

**验收**：
- 老 Task 有 assets.json → Lazy Migration，不重传
- 只剩旧 Asset ID → 标记需修复，禁止盲用
- 迁移后 assets.json 标记为 Legacy（仍可读，最终退出）

**回滚边界**：Phase 5 只读 assets.json 写 Library DB，不删 assets.json。如果 DB 出问题，assets.json 仍是 fallback。

---

### Phase 6：完整素材库页面（UI 层）

**目标**：独立一级页面，承担生命周期管理。

**交付**：
- 素材库页面：列表 / 详情 / 引用 / Variant / Preview / 源路径
- 卡片只展示用户信息（Preview/名称/类型/时长分辨率/本地状态/云端状态/任务引用数）
- 详情页：Revision / SourceLocation / Variant / RemoteAsset / 使用任务
- 筛选：全部/图片/视频/音频 + 本地可用/仅云端/需修复 + 名称搜索
- 导入素材入口

**验收**：
- 能看到"我有什么素材""素材在哪""是否还有 Source""有哪些 Variant""哪些任务使用"
- "仅云端"显示已有可复用 Variant 数，不写"永久可用"
- OPAQUE_LEGACY_ASSET 进"需修复"列表

**回滚边界**：Phase 6 纯前端 + 只读 API，不影响 Runner。

---

### Phase 7：Source Cleanup / Manage / Restore（最容易误删，最后做）

**目标**：开放托管 / 清理 / 恢复。

**交付**：
- 托管到素材库：Copy to library managed source → 校验 Hash → 注册 Managed Location
- 清理本地源：清理前检查（Revision → Task Bindings → 各 Task Desired Transform → Variant → Remote Asset），所有任务都有 Remote Variant 才提示可安全清理
- 恢复源文件：用户选文件 → 算 Hash → 相同则恢复 Revision + 增 SourceLocation；不同则提示作为新版本导入
- 删除 data_dir 新规则：扫描 DATA_DIR SourceLocations 是否有其他有效 Location / 其他 Task Binding；只删 tasks + data_dir 物理文件 + 相关 runtime，不删 Library Managed Source / Remote Assets / Library Item
- 数据完整性检查：DB Revision 是否有 Preview / SourceLocation 路径是否存在 / Variant Artifact 状态 / RemoteAsset metadata / TaskBinding 引用 / 重复 content_hash / 孤儿 Preview/Artifact
- 第一阶段只报告不自动 GC Remote Asset

**验收**：
- Managed Source + 删除原 data_dir → Source 仍正常
- 删除 data_dir Source → Library Item 变"仅云端"，不删 Asset
- External Disk 拔出 → 状态 unavailable，不删 Location
- 恢复同 Hash Source → 恢复原 Revision
- 恢复不同 Hash → 创建新 Revision
- 清理前能正确提示"以下 N 个素材删除后将变为仅云端"

**回滚边界**：Phase 7 涉及删除，必须有 dry-run + 确认 + 完整性检查。任何删除操作前必须能回退。

---

## 5. 核心测试矩阵（每个 Phase 完成后必须全过）

| 场景 | 预期 | 主要验证 Phase |
|------|------|----------------|
| 当前目录第一次选文件 | 自动入库并绑定 Revision | Phase 2 |
| 另一 data_dir 选择内容相同文件 | 命中同 Revision | Phase 1/2 |
| 素材库直接选择已有素材 | 不复制 Source | Phase 2/6 |
| 同 Revision + 同 Transform | 复用同 Remote Asset | Phase 3/4 |
| 同 Revision + 新 Transform | 新建 Variant | Phase 3/4 |
| Source Missing + Variant 已上传 | 正常复用 | Phase 4 |
| Source Missing + 请求新 Variant | 阻断并要求恢复 Source | Phase 4 |
| 覆盖同路径文件 | 创建新 Revision，不污染旧 Task | Phase 1/2 |
| 删除 runtime/work | 已有 Remote Variant 正常复用 | Phase 3 |
| 删除 data_dir Source | Library Item 变仅云端，不删除 Asset | Phase 7 |
| Managed Source + 删除原 data_dir | Source 仍正常 | Phase 7 |
| External Disk 拔出 | 状态 unavailable，不删除 Location | Phase 7 |
| 恢复同 Hash Source | 恢复原 Revision | Phase 7 |
| 恢复不同 Hash | 创建新 Revision | Phase 7 |
| 两任务并发构建同 Variant | 只能产生一个 Variant / Remote | Phase 3/4 |
| Upload 失败 | 不破坏已有 Remote Asset | Phase 4 |
| 老 Task 有 assets.json | Lazy Migration，不重传 | Phase 5 |
| 只剩旧 Asset ID | 标记需修复，禁止盲用 | Phase 5 |

---

## 6. 三个参考音频场景的重构落地

重构目标之一是改成显式 audio model。迁移策略：

### 6.1 目标模型

```json
// 视频 + 提取音频
{"video": {"revision_id": "rev_video"}, "audio": {"mode": "extract_from_video"}}

// 视频 + 独立音频
{"video": {"revision_id": "rev_video"}, "audio": {"mode": "independent", "revision_id": "rev_audio"}}

// 纯音频
{"video": null, "audio": {"mode": "independent", "revision_id": "rev_audio"}}
```

### 6.2 迁移期兼容

V1.3 用 `pass_reference_video` / `file` / `audio_file` 组合区分三场景。Phase 2 接入时：

- Task JSON 同时存 `file`/`audio_file`（legacy）和 `revision_id`（新）
- factory 读 `revision_id` 优先，缺失则退化到 `file`
- `_resolve_transform("audio")` 的 **音频源时长规则必须保留**（`seedance_duration = max(4, ceil(音频源时长))`，音频源 = audio_file 或纯音频 file，不是视频时长）——这是之前踩过的坑

### 6.3 前端交互保留

- 「📹 视频 / 🎵 音频」两个 tab 保留
- `switchRefTab` 只切显示不清空
- `formTask` 按当前 tab 取数据
- `editTask` 回填 audio_file 到音频字段
- 有独立音频时置灰"传参考音频"
- 上传/选择按文件类型自动归 tab

这些在 Phase 2 前端重写时必须原样保留语义。

---

## 7. 并发与原子性要求（贯穿所有 Phase）

- `source_revisions.content_hash` UNIQUE：并发导入同文件 → Unique Constraint → 读已有 Revision
- `variants.signature` UNIQUE + `BUILDING/READY/FAILED` 状态：同 Signature 只允许一个 Build/Upload
- Upload 原子性：Build Artifact → Upload → 拿 asset_id → Transaction 写 RemoteAsset；上传失败不删已有 RemoteAsset
- Preview 原子性：generate tmp → validate → atomic rename

---

## 8. 不做的事（第一期明确排除）

- 复杂文件夹分类
- AI 自动标签
- 跨用户共享
- 权限管理
- 智能推荐
- 复杂云端 GC
- 多 Provider Asset
- 复杂版本 diff

---

## 9. 最终职责边界（作为验收基线）

| 组件 | 职责 |
|------|------|
| Asset Library Page | 我有什么素材？素材在哪？是否还有 Source？有哪些 Revision/Variant？哪些任务使用？是否可清理？ |
| Data Dir Browser | 这个任务目录当前有哪些真实文件？这些文件和 Library 的对应关系？ |
| Task Editor | 这个任务选择哪些 Revision？如何使用这些素材？（不管文件生命周期） |
| Asset Planner | 当前请求对应哪个 Variant？Reuse / Build / Upload / Block？ |
| Runtime | 临时处理（不是素材库） |
| Output | 最终生成结果（和素材身份完全解耦） |

---

## 10. 实施前的检查清单

在开始 Phase 0 之前，确认：

- [ ] 用户已确认采用本方案（Library + Revision + Variant）
- [ ] 用户已确认 `data/_asset_library/` 作为 Library 根目录
- [ ] 用户已确认 SQLite 作为 Library DB
- [ ] 用户已确认 Lazy Migration 策略（不一次全量扫描）
- [ ] 用户已确认三种参考音频场景的显式 model 迁移路径
- [ ] 用户已确认 Phase 顺序不可跳步
- [ ] 用户已确认每个 Phase 完成后跑测试矩阵

---

## 11. 一句话总结

**素材从此属于全局 Library，而不是属于某个任务文件夹；任务只是引用素材。**

整个重构以 `revision_id` 为身份中枢，以 `Variant Signature` 为复用中枢，以 `RemoteAsset` 为云端资产载体，Task 只持有 `revision_id + transform`，不再持有 path 或 asset_id。现有 `assets.json` 作为 Legacy fallback，直到 Phase 5 迁移完成后退出。
