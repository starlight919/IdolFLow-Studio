# Seedance Prompt 设计文档

> 版本：V2.3（七层语义架构 + Lyrics Timestamp 动态渲染 + 时长对齐 offset + 可编辑 Prompt）
> 最后更新：2026-08-15
> 实现文件：`idolmv_pipeline/video_tasks/prompts.py`
> 模板清单与编写规范：见 [`Seedance_Prompt_Templates.md`](./Seedance_Prompt_Templates.md)（前端 custom 模板 + 外部最佳实践 + 维护流程）

主要任务：对口型、动作模仿、动作 + 对口型

## 1. 设计目标

当前主要支持三类生成任务：

* `lip_sync`：人物保持原图状态，按照参考视频 / 音频 / 歌词完成精确对口型
* `motion`：人物保持原有身份与场景，模仿参考视频中的完整身体动作
* `dance_lip_sync`：同时模仿参考视频身体动作，并完成精确对口型

Prompt 设计的核心目标不是简单描述“生成什么”，而是明确：

1. **每个参考素材负责什么**
2. **多个参考素材如何共同约束同一个目标**
3. **发生潜在冲突时，各维度如何处理**
4. **尽量避免重复、互相冲突和过量 negative prompt**

---

# 2. 核心设计原则

## 2.1 Reference Ownership

人物、场景、身体动作等适合采用单一参考职责：

| 目标                | 主要参考            |
| ----------------- | --------------- |
| 人物身份              | 图片1             |
| 五官 / 发型 / 服装 / 体型 | 图片1             |
| 场景 / 光线 / 构图      | 图片1             |
| 身体动作              | 视频1             |
| 动作顺序 / 节奏 / 轨迹    | 视频1             |
| 镜头                | `camera_policy` |

例如：

> 图片1负责人物和场景；视频1只负责动作。

避免视频参考中的人物、服装和场景污染生成结果。

---

## 2.2 Lip Sync 使用多源约束融合

口型不能采用单一 Source of Truth。

歌词、音频和视频同时参与对生成视频口型的约束，但承担不同信息：

| 参考 | 主要作用                     |
| -- | ------------------------ |
| 歌词 | 字词、音节、发音顺序               |
| 音频 | 实际发音、节奏、持续时间、起止、停顿       |
| 视频 | 嘴形、嘴部开合、唇形转换、闭口时机及视觉口型时间 |

因此：

```text
Lip Sync
├── Linguistic Constraint   ← Lyrics
├── Acoustic Constraint     ← Audio
├── Temporal Constraint     ← Audio + Video
└── Visual Lip Constraint   ← Video
```

三种参考不是互相替代，而是共同定义最终口型。

---

## 2.3 Dimension-based Priority

不同参考可能共同影响同一任务，但不同维度拥有不同优先级：

```text
人物身份：
image

歌词内容：
lyrics + audio

发音：
audio + lyrics

口型时间：
audio + video

嘴形：
video + audio

身体动作：
video

场景：
image
```

不要使用简单的：

```text
audio > video > lyrics
```

而应该针对具体约束维度决定 reference。

---

## 2.4 Lyrics Timestamp 作为可选时间增强

前端允许用户对歌词逐句手动打点：

```json
[
  { "text": "冻结那时间", "time": 1.234 },
  { "text": "冻结初遇那一天", "time": 5.678 },
  { "text": "冻结那爱恋", "time": null }
]
```

`time` 表示该句歌词对应的人工时间点。该信息用于增强已有的 Lyrics + Audio + Video 对口型约束，但**不改变原来的 Reference Ownership 和 Lip Sync 主结构**。

设计上遵循：

```text
没有有效 timestamp
→ 完全使用原 V2 Lyrics Prompt

存在有效 timestamp
→ 使用 Timestamped Lyrics Prompt
→ 直接把“歌词 + 时间”写成 Seedance 易理解的任务语言
→ Audio / Video 的原有职责保持不变
```

重要原则：

* timestamp 是 **Lyrics 输入的可选增强**，不是新的独立 Performance Contract。
* `null`、字段语义、校验规则、时间点来源等属于 Builder / 业务层语义，不直接写入 Seedance Prompt。
* 最终 Prompt 只保留模型真正需要执行的内容，例如“1.23s 开始唱某句”“其余歌词自然衔接”。
* 当前只有单点 `time` 时，不人为构造不存在的 `start-end` 区间。

### 2.4.1 时间戳与时长对齐（pad_mode）的 offset 规则

时间戳是在**原始音频**上打的，但「前面补齐」会让音频开头插入静音/静止帧，
导致歌词实际起唱时间整体后移。因此 prompt 里的时间戳需要加上 offset。

