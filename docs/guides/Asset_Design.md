# Seedance 素材 Asset 缓存与复用设计

> 版本：V1.4（2026-08-16）
> 实现文件：`idolmv_pipeline/video_tasks/planner.py`、`runner.py`、`factory.py`、`web/handlers.py`

---

## 1. 设计目标

解决素材上传到 Seedance 云端的**缓存复用**与**任务编辑**问题，核心目标：

1. **源文件未变 → 自动复用已上传资源**（不重复上传、不重复付费）
2. **源文件或处理参数变化 → 自动重新上传**（保证结果正确）
3. **源文件被删除 → 合理处理**（能复用则复用，不能则明确提示重选）
4. **编辑任务（改 prompt/歌词/pad_mode）不触发无谓重传**

---

## 2. 核心设计原则

### P1. 编辑任务 ≠ 上传素材

- 修改 Prompt、歌词、镜头策略等**不影响素材内容**，绝不应触发素材重传。
- 只有 **源文件** 或 **影响素材内容的处理参数**（对齐/裁剪/分段）变化，才需要重新处理并上传。

### P2. 统一决策引擎

- Runner 与后端 Status API **共用同一个 AssetPlanner**，避免"UI 显示复用、Runner 实际失败"的不一致。
- Asset 面板状态来源 = Planner Decision（单一决策来源），前端不做二次判断。

### P3. 任务要求素材"可识别"，而非"本地存在"

- 素材能否用于任务，取决于能否**识别其内容**（有源文件或 Snapshot），而非本地文件是否存在。

---

## 3. 总体模型（五层）

```
Material（素材）──引用──> Source（源文件）
     │                      │
     ├──生成──> Artifact（处理产物）──> Remote Asset（云端资源）
     │                        │
     └──快照──> Snapshot（给用户看的版本）
```

| 层 | 含义 | 说明 |
|----|------|------|
| **Material** | 任务里的一个逻辑素材 | Anchor 图 / 参考音频 / 参考视频 |
| **Source** | 源文件 | 用户提供的原始素材，可被编辑/删除 |
| **Artifact** | 处理产物 | 由 Source 加工生成（提取音频、切片、补齐时长） |
| **Snapshot** | 给用户看的版本 | Source 缺失时用于识别内容 |
| **Remote Asset** | 云端资源 | 上传到 Seedance 的持久对象，`assets.json` 记录 |

---

## 4. 素材类型与处理产物

| Material | Source | Artifact（处理产物） | Remote Asset key |
|----------|--------|---------------------|------------------|
| Anchor 图 | `task_dir/anchor.file` | 无（直接上传源图） | `anchor_anchor-N` |
| 参考音频 | `task_dir/(audio_file or file)` | `audio.mp3` / `audio_padded.mp3` | `reference-1:audio` |
| 参考视频 | `task_dir/reference.file` | `segment_XX.mp4` | `reference_参考_00` |

### 4.1 参考音频的三种输入场景（重要）

任务的「参考音频」有**三种输入场景**，靠「📹 视频 / 🎵 音频」两个 tab 与 `pass_reference_video` 区分，**切勿混淆**：

| 场景 | 前端操作 | `pass_reference_video` | `file` | 音频来源 | 音频准备 | 视频切片 | 提交内容 |
|------|---------|-----------------------|--------|---------|---------|---------|---------|
| **① 视频 + 视频提取音频**（可选用不用） | 📹 视频 tab 选视频，勾选/取消「传参考音频」 | `true` | 视频文件 | **从视频 `extract_audio`** | 提取 | 走 `segment_XX` | `video_url` + `audio_url`（勾选时） |
| **② 纯音频** | 🎵 音频 tab 选音频 | `false` | 音频文件 | 音频文件本身 | `copyfile` 直接拷贝 | **跳过** | 只 `audio_url` |
| **③ 视频 + 独立音频**（对口型） | 📹 视频 tab 选视频 + 🎵 音频 tab 选独立音频 | `true` | 视频文件 | **独立音频 `audio_file`**（不从视频提取） | 用独立音频 | 走 `segment_XX` | `video_url` + `audio_url`（独立音频） |

