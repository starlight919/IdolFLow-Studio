# Seedance 素材库演进路线图（保守版）

> 版本：V2.0（2026-08-16）
> 状态：**路线已收敛**——Phase 1 已实施，Phase 2/3 按需推进，全局素材库改为远期可选方向（暂不安排）
> 关联文档：`Asset_Design.md`（现有实现）、`Video_Task_Workflow.md`、`Singing_Video_Guide.md`、`VIDEO_LOCATIONS.md`
> 实现文件：`idolmv_pipeline/video_tasks/{planner.py,runner.py,store.py,factory.py,models.py}`、`idolmv_pipeline/web/handlers.py`、`idolmv_pipeline/web/static/modules/task.js`

---

## 1. 设计目标

回答「素材库要不要重构、改到哪一步」这一决策问题，核心结论：

1. **现有目录约定已足够好** → 不重设计 location、不迁移数据路径
2. **先修确定存在的逻辑漏洞** → Phase 1（已实施）
3. **小步增强按需做** → Phase 2/3（可选，独立可回滚）
4. **全局素材库改为远期可选方向** → 暂不安排，仅记录将来怎么接入

> **一句话结论**：目录布局与身份模型维持现状；先把确定存在的逻辑漏洞修掉，把全局素材库从「待实施的重构」改为「有真实需求再考虑的远期方向」。

---

## 2. 核心设计原则

### P1. 划不来的时候，不重构

- 全局素材库（Library / SQLite / Revision / Variant）要动 planner / runner / store / factory / handlers / task.js 全链路，Task JSON 要双读兼容 `revision_id`，assets.json 要做 Legacy fallback——任何一步出错都会影响**正在运行的任务**。
- 而它解决的问题（跨文件夹重复上传同一文件）当前**并不常见**。
- **结论**：不做近期重构。

### P2. 目录布局即身份模型，不做路径迁移

- 素材身份 = `task_dir + 相对路径` + 指纹，与磁盘布局强绑定，正是它**简单可靠**的原因。
- 改成全局身份（Content Hash）需迁移所有存量 `assets.json` 与任务 JSON，但现有布局**没有阻碍以后扩展**——真要上全局库时，现有 `data/<文件夹>/` 结构可以直接当导入源用，无需现在预先改造。

### P3. 已有复用语义全部保留

- `assets.json` + Artifact Signature 已覆盖主要复用场景：源未变 + 参数未变 → 复用云端；源/参数变化 → 自动重建重传；源删除但云端资产有效 → 仍可复用。
- 保守路线下，这些语义**一条不改**。

---

## 3. 总体模型（三层，维持现状）

```
data/<任务文件夹>/                    ← 素材与任务数据（身份边界）
  ├── anchors/                       Anchor 源图
  ├── references/                    参考音视频源文件
  ├── tasks/                         Video 任务配置（*.json）
  └── seedance/assets.json           ⭐ 云端资产缓存（按 data_dir 隔离）

runtime/work/<任务文件夹>/            ← 临时处理缓存（可随时清理）
runtime/outputs/<任务文件夹>/<run_id>/ ← 生成结果（最终产物）
```

| 层 | 目录 | 职责 | 变化 |
|----|------|------|------|
| **素材数据** | `data/<文件夹>/` | 源文件、任务配置、`assets.json` | 无 |
| **处理缓存** | `runtime/work/<文件夹>/` | 提取音频 / 切片 / 补齐时长的中间产物 | 无（可清理） |
| **生成结果** | `runtime/outputs/<文件夹>/<run_id>/` | `final.mp4` / `result.mp4` / manifest | 无 |

> **明确排除**（本路线图不引入）：SQLite、`data/_asset_library/`、LocationResolver、`revision_id` schema 变更、`assets.json` 退役。

---

## 4. 素材身份与缓存签名（维持不变）

### 4.1 素材身份

| 项 | 现状 | 说明 |
|----|------|------|
| Task 素材字段 | `references[].file / audio_file`、`anchors[].file` | 相对 `task_dir` 的路径，**不引入 `revision_id`** |
| Asset key | `anchor_<key>` / `reference_<name>_<idx>` / `<ref_name>:audio` | 基于位置 |
| 资产缓存 | `<task_dir>/seedance/assets.json` | `{<key>: asset_id, <key>__source: {path,size,mtime_ns}, <key>__transform: {...}}` |

### 4.2 决策引擎语义（保留）

| 语义 | 说明 |
|------|------|
| `plan_material(InspectedMaterial) → AssetDecision` | 5 个 Action 不变（REUSE_REMOTE / UPLOAD_EXISTING_ARTIFACT / BUILD_AND_UPLOAD / NEED_SOURCE_FOR_REBUILD / NEED_MATERIAL_REBIND） |
| 「资产存在」 vs 「能否复用」分离 | 显示「已上传」不依赖 `artifact_valid`；复用（REUSE_REMOTE）需 `artifact_valid` |
| `_resolve_transform("audio")` | `seedance_duration` 基于**音频源自身时长**（`audio_file` 或纯音频 `file`），不是视频时长 |