| 条件 | offset | 说明 |
|------|--------|------|
| `pad_mode = none` / `back` | **0** | 前面不动，无需偏移 |
| `pad_mode = front` 且未超时长 | `ceil(total) - total` | 前面补的时长，时间轴后移 |
| 超时长（`total > max_duration`） | **0** | 直接截断，无补齐 |

关键原则：

* 只有「前面补时长」才需要 offset，后面补齐/不补齐都不影响歌词起唱时间。
* 超时长（视频超过模型上限 30s / 15s）时，时长对齐失去意义，统一按「截断」处理
  （`pad_mode` 归一为 `none`），offset 必然为 0。
* offset 的计算与「生成前补齐」「生成后裁剪」三处共用同一个量
  `Δ = seedance_duration - original_total`，保证逻辑自洽：
  - front：前面补 `Δ` → 时间戳 +`Δ` → 生成后裁掉前面 `Δ`；
  - back：后面补 `Δ` → 时间戳不动 → 生成后 `-shortest` 裁掉后面；
  - none：不补 → 时间戳不动 → 不裁。

---

# 3. Prompt 总体架构

V2 不再完全按照“图片 / 视频 / 音频 / 歌词”素材顺序追加，而按照模型需要完成的任务组织：

```text
Layer 1  TASK
         ↓
Layer 2  REFERENCE MAP
         ↓
Layer 3  PERFORMANCE
         ├── Motion Contract
         └── Lip Sync Contract
         ↓
Layer 4  PRESERVATION
         ↓
Layer 5  CAMERA
         ↓
Layer 6  QUALITY
         ↓
Layer 7  CUSTOM
```

其中：

* `TASK`：告诉模型当前到底要完成什么
* `REFERENCE MAP`：明确各参考素材职责
* `PERFORMANCE`：描述动作和口型如何执行
* `PRESERVATION`：保持人物、服装、场景
* `CAMERA`：独立控制镜头策略
* `QUALITY`：处理肢体、背景、AI 痕迹等
* `CUSTOM`：追加用户自定义需求

---

# 4. Layer 1 — Task Contract

第一句话直接定义任务。

## `lip_sync`

```text
让图片1中的人物在保持原人物、场景和构图的情况下，
按照参考视频、参考音频和给定歌词完成自然准确的演唱/说话口型。
```

## `motion`

```text
让图片1中的人物完整模仿视频1中的身体动作，
同时保持图片1中的人物身份、服装、场景和整体视觉效果。
```

## `dance_lip_sync`

```text
让图片1中的人物完整模仿视频1中的身体动作，
同时结合参考视频、参考音频和歌词完成准确对口型。
```

Task 层只定义目标，不在这里重复细节约束。

---

# 5. Layer 2 — Reference Map

Reference Map 用于明确素材职责。

## `lip_sync`

```text
@image1 锁定人物身份、脸部、肤色、发型、服装、体型、场景、构图和光线，全程保持一致。
@video1 仅提供视觉口型参考：嘴形、嘴部开合、唇形变化与对应口型时间；不替换人物外观。
@audio1 提供实际发音、音节、节奏、持续时间、发音起止和停顿。
歌词提供准确的字词、音节内容与发音顺序。
外观与身份以 @image1 为准；口型同时满足歌词内容、发音时间与对应时间点正确的视觉嘴形。
```

> 设计依据（社区 R2V 最佳实践，详见 §18）：
> - 每份参考「单一职责」，在 Prompt 中用 `@引用` **显式声明**其职责边界；
> - 用 `@image1 / @video1 / @audio1` 显式引用各素材（而非"图片1负责…"的工程语言）；
> - "负责"类措辞改为**正向、可执行约束**（"锁定…/仅提供…/"），模型无需理解内部设计哲学。
>
> 纯音频（无参考视频）时，本层**不列出视频行**，Layer 1 任务句同步改写为"按照参考音频和给定歌词"，避免出现不存在的"参考视频"。

---

## `motion`

```text
@image1 锁定人物身份、脸部、发型、服装、体型、场景、构图和光线。
@video1 仅提供身体动作参考：姿态变化、动作顺序、运动轨迹、动作幅度与节奏；不复制其画面元素。
```

---

## `dance_lip_sync`

```text
@image1 锁定人物身份、脸部、发型、服装、体型、场景、构图和光线。
@video1 提供身体动作参考，并作为视觉口型时间参考；不替换人物外观。
@audio1 提供实际发音、节奏、音节持续时间、起止和停顿。
歌词提供准确的演唱 / 说话内容与发音顺序。
外观与身份以 @image1 为准；身体动作与口型在同一时间轴中互不干扰。
```