> **关键设计：视频 + 独立音频对口型**（📹 与 🎵 两个 tab 可共存）。
> 同时传视频与独立音频时，音频作为**独立对口型源**保存并生效（视频模仿动作、音频对口型），生成时用独立音频而非从视频提取。两个 tab 内容互不覆盖：「选择文件 / 上传」按**当前 tab** 归位（视频 tab → 视频字段、音频 tab → 音频字段），编辑回填时 `audio_file` 一并回填到音频字段。未传独立音频时才回退场景 ①（从视频提取）。

**源文件选择逻辑**：`source = task_dir / (reference.audio_file or reference.file)`。
- 场景 ①：前端不设置 `audio_file` → `source = file`（视频）→ 从视频提取音频
- 场景 ②：前端不设置 `audio_file` → `source = file`（音频）→ 直接拷贝
- 场景 ③：前端设置 `audio_file` → `source = audio_file`（独立音频）→ 视频仍走切片，音频用独立音频

> **切换边界（视频 ⇄ 纯音频）**：`switchRefTab` 只切换显示、**不清空**另一字段的数据，保存时 `formTask` 按**当前 tab** 取数据（`isAudioTab ? #audio-refs : #references`）：
> - 停在「🎵 音频」tab → 生成纯音频 references（场景 ②），残留的视频 `#references` 不混入 ✅
> - 停在「📹 视频」tab → 生成视频 references（场景 ①/③）；若 `#audio-refs` 有独立音频，作为 `audio_file` 一并保存（场景 ③，对口型），不清空 ✅
> 编辑任务回填时 `editTask`：纯音频任务清空 `#references`；视频任务若带 `audio_file` 则回填到音频字段（编辑可见、可改）。

> **音频 transform 匹配基于「音频源自身时长」**（`_resolve_transform("audio")`）：
> - `seedance_duration` = `max(4, ceil(音频源时长))`，其中**音频源** = `audio_file`（独立音频）或纯音频任务的 `file`——而非视频的时长。因为独立音频/纯音频与视频时长可能不同（如 21.1s 音频 vs 视频 16.8s），用视频时长会误判不匹配、反复重传。
> - `kind` = `audio_padded`（音频源时长 < seedance_duration，会被 pad）或 `audio`；status 面板未 prepare（`audio_file_url` 未设）时按「音频源时长 < seedance_duration」推断，与 prepare 后产物一致，避免音频资产误显示「未上传」。

---

## 5. 缓存签名（Artifact Signature）✅

产物缓存是否复用，由 **Artifact Signature** 决定：

```
signature = hash(源文件指纹 + 处理参数 transform + 处理器版本)
```

- **源文件指纹**：`{path, size, mtime_ns}`（判断是否编辑；忽略 path 的比较用 `size+mtime_ns`）
- **处理参数 transform**：影响产物内容的参数（`pad_mode`/`split`/`crop`/`duration` 等）
- **处理器版本**：产物生成逻辑变化时递增，强制重建缓存

**效果**：
- 源文件或处理参数任一变化 → 签名变 → 产物重建 → 云端 Asset 自动重传 ✅
- 均未变 → 签名不变 → 复用 ✅

> 每个处理产物旁的 `.src.json` marker 记录该签名（`{signature, source, transform, processor}`）。

---

## 6. 四状态模型

素材在任意时点的产品状态（由 Source / Artifact / Asset / Snapshot 组合）：

| 状态 | Source | Asset | 可识别 | 能否提交 | UI 文案 |
|------|--------|-------|--------|---------|--------|
| **A. LOCAL_READY** | ✅ | 任意 | ✅ | ✅ | 本地素材可用 |
| **B. REMOTE_ONLY_IDENTIFIABLE** | ❌ | ✅ | ✅ | ✅（transform 匹配） | 仅云端版本 · 可复用 |
| **C. REMOTE_ONLY_OPAQUE** | ❌ | ✅ | ❌ | ❌ | 无法识别 · 请重新选择 |
| **D. MISSING** | ❌ | ❌ | ❌ | ❌ | 素材缺失 · 请重新选择 |