> **重要（历史踩坑点）**：第 4.2 行 `seedance_duration` 的音频源时长规则，任何改动**必须保留**，否则已上传的音频资产会反复误显示「未上传」并重传。

---

## 5. 决策矩阵（本次收敛的决策依据）

| 决策项 | 结论 | 理由 |
|--------|------|------|
| 是否重设计 location（`data_root`/`work_root`/`output_root`） | ❌ 否 | 现有三层目录职责清晰、文档与磁盘一致，重构划不来 |
| 是否迁移数据路径 | ❌ 否 | 路径即身份，迁移需动全量存量数据，无必要性 |
| 是否近期引入全局素材库（Library/SQLite/Revision/Variant） | ❌ 否 | 全链路改造风险高，解决的问题当前不常见 |
| 是否修已确认的逻辑漏洞 | ✅ 是（Phase 1） | 小改动、不动数据布局、确定性收益 |
| 是否做小步增强（稳定 Material ID / 跨文件夹提示等） | 🔶 按需（Phase 2） | 真遇到麻烦才做，独立可回滚 |
| 是否做只读素材总览页 | 🔶 按需（Phase 3） | 确有「我有哪些素材」需求时再做，不新增存储 |
| 全局素材库是否排期 | ❌ 否 | 改为远期可选方向，仅记录将来怎么接入 |

---

## 6. Phase 1：正确性修复（已实施 ✅，2026-08-16）

一批经过验证的逻辑漏洞，全部是**小改动、不动数据布局**。

### 6.1 后端

| # | 修复 | 位置 | 说明 |
|---|------|------|------|
| 1 | `adapter_from_task` 用 task id 而非 data_dir 解析 task_dir | `factory.py` | `id != data_dir` 的任务会找错素材目录（`validate` 已算出 `data_dir`，直接使用） |
| 2 | `clear_assets` 子串匹配误伤 | `store.py` | `category in k` 会连带删除含相同子串的其他键（如 reference 名含 "audio"）；改为精确匹配主键 + `__source/__transform` 边车键 |
| 3 | `list()` 排序 stat 竞态 | `store.py` | glob 与排序之间文件被删会让整个任务列表 500；`_safe_mtime` 兜底 0 |
| 4 | `pass_reference_audio=False` 仍规划/上传音频 | `runner.py` `_plan_all` | motion 模式 / 手动关闭时不传音频却仍上传浪费且污染 Status 面板；改为跳过 |
| 5 | 音频源缺失时残留过期指纹标记 | `runner.py` `prepare` | 源不存在时清掉 `audio.src.json`，避免残留指纹误判缓存有效 |

### 6.2 前端（`task.js`）

| # | 修复 | 说明 |
|---|------|------|
| 1 | **独立音频按索引配对错位（最重要）** | `editTask` 回填 `audio_file` 时 `filter(Boolean)` 丢掉空位，`formTask` 按行号配对 → 编辑再保存会把音频挂到错误的视频上。现改为按 reference 顺序生成含空行占位的 `#audio-refs`，`formTask` 用原始行（不过滤空行）配对，并在音频数 > 视频数时报错而非静默丢弃 |
| 2 | 嵌套任务文件夹被截断 | `editTask` 回填 `#task-dir` 用 `data_dir`（仅末级目录名），嵌套路径保存后任务跑到错误位置；改为从 `task_dir` 绝对路径剥 `data_root` 前缀还原完整相对路径 |
| 3 | 更新任务先删后存可能丢数据 | `_doSave` 改为**先保存新任务成功、再删旧任务**，保存校验失败不再连带删除旧任务 |
| 4 | `resetForm` 残留音频 tab | 上次编辑纯音频任务后点「新任务」，表单停留在音频 tab、pad-mode/传音频行仍隐藏，新任务被误存为纯音频；重置时显式切回视频 tab |
| 5 | 「启动」遇改名后断头路 | `startCurrent` 设置的 `_pendingStart` 此前没人接住；保存方式弹窗成功后现在接续 `requestStart`，无需再手动点启动 |
| 6 | 素材选择「覆盖」与上传「追加」不一致 | `confirmAssetSelection` 原来整体替换字段内容，会丢掉未重新勾选的已有项；统一为合并去重（`_mergeIntoField`），音频优先填空占位行保持行号对齐 |
| 7 | chips 移除音频丢占位 | `removeVideoAsset` 在 `#audio-refs` 上改为空行占位而非删行，保持配对对齐 |
| 8 | `checkMissingAssets` 吞错 | 服务异常时横幅直接消失，用户误以为素材齐全；改为显示「检测失败」 |
| 9 | 切换任务文件夹残留编辑态 | `chooseFolder` 清空素材后同步清 `currentTask` / `originalPadMode`，重置按钮与保存弹窗行为一致 |