---

# 6. Layer 3 — Performance Contract

Performance 是不同 mode 最核心的差异。

---

## 6.1 Lip Sync Contract

### 三重口型约束

```text
对口型必须同时结合歌词、参考音频和视频1。

歌词用于确定准确的字词、音节和发音顺序，
不得漏字、错字、吞字或增加额外内容。

参考音频用于确定实际发音、节奏、每个音节的持续时间、
发音起止、停顿以及整体时间轴。

视频1用于确定每个发音对应的嘴形、
嘴部开合幅度、唇形转换、闭口时机和连续口型变化。

生成口型必须同时满足：
正确的歌词内容、
正确的发音时间，
以及对应时间点正确自然的视觉嘴形。
不得只依据其中任意一种参考生成口型。
```

### 时间同步

```text
参考音频和视频1共同约束口型时间。

音频用于确认发音实际开始、持续和结束的时间；
视频用于确认对应时间点嘴部开始运动、展开、转换和闭合的时机。

保持声音与嘴部动作处于同一时间轴，
避免声音开始后嘴仍未运动、
声音结束后嘴仍持续发音，
或嘴部动作相对参考出现明显提前或延迟。
```

### 自然微动作

`lip_sync` 默认不是完全静止：

```text
除口型外，仅保留自然眨眼、轻微面部表情、
正常呼吸和极小幅度的自然头部微动。
身体主体保持稳定，不主动增加明显手势或大幅身体动作。
```

---

# 7. Motion Contract

动作模仿重点不是机械复制像素位置，而是保持动作语义、时间和关键姿态。

```text
完整复现视频1从开始到结束的动作编排。

保持相同的：
- 动作顺序
- 动作节奏
- 速度变化
- 身体朝向
- 重心变化
- 手臂轨迹
- 腿部动作
- 动作幅度
- 关键姿态与卡点

不得遗漏动作、交换动作顺序、
增加额外动作、重复动作或自行重新编排。
```

## 身体比例适配

参考视频人物与目标图片人物可能具有不同身高、肩宽和肢体比例，因此：

```text
动作需要自然适配图片1人物原有的身体比例和当前构图。

优先保持动作语义、节奏、方向、轨迹和关键姿态的一致，
不要为了机械复制参考人物的绝对空间位置而拉伸、
扭曲或改变目标人物身体结构。
```

---

# 8. Dance + Lip Sync Contract

`dance_lip_sync` 同时维护两个表演通道：

```text
Body Performance ← Video
Lip Performance  ← Lyrics + Audio + Video
```

Prompt：

```text
身体动作从开始到结束完整跟随视频1，
保持原动作顺序、节奏、速度变化、运动轨迹和关键姿态。

动作自然适配图片1人物的身体比例，
不得漏动作、重复动作、增加动作或改变动作顺序。

口型同时结合歌词、参考音频和视频1：
歌词确定字词和发音顺序；
音频确定实际发音、节奏、起止和停顿；
视频1确定对应时间点的视觉嘴形、开合和唇形转换。

身体动作和口型保持在同一完整时间轴中。
不得为了完成身体动作而导致口型提前或延迟，
也不得为了对口型而跳过、重复或重新排序身体动作。
```

这里不再使用：

> 舞蹈和口型同等重要

而是明确两个 channel 分别需要满足什么。

---

# 9. Layer 4 — Preservation Contract

所有模式通用。

```text
始终保持图片1中的同一人物。

全程保持人物脸型、五官、肤色、发型、发色、
服装、体型和身体比例稳定。

保持图片1中的原始场景、主要背景元素、光线和视觉风格。
参考视频中的人物身份、服装和场景不得替换图片1中的对应内容。
```

对于动作模式追加：

```text
即使发生转头、抬手、快速运动、身体旋转或局部遮挡，
人物脸部身份和整体外观仍需保持稳定。
```

---

# 10. Layer 5 — Camera Policy

镜头不再属于全局强制规则，而作为独立策略。

支持：

```python
camera_policy = "locked" | "keep_image" | "follow_video"
```

## `locked`

适合普通对口型：

```text
镜头固定，保持图片1原始视角和构图。
不进行推拉、摇移、旋转、缩放或主动重新构图。
```

## `keep_image`

默认用于动作模仿：

```text
整体保持图片1的原始镜头、视角和构图。
允许为了完整容纳人物动作产生必要的小幅构图适配，
但不主动增加额外电影式运镜。
```

## `follow_video`

仅在明确需要模仿参考视频运镜时使用：