> B 状态（仅云端可复用）依赖 Snapshot 识别内容；源缺失且无法识别内容时视为 C/D 阻断（需重选）。

---

## 7. AssetPlanner 决策引擎 ✅

### 7.1 五种 Asset Action

| Action | 含义 |
|--------|------|
| `REUSE_REMOTE` | 直接复用已上传的云端 Asset |
| `UPLOAD_EXISTING_ARTIFACT` | 本地产物已有效，仅上传产物 |
| `BUILD_AND_UPLOAD` | 需重建产物并上传 |
| `NEED_SOURCE_FOR_REBUILD` | 源缺失但需重建，阻断并提示 |
| `NEED_MATERIAL_REBIND` | 素材缺失/不可识别，阻断并提示重选 |

### 7.2 决策逻辑（有源 / 无源两分支）

```
有源：
  本地产物有效（签名匹配）？
    ├─ 有「有效 Asset」（对应当前产物）→ REUSE_REMOTE（复用云端）
    └─ 无「有效 Asset」→ UPLOAD_EXISTING_ARTIFACT（本地产物有效，重新上传）
  产物无效但 Asset transform 匹配（含旧资产兜底） → REUSE_REMOTE
  否则 → BUILD_AND_UPLOAD（重建产物并上传）

无源：
  有 Asset 且可识别：
    transform 匹配 → REUSE_REMOTE（复用云端）
    transform 变化 → NEED_SOURCE_FOR_REBUILD（需源重建）
  有 Asset 但不可识别 → NEED_MATERIAL_REBIND
  无 Asset → NEED_MATERIAL_REBIND
```

> **「资产是否存在」与「能否复用」分离**（`_inspect_reference` / `_inspect_audio`）：
>
> **资产是否存在**（用于 `asset_state` / `asset_id` 显示，"已上传" vs "未上传"）：资产存在 + 资产对应当前产物——
> 1. 资产存在（`assets.json` 有该 key 的 asset id）；
> 2. 资产对应当前产物：资产有 `__transform` → 其 transform 与当前 desired 一致；旧资产无 `__transform` → 上传时的产物指纹 `__source` 与当前本地产物一致（`size + mtime_ns`，忽略 path）。
>
> 不依赖 `artifact_valid`：status 面板未 prepare 时无法确认产物对应当前源，但"资产已上传"这一事实成立，故仍显示"已上传"+ 返回 `asset_id`。
>
> **能否复用**（`REUSE_REMOTE` vs 重传）：在"资产存在"基础上，还要求 **`artifact_valid`**（本地产物 marker 签名匹配当前源）——否则即使资产 `__source` 匹配旧产物，也仅显示"已上传"但 action 走重传（`UPLOAD_EXISTING_ARTIFACT` / `BUILD_AND_UPLOAD`），避免误用残留旧产物。

### 7.3 阻断

任一素材 `can_submit=False` → 整体提交失败，并明确原因（哪个素材、为什么）。

---

## 8. 编辑任务对 Asset 的影响

| 编辑操作 | 是否触发重传 | 原因 |
|----------|------------|------|
| 修改 Prompt / 歌词 / 镜头策略 | ❌ 不触发 | 不影响素材内容 |
| 调整 Anchor 顺序（同一批图） | ✅ 视情况 | Asset key 基于位置，顺序变会换 key（稳定 Material ID 为后续优化方向） |
| 更换某张 Anchor 图 | ✅ 触发 | 源图内容变化 |
| 修改 `pad_mode` / `crop_filter` / `split` | ✅ 触发 | transform 变化 → 产物重建 → 重传 |
| 修改 `seedance_duration` | ✅ 触发 | 影响产物补齐/切片 |

---

## 9. 完整提交流程 ✅

```
PLAN → 阻断检查 → (需要 build 时) PREPARE → 按 action UPLOAD → SUBMIT
```

1. **PLAN**：对每个素材 inspect（Source/Artifact/Asset/transform 状态）→ 产出 AssetDecision
2. **阻断检查**：有 `NEED_*` 则中止并提示
3. **PREPARE**：需要 build 的素材生成/重建产物（含签名 marker）
4. **UPLOAD**：按 action 复用（REUSE）或上传（UPLOAD/BUILD），上传成功写 `__transform`
5. **SUBMIT**：用 Asset id 提交 Seedance 生成