---

## 7. Phase 2（可选，按需）：不动布局的小增强

> 只有当实际用起来真遇到麻烦时才做，每一项都**独立、可单独回滚**。

| # | 增强 | 说明 |
|---|------|------|
| 1 | Anchor 稳定 Material ID | `anchor-N` 位置键导致列表重排即重传。可在 Task JSON 里为 anchor 持久化一个稳定 key（`anchor_asset_keys` 机制已存在，只差生成与回填），不影响 assets.json 结构 |
| 2 | 跨文件夹复用提示（只读） | Status 面板 / Data Dir Browser 增加「该文件在其他文件夹已上传过」的提示（扫描各 `seedance/assets.json` 的 `__source` 指纹比对），只提示不自动复用，避免跨文件夹共享 assets.json 带来的清理/一致性问题 |
| 3 | 音频扩展名识别增强 | `_resolve_transform("audio")` 与前端的音频正则补充 `.aiff/.opus/.wma` 等少见格式，避免按视频时长误判 |
| 4 | `trim_duration` 死字段清理 | `ReferenceSpec.trim_duration` 没有任何地方用到，却被 factory 误当成 `duration` 填入；删除或改为显式 kwargs 传参 |

---

## 8. Phase 3（可选）：素材总览页面（只读）

如果确有「我有哪些素材」的查看需求，做一个**只读**的素材总览页：

| 项 | 设计 |
|----|------|
| 数据来源 | 扫描 `data/*/seedance/assets.json` + 源文件存在性 |
| 展示 | 按文件夹分组展示已上传资产、源状态、被哪些任务引用 |
| 边界 | 不新增存储、不迁移数据、不提供清理/托管操作（删除仍走现有 data_dir 级联删除） |
| 实现 | 纯前端 + 只读 API，随时可下线 |

---

## 9. 远期方向（暂不安排，仅记录）

全局素材库（Library + Content Hash + Variant）作为**远期可选**方向保留在 Git 历史（本文件 v1 版本）中。

若未来真的要做（例如多项目共享素材成了常见需求），可以从这几步开始：

1. 以现有 `data/<文件夹>/` 为导入源做**增量迁移**，不要求一次性全量
2. 现有路径布局无需预先改造，迁移工具可直接读取当前 `assets.json` + `__source` 指纹

> 在那一刻到来之前，本路线图**明确排除**：SQLite、`data/_asset_library/`、LocationResolver、`revision_id` schema 变更、assets.json 退役。

---

## 10. 验收基线（现有行为必须始终成立）

| # | 场景 | 预期 |
|---|------|------|
| 1 | 源文件 + 处理参数均未变 | REUSE_REMOTE，不重传 |
| 2 | 源文件被编辑（size/mtime 变） | BUILD_AND_UPLOAD（SOURCE_CHANGED） |
| 3 | pad_mode / 裁剪 / 分段变化 | 重建重传（TRANSFORM_CHANGED） |
| 4 | 删除 `runtime/work` | 已上传资产正常复用；需重建时自动重建 |
| 5 | 源文件删除 + 云端资产仍匹配 | REUSE_REMOTE（SOURCE_MISSING_REMOTE_REUSE） |
| 6 | 源文件删除 + 参数变化 | 阻断（NEED_SOURCE_FOR_REBUILD） |
| 7 | 纯音频 / 视频+独立音频 / 视频+提取音频 三场景 | 按 §4.2 规则正确区分，`seedance_duration` 基于音频源时长 |
| 8 | `pass_reference_audio=false` | 不规划、不上传音频资产 |
| 9 | 编辑任务再保存 | `audio_file` 与视频的配对关系不变 |
| 10 | 改名/改文件夹后更新任务 | 新任务保存成功后才删除旧任务 |

---

## 11. 相关文件

| 文件 | 职责 |
|------|------|
| `video_tasks/planner.py` | 决策引擎（Action/ReasonCode/`plan_material`） |
| `video_tasks/runner.py` | 指纹、inspect、`upload()`（plan→prepare→upload） |
| `video_tasks/store.py` | 任务存取、`validate`、`clear_assets`、`list` |
| `video_tasks/factory.py` | adapter 构造、`adapter_from_task`、`_timestamp_offset` |
| `video_tasks/models.py` | `ReferenceSpec` / `AnchorSpec` / `VideoTaskAdapter` 数据模型 |
| `web/handlers.py` | Status API（`_task_assets`） |
| `web/static/modules/task.js` | Asset 面板渲染、表单保存/回填 |

---

## 12. 一句话总结

**目录布局与身份模型维持现状；先把确定存在的逻辑漏洞修掉，把全局素材库从「待实施的重构」改为「有真实需求再考虑的远期方向」。**