```text
人物动作和镜头运动均参考视频1，
同时保持图片1中的人物身份、服装、场景和视觉外观。
```

### 默认值

```python
lip_sync       -> locked
motion         -> keep_image
dance_lip_sync -> keep_image
```

---

# 11. Layer 6 — Quality Guard

统一质量约束保持简洁，避免大量重复 negative prompt：

```text
保持人物动作连续自然，脸部、身体和手部结构稳定。

避免身份漂移、五官变化、关节扭曲、肢体拉伸、
穿模、机械抖动、画面闪烁和背景形变。

保持真实自然的皮肤与头发质感，
避免明显塑料感、过度平滑和不自然 AI 纹理。

不得生成字幕、歌词文字、水印、logo、贴纸、
平台图标或原画面不存在的叠加元素。
```

## 11.1 防脏画面（专项负向补充）

Quality Guard 默认保持简洁，避免堆叠过多 negative prompt。
但当生成偶发**脏污、细碎噪点、高频纹理、密集小装饰**时，
可追加一段「防脏画面」专项负向约束（Anchor 生成器禁止项区有独立勾选框，勾选后自动并入）：

```text
整体画面必须干净、平滑、统一，强调大色块叙事与整体轮廓，
不要细碎噪点，不要高频纹理，不要脏污颗粒，不要密集小装饰，
边缘清晰利落，表面干净，画面呼吸感强，一目了然。
```

使用原则：
- **默认不勾选**：常规产出不应额外堆叠该约束，以免压制必要的细节纹理。
- **按需启用**：仅在出现画面脏污/噪点问题时勾选。
- 与 Quality Guard 不冲突——它负责结构稳定，防脏约束负责表面洁净，二者互补。

---

# 12. Layer 7 — Lyrics

歌词仍属于 Lip Sync Contract 的正式输入。

V2.1 只增加一个动态渲染分支：**普通歌词**与**带人工时间点的歌词**。

## 12.1 普通歌词

当 `lyrics_timestamps` 不存在、为空，或全部 `time == null` 时，保持 V2 已确认的 Prompt 不变：

```text
演唱 / 说话内容：

{lyrics}
```

对于存在音频和视频的任务，继续使用：

```text
歌词用于明确准确的文字、音节和发音顺序；
参考音频和视频共同确定对应的实际发音与口型时间。
```

即：没有 timestamp 时，不增加任何额外时间说明。

---

## 12.2 带人工时间点的歌词

当 `lyrics_timestamps` 中至少存在一个有效 `time` 时，进入 Timestamped Lyrics 分支。

这里再区分两种情况。

### 全部歌词都有时间

直接采用最简洁的 Seedance 任务语言：

```text
全程自然对口型唱歌，严格按以下歌词和时间对口型：
0.74s开始唱“长大后谁不是离家出走”；
5.10s开始唱“茫茫人海里游”；
9.70s开始唱“抬起头才发现”；
11.90s开始唱“流眼泪的星星”。

保持演唱节奏、停顿和嘴部动作与参考音频、视频一致。
唱完后自然收尾。
```

这类写法最接近实际 Seedance Prompt 的颗粒度：直接给出“时间 + 歌词”，不解释数据结构。

### 只有部分歌词有时间

完整歌词仍然只写一遍，再单独强化已经人工标注的时间点：

```text
演唱 / 说话内容：
冻结那时间
冻结初遇那一天
冻结那爱恋

严格按以下已标注时间对口型：
1.23s开始唱“冻结那时间”；
5.68s开始唱“冻结初遇那一天”。

其余歌词按原顺序结合参考音频和视频自然衔接。
保持整体演唱节奏、停顿和嘴部动作与参考音频、视频一致。
唱完后自然收尾。
```

这样不会把未打点的歌词写成工程化的 `null` 状态，也不会对每一行重复“自然衔接”。

> 注：渲染前所有时间点需先加上时长对齐的 offset（`pad_mode=front` 时），规则见 §2.4.1。

---

## 12.3 Prompt 与内部语义分离

接口内部可以存在：

```json
[
  { "text": "冻结那时间", "time": 1.234 },
  { "text": "冻结初遇那一天", "time": 5.678 },
  { "text": "冻结那爱恋", "time": null }
]
```

但最终 Prompt 不输出：

```text
time = null
人工 onset
没有结束时间
下一句不能作为上一句结束
```

这些属于 Builder / 业务层语义。

模型侧只保留自然任务语言，例如：

```text
1.23s开始唱“冻结那时间”；
5.68s开始唱“冻结初遇那一天”。
其余歌词按原顺序结合参考音频和视频自然衔接。
```