---

## 10. Asset 面板（Status API）

`GET /api/tasks/{id}/assets` 返回每个素材的 **Planner Decision**：

```json
{
  "key": "anchor_anchor-1", "asset_id": "asst_xxx",
  "action": "REUSE_REMOTE", "reason": "CACHE_HIT",
  "source_state": "PRESENT", "artifact_state": "VALID", "asset_state": "AVAILABLE",
  "visibility_state": "IDENTIFIABLE",
  "can_submit": true, "requires_source": false, "block_reason": null
}
```

前端按 `action` 渲染状态徽标（✓ 复用 / 🔄 将重新生成并上传 / ⚠️ 需重选等）。

---

## 11. 设计边界与已知限制

| # | 边界 | 说明 |
|---|------|------|
| 1 | **源文件删除** | 源缺失时若无法识别内容（无 Snapshot），判定 `NEED_MATERIAL_REBIND` 阻断并提示重选；已上传的云端资源仍有效，但需用户重新提供源文件才能继续 |
| 2 | **Anchor Asset key 基于位置** | key 由 `anchor-N` 位置决定，调整 Anchor 顺序会使同一张图换 key 而重复上传；稳定 Material ID 为后续优化方向 |
| 3 | **旧资产无 transform 的兼容** | 有 `__source` 无 `__transform` 时，若产物指纹一致则视为匹配复用；但**产物重建后（`__source` 与当前产物不一致）会视为"无有效资产"走重传**，不复用旧资产 |
| 4 | **资产显示与复用分离（产物重建/换源防误判）** | **核心防误判**：「资产是否存在」（显示"已上传"）= 资产存在 + 资产对应当前产物（`__transform` 匹配 或 `__source` 指纹匹配），**不依赖 `artifact_valid`**（status 面板未 prepare 时仍能显示已上传）；「能否复用」（REUSE_REMOTE）还需 `artifact_valid`（产物 marker 签名匹配当前源）。产物重建或**残留旧切片 + 资产 __source 匹配但产物无 marker/不对应当前源**时，仍显示"已上传"但 action 走重传（`UPLOAD_EXISTING_ARTIFACT` / `BUILD_AND_UPLOAD`），避免误用旧产物 |
| 5 | **跨任务文件夹隔离** | 资产缓存 `seedance/assets.json` 按**任务文件夹（data_dir）** 独立存放，**跨文件夹不共享、不互相复用**。即使两个文件夹有相同文件名的素材（如同名视频），资产也不通用——避免跨任务串数据；若需跨文件夹复用需引入全局内容指纹去重（后续方向） |
| 6 | **云端资源持久有效** | Seedance Asset 为持久化云端对象，正常情况下不会失效；🗑 清缓存仅用于确实需要强制重新上传的场景 |
| 7 | **不传参考音频则不规划音频资产** | `pass_reference_audio=false`（如 motion 模式 / 手动关闭）时，音频不进入提交内容，Planner 也不再为其生成决策或上传（避免无效上传与面板噪音） |
| 8 | **清缓存按键精确匹配** | `clear_assets` 只删除指定主键及其 `__source` / `__transform` 边车键；不再按子串匹配，避免键名含相同子串的素材被连带清除 |
| 9 | **Status API 容错** | 面板接口跳过素材文件与 prompt 校验（`skip_material_check`），即使源缺失或任务数据不完整也能展示素材状态 |

---

## 12. 相关文件

| 文件 | 职责 |
|------|------|
| `video_tasks/planner.py` | 决策引擎（Action/ReasonCode/`plan_material`） |
| `video_tasks/runner.py` | 指纹、inspect、`upload()`（plan→prepare→upload） |
| `video_tasks/factory.py` | adapter 构造、`skip_material_check` |
| `web/handlers.py` | Status API（`_task_assets`） |
| `web/static/modules/task.js` | Asset 面板渲染 |
| `web/static/app.css` | Asset 面板样式 |