当前接口只有单点 `time`，因此 Builder 不主动伪造区间；但这个实现细节也不需要向 Seedance 解释。

---

## 12.4 接口与内部数据

前端已经支持：

```text
GET  /api/tasks/{id}/lyrics-timestamps
POST /api/tasks/{id}/lyrics-timestamps
```

POST body：

```json
{
  "lyrics_timestamps": [
    { "text": "冻结那时间", "time": 1.234 },
    { "text": "冻结初遇那一天", "time": 5.678 },
    { "text": "冻结那爱恋", "time": null }
  ]
}
```

字段语义和校验属于 Builder / 业务层：

* `text` 对应歌词框中的一行。
* `time` 为秒，浮点数；未打点为 `null`。
* 至少存在一个有效 `time` 才进入 timestamp Prompt 分支。
* 全部为 `null` 时退化为普通歌词模式。
* 非法或明显矛盾的数据应在业务层处理，不直接编译进 Prompt。

---

# 13. Custom Constraints

用户额外输入最后追加：

```text
额外要求：
{constraints}
```

默认不修改用户文本。

但基础系统约束与用户约束发生冲突时，内部应优先保证：

```text
人物身份
→ 任务核心
→ Reference 分工
→ 用户额外要求
```

例如 `motion` 模式下用户要求“换成视频中的人物”，实际上已经改变任务定义，应由上层业务决定是否允许，而不是 Prompt 内部隐式解决。

## 13.1 可编辑 Prompt（自定义覆盖）

V2.3 起，Web 界面「预览 Prompt」由只读 `<pre>` 改为可直接编辑的 `<textarea>`：

* **未编辑（自动模式，默认）**：系统按七层架构自动生成完整 prompt，「任务附加约束」（`constraints`）作为「追加小补」仍以「额外要求」追加在末尾（不动其他部分）。
* **手动编辑（自定义模式）**：用户在预览框直接改动内容即视为自定义，保存 / 生成时**整段使用用户文本**（整段重写），不再叠加歌词、时间戳、附加约束等自动拼接内容；参考素材（图 1 / 视频 1 / 音频 1）的角色说明也需用户自行写清。
* 界面有「恢复自动生成」按钮可放弃自定义、回到系统生成版本；编辑后模式徽标显示为「自定义」，且提示条会说明两种方式的区别与后果。
* 后端通过任务字段 `custom_prompt` 传递；`adapter_from_task` 优先使用 `custom_prompt`，否则走 `build_prompt`。校验阶段自定义时跳过 `build_prompt`（用户文本无法程序校验）。

因此，`constraints`（附加约束）只在自动模式下参与；一旦启用自定义 prompt，`constraints` 不再生效。

---

# 14. 推荐代码结构

总体 Prompt Builder 不需要重构，只需要让 Lyrics 输入支持可选 timestamp。

建议抽象：

```python
@dataclass
class LyricsTimestamp:
    text: str
    time: float | None


@dataclass
class PromptSpec:
    mode: str

    image_ref: str = "图片1"
    video_ref: str | None = None
    audio_ref: str | None = None
    lyrics: str | None = None
    lyrics_timestamps: list[LyricsTimestamp] | None = None

    camera_policy: str = "keep_image"

    preserve_identity: bool = True
    preserve_scene: bool = True

    constraints: str | None = None
```

Prompt Builder 仍保持原结构：

```python
def build_prompt(spec: PromptSpec) -> str:
    parts = [
        build_task(spec),
        build_reference_map(spec),
        build_performance(spec),
        build_preservation(spec),
        build_camera(spec),
        build_quality(spec),
    ]

    if spec.constraints:
        parts.append(build_custom(spec))

    return "\n\n".join(filter(None, parts))
```

只增加一个集中判断：

```python
def has_lyrics_timestamps(spec: PromptSpec) -> bool:
    return bool(
        spec.lyrics_timestamps
        and any(item.time is not None for item in spec.lyrics_timestamps)
    )
```

不要只判断 `lyrics_timestamps is not None`，因为数组可能存在但全部是 `null`。

---

# 15. Performance Builder

Performance Builder 本身继续沿用 V2：

```python
def build_performance(spec):
    if spec.mode == "lip_sync":
        return build_lip_sync_contract(spec)

    if spec.mode == "motion":
        return build_motion_contract(spec)

    if spec.mode == "dance_lip_sync":
        return "\n\n".join([
            build_motion_contract(spec),
            build_lip_sync_contract(spec),
            build_motion_lip_alignment(spec),
        ])
```

`build_lip_sync_contract(spec)` 不需要增加独立的 `Lyrics Timestamp Contract`。

只需要在原 Lip Sync Contract 中调用动态 Lyrics Builder：

```python
def build_lip_sync_contract(spec):
    return "\n\n".join(filter(None, [
        build_lip_sync_core(spec),
        build_lyrics_input(spec),
        build_lip_timing(spec),
        build_lip_micro_motion(spec),
    ]))
```

其中真正发生分支的是：

```python
def build_lyrics_input(spec):
    if has_lyrics_timestamps(spec):
        return build_timestamped_lyrics(spec)

    return build_plain_lyrics(spec)
```

核心变化：

**Lip Sync 仍然是原来的完整 Contract；timestamp 只改变 Lyrics 的渲染方式。**

---

# 16. Lip Sync 动态构建

Lip Sync 仍然首先根据参考素材是否存在动态构建：

## Lyrics + Audio + Video

最强约束：

```text
lyrics
   ↓
linguistic

audio ─┐
       ├── temporal
video ─┘

video
   ↓
visual lip
```

---

## Lyrics + Video

没有独立音频时：

```text
歌词负责文字和发音顺序；
视频1共同提供实际口型、发音节奏、嘴形变化和时间节点。
```

---

## Lyrics + Audio

没有可用视觉口型视频时：

```text
歌词负责准确字词与发音顺序；
参考音频负责实际发音、节奏、持续时间、起止和停顿。

根据歌词与参考音频生成自然、符合真实发音规律的嘴形变化。
```

---

## Lyrics Rendering 分支

在上述 Reference Availability 之外，再单独判断歌词是否存在有效 timestamp：

```text
没有 timestamp
→ build_plain_lyrics()

有 timestamp
→ build_timestamped_lyrics()
```

推荐实现：

```python
def build_plain_lyrics(spec):
    return f"演唱 / 说话内容：\n\n{spec.lyrics}"


def build_timestamped_lyrics(spec):
    items = [
        item for item in (spec.lyrics_timestamps or [])
        if item.text.strip()
    ]
    timed = [item for item in items if item.time is not None]

    # 全部歌词都有时间：直接输出 time + lyrics
    if items and len(timed) == len(items):
        lines = ["全程自然对口型唱歌，严格按以下歌词和时间对口型："]
        lines += [
            f'{item.time:.2f}s开始唱“{item.text.strip()}”；'
            for item in items
        ]
    else:
        # Partial timestamp：完整歌词写一次，只额外列出已有时间点
        lines = [
            "演唱 / 说话内容：",
            *(item.text.strip() for item in items),
            "",
            "严格按以下已标注时间对口型：",
            *(
                f'{item.time:.2f}s开始唱“{item.text.strip()}”；'
                for item in timed
            ),
            "其余歌词按原顺序结合参考音频和视频自然衔接。",
        ]

    lines += [
        "保持整体演唱节奏、停顿和嘴部动作与参考音频、视频一致。",
        "唱完后自然收尾。",
    ]

    return "\n".join(lines)
```

小数位建议统一到 2 位左右即可。Seedance 的 Prompt 不需要保留接口浮点数的全部精度。

这里不要输出 `null`、`onset`、`end_time`、`manual timestamp` 等工程字段解释。

---

# 17. 三种模式完整 Prompt 模板

## `lip_sync`

```text
让图片1中的人物在保持原人物、场景和构图的情况下，
按照视频1、参考音频和给定歌词完成自然准确的演唱口型。

@image1 锁定人物身份、脸部、发型、服装、体型、场景、构图和光线，全程保持一致。
@video1 仅提供视觉口型参考：嘴形、嘴部开合、唇形变化与对应口型时间；不替换人物外观。
@audio1 提供实际发音、音节、节奏、持续时间、发音起止和停顿。
歌词提供准确的文字、音节内容与发音顺序。
外观与身份以 @image1 为准；口型同时满足歌词内容、发音时间与对应时间点正确的视觉嘴形。

对口型必须同时结合歌词、参考音频和视频1。
生成口型需要同时满足正确歌词、正确发音时间以及对应时间点正确的嘴形。
不得只依据其中任意一种参考生成口型。

歌词：
{lyrics}

参考音频和视频1共同约束口型时间。
保持每个发音开始、持续、结束、停顿、开口和闭口自然同步。

除口型外，仅保留自然眨眼、轻微表情、呼吸和极小幅度头部微动。
身体主体保持稳定。

始终保持图片1中的人物身份、服装、场景、光线和视觉外观。

镜头固定，保持图片1原始视角和构图，
不主动推拉、摇移、旋转或缩放。

保持脸部和身体结构稳定，
避免身份漂移、肢体异常、背景形变、画面闪烁及明显AI痕迹。
不得生成字幕、文字、水印、logo或额外元素。
```

---

## `motion`

```text
让图片1中的人物完整模仿视频1中的身体动作，
保持图片1中的人物身份、服装、场景和整体视觉效果。

@image1 锁定人物身份、脸部、发型、服装、体型、场景、构图和光线。
@video1 仅提供身体动作参考：姿态变化、动作顺序、运动轨迹、动作幅度与节奏；不复制其画面元素。

完整复现视频1从开始到结束的动作编排，
保持动作顺序、节奏、速度变化、身体朝向、重心变化、
手臂轨迹、腿部动作、动作幅度以及关键姿态。

不得漏动作、交换动作顺序、增加动作、重复动作或自行重新编排。

动作自然适配图片1人物原有的身体比例和当前构图。
保持动作语义、节奏、方向和关键姿态一致，
不要为了机械复制参考人物的绝对空间位置而扭曲身体结构。

始终保持图片1中的同一人物以及原有服装、场景、光线和视觉风格。

整体保持图片1原始镜头和视角，
允许为了完整容纳动作产生必要的小幅构图适配，
不主动增加额外运镜。

保持动作连续自然，
避免身份漂移、关节扭曲、穿模、肢体拉伸、背景形变和画面闪烁。
不得生成文字、水印、logo或额外元素。
```

---

## `dance_lip_sync`

```text
让图片1中的人物完整模仿视频1中的身体动作，
同时结合视频1、参考音频和歌词完成准确演唱口型。

@image1 锁定人物身份、脸部、发型、服装、体型、场景、构图和光线。
@video1 提供身体动作参考，并作为视觉口型时间参考；不替换人物外观。
@audio1 提供实际发音、节奏、音节持续时间、起止和停顿。
歌词提供准确的文字、音节内容与发音顺序。
外观与身份以 @image1 为准；身体动作与口型在同一时间轴中互不干扰。

身体动作从开始到结束完整跟随视频1，
保持动作顺序、节奏、速度变化、运动轨迹、身体朝向和关键姿态。
不得漏动作、重复动作、增加动作或重新排列动作。

动作自然适配图片1人物原有的身体比例，
不要为了机械复制空间位置而拉伸或扭曲肢体。

口型必须同时结合歌词、参考音频和视频1：
歌词确定实际演唱内容和发音顺序；
参考音频确定实际发音、音节、节奏、起止和停顿；
视频1确定对应时间点的嘴形、嘴部开合、唇形转换和闭口时机。

生成口型必须同时满足正确歌词、
正确发音时间和对应时间点正确自然的视觉嘴形。

身体动作与口型保持在同一完整时间轴中：
不得因身体动作导致口型提前或延迟，
也不得为了口型同步而跳过、重复或重新排序身体动作。

始终保持图片1中的人物身份、服装、体型、场景、光线和视觉风格。

整体保持图片1原始镜头和构图，
允许为了容纳完整身体动作进行必要的小幅构图适配，
不主动增加额外运镜。

保持人物身份、脸部、身体和手部结构稳定，
避免关节扭曲、肢体穿模、身份漂移、背景形变和画面闪烁。
不得生成字幕、文字、水印、logo或额外元素。
```

---

## 有人工时间戳时的增量模板

`lip_sync` 和 `dance_lip_sync` 的基础模板都保持不变。

当存在有效 timestamp 时，**只替换原来的 Lyrics 输入块**，不重写 Reference Map、Preservation、Camera、Quality，也不新增独立 Timestamp Contract。

### 全部歌词都有 timestamp

原块：

```text
歌词：
{lyrics}
```

替换为：

```text
全程自然对口型唱歌，严格按以下歌词和时间对口型：
0.74s开始唱“长大后谁不是离家出走”；
5.10s开始唱“茫茫人海里游”；
9.70s开始唱“抬起头才发现”；
11.90s开始唱“流眼泪的星星”。

保持整体演唱节奏、停顿和嘴部动作与参考音频、视频一致。
唱完后自然收尾。
```

### Partial timestamp

替换为：

```text
演唱 / 说话内容：
冻结那时间
冻结初遇那一天
冻结那爱恋

严格按以下已标注时间对口型：
1.23s开始唱“冻结那时间”；
5.68s开始唱“冻结初遇那一天”。

其余歌词按原顺序结合参考音频和视频自然衔接。
保持整体演唱节奏、停顿和嘴部动作与参考音频、视频一致。
唱完后自然收尾。
```

这种做法保留了外部优秀 Prompt 示例中“直接给模型时间 + 歌词”的优势，同时不会把前端数据协议暴露给 Seedance。

---

# 18. Prompt 编译原则

最终 Prompt 遵循几个原则：

### 1. 先讲任务，再讲限制

避免一开始连续出现大量：

```text
严禁……
不得……
严禁……
```

模型首先应明确需要完成的主要任务。

### 2. 正向描述优先

例如优先：

```text
保持图片1人物身份稳定
```

而不是连续枚举：

```text
不得换人、不得脸变、不得发型变化……
```

仅对典型错误保留必要 negative constraint。

### 3. Reference 职责尽量只定义一次

避免同时出现：

```text
视频严格控制口型
音频严格控制口型
歌词严格控制口型
```

改为明确：

```text
三者共同约束口型，
但分别提供 linguistic / acoustic / temporal / visual 信息。
```

### 4. 时间关系必须明确

对口型和动作任务都应强调：

```text
from start to end
same timeline
same order
timing / onset / offset / pause
```

因为目标不仅是“长得像”，更重要的是整个时间序列正确。

### 5. Builder 语义与模型 Prompt 分离

设计文档可以明确：

```text
time == null
start-only timestamp
partial timestamp
validation / fallback
```

但这些概念不应原样写给 Seedance。

最终 Prompt 只保留可执行语言：

```text
1.23s开始唱“……”
其余歌词按参考音频和视频自然衔接
保持节奏、停顿和嘴部动作一致
```

Prompt 的目标是让模型完成任务，而不是让模型理解前端和接口的数据协议。

---

# 19. 推荐最终架构

```text
                    Task Mode
                        │
                        ↓
              Reference Resolver
           ┌────────────┼────────────┐
           ↓            ↓            ↓
        Identity      Motion       Lip Sync
          │             │             │
        image         video      ┌────┼────┐
                                ↓     ↓    ↓
                             lyrics audio video
                                │     │    │
                         optional time │    │
                                │     │    │
                                └── Fusion ┘
                                    │
                                    ↓
                            Performance Contract
                                    │
                          ┌─────────┴─────────┐
                          ↓                   ↓
                   Preservation          Camera
                          └─────────┬─────────┘
                                    ↓
                              Quality Guard
                                    ↓
                            Custom Constraints
```

## 核心思想

**人物、场景、身体动作使用 Reference Ownership。**

**口型使用 Lyrics + Audio + Video Multi-Reference Constraint Fusion；可选 Lyrics Timestamp 只增强歌词时间表达，不改变原有三源职责。**

Prompt 不再只是：

```text
GLOBAL
+ VIDEO
+ AUDIO
+ LYRICS
```

而是：

```text
Task
+ Reference Mapping
+ Performance Contract
+ Preservation
+ Camera
+ Quality
+ Custom
```

这样能够更准确表达当前业务真正需要模型完成的任务，同时也方便未来扩展更多参考图片、动作视频、独立音频以及不同镜头策略。

---

# 20. 参考来源与设计依据

本架构的措辞与分层并非主观设定，而是对齐 Seedance 官方教程与社区实测经验。
详细来源清单、原文摘录与适用结论见 **`docs/guides/Seedance_Prompt_Templates.md` §来源与依据**。
此处只列当前设计所引用的关键结论：

| 设计决策 | 依据（来源） | 结论 |
| --- | --- | --- |
| 各参考「单一职责」+ 显式声明 + 冲突以 Prompt 优先 | Seedance 2.5 R2V 指南 / heymarmot 指南 | 每份参考只管一类信息，避免职责冲突 |
| 用 `@image1 / @video1 / @audio1` 显式引用 | Seedance 2.5 R2V 指南（多模态参考喂法） | 模型依赖显式标记区分素材作用，而非"图片1负责…"的工程语言 |
| "负责"类措辞改为正向可执行约束 | Seedance 提示词指南（正向描述优先） | 模型只需理解"要做什么"，无需理解内部设计哲学 |
| 图管外观 / 视频管动作运镜 / 音频管节奏（按域分工） | Seedance 2.5 R2V 指南 · 社区 9 图 3 视频 3 音频实操 | 按域分配参考，避免多素材互相打架 |
| 纯音频模式不列出视频行、Layer 1 同步改写 | 上述"单一职责 + 显式声明"原则的直接推论 | 不向模型描述不存在的素材，避免误导 |
| 口型三源融合（Lyrics+Audio+Video） | 腾讯云音频参考 / 社区 R2V 口型实践 | 任一单源都不完整，须多源共同约束 |

> 改进任何 Prompt 措辞前，应先回到上述来源核对，确保"有理有据"，不凭空改写。
