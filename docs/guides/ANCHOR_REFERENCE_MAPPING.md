# Anchor-based Reference Mapping 设计文档

## 概述

Anchor-based Reference Mapping 是多参考图合成的核心抽象层。它与传统 "Image Role" 方案的本质区别是：

**之前**：每张参考图被分配一个固定角色（图1=身份、图2=场景、图3=服装）

**现在**：每个可控制的视觉属性（Anchor）独立映射到来源图，一张图可同时提供多个视觉属性。

```
identity        ← image_1
hairstyle       ← image_2
scene           ← image_2
lighting        ← image_2
clothing        ← image_2
skin_texture    ← image_2
dog (object)    ← image_3
chair (object)  ← image_3
```

## 设计目标

1. **解耦图片角色**：不预定义"图2=场景图、图3=服装图"
2. **多锚点同源**：一张图可同时贡献 scene、clothing、lighting 等多个属性
3. **操作语义化**：每个锚点携带操作类型（preserve / transfer / match / remove / replace）
4. **灵活扩展**：新增视觉属性只需扩展 Taxonomy，不改变架构

---

## 流水线

```
User free-form Chinese text
        │
        ▼
┌─────────────────────────────┐
│  1. Keyword Pattern Parser  │  ← 正则规则 + auto-inference
│      (parse_natural_language)│
└─────────────┬───────────────┘
              ▼
        ┌──────────┐
        │ 2. GPT   │  ← 如果 keyword 解析不够充分，回退/增强
        │   Parsing│
        └────┬─────┘
             ▼
    ┌────────────────┐
    │ 3. Anchor List │  每个 Anchor: (type, category, source, operation, priority)
    └───────┬────────┘
            ▼
    ┌────────────────────────┐
    │ 4. Conflict Resolver   │  identity 锁定 image_1 / priority 合并规则
    │    + Default Injector   │  注入 GLOBAL_DEFAULTS
    └───────┬────────────────┘
            ▼
    ┌───────────────────────────────┐
    │ 5. Structured Schema          │  按 category 分组的 JSON
    │    (_build_structured_schema)  │
    └───────┬───────────────────────┘
            ▼
    ┌───────────────────────────────┐
    │ 6. Canonical Prompt Renderer  │  渲染为英文 gpt-image-2 prompt
    │    (_render_canonical_prompt)  │
    └───────┬───────────────────────┘
            ▼
    ┌───────────────────────────────┐
    │ 7. Form Pre-fill Configs      │  前端 aspect checkboxes +
    │    (_build_aspects +           │  reference bindings 预填
    │     _build_reference_configs)  │
    └───────────────────────────────┘
```

---

## Anchor Taxonomy（7 大类）

### 1. Subject（人物主体）— 跟"人是谁"有关

| Anchor Type       | Priority | 描述                                              |
| ----------------- | -------- | ------------------------------------------------- |
| `identity`        | critical | 保持人物五官、脸型、骨相、年龄感与肤色完全一致    |
| `facial_features` | medium   | 面部特征                                          |
| `face_shape`      | low      | 脸型轮廓                                          |
| `hairstyle`       | high     | 发型、发际线、长度和造型与参考图一致              |
| `hair_texture`    | medium   | 头发质感、光泽和发丝细节                          |
| `skin_texture`    | medium   | 皮肤质感、毛孔、肤色均匀度                        |
| `body_shape`      | low      | 体型轮廓                                          |
| `body_proportion` | medium   | 头身比、肩宽、骨架比例                            |

### 2. Appearance（穿着配饰）— 跟"穿什么戴什么"有关

| Anchor Type   | Priority | 描述                     |
| ------------- | -------- | ------------------------ |
| `clothing`    | high     | 服装款式、版型、颜色     |
| `shoes`       | low      | 鞋子款式                 |
| `glasses`     | medium   | 眼镜框型、镜片           |
| `hat`         | low      | 帽子                     |
| `earrings`    | low      | 耳饰                     |
| `necklace`    | low      | 项链                     |
| `bag`         | low      | 包                       |
| `accessories` | low      | 配饰综合                 |

### 3. Environment（场景环境）— 跟背景、地点有关

| Anchor Type     | Priority | 描述                               |
| --------------- | -------- | ---------------------------------- |
| `scene`         | high     | 场景背景、空间结构                 |
| `background`    | medium   | 背景环境                           |
| `foreground`    | low      | 前景元素                           |
| `furniture`     | low      | 家具                               |
| `architecture`  | low      | 建筑结构                           |
| `weather`       | low      | 天气条件                           |
| `time_of_day`   | low      | 时间段                             |
| `scene_objects` | medium   | 场景中的物体（如桌子、栏杆）       |

### 4. Objects（独立物体）— 图2/图3可能提供某个固定物体

| Anchor Type | Priority | 描述                         |
| ----------- | -------- | ---------------------------- |
| `object`    | high     | 独立物体（狗、椅子、吉他等） |

每个 object anchor 携带额外字段：

```python
ObjectAnchor(
    name="dog",           # 物体名称
    source="image_3",     # 来源图
    operation="transfer", # 操作
    preserve=["appearance", "color", "texture"],  # 保留属性
    position="beside_subject",  # 位置
    identity_source="",   # 可选：物体身份来源
    pose_source="",       # 可选：物体姿态来源
    position_source="",   # 可选：物体位置来源
    lighting_source="",   # 可选：物体光照来源
)
```

### 5. Composition（构图姿态）— 照片怎么拍

| Anchor Type        | Priority | 描述                     |
| ------------------ | -------- | ------------------------ |
| `pose`             | high     | 人物姿态                 |
| `framing`          | medium   | 构图（半身/全身/特写）   |
| `camera_angle`     | low      | 拍摄角度                 |
| `facing_direction` | low      | 朝向                     |
| `subject_position` | low      | 人物在画面中的位置       |

### 6. Photography（摄影风格）— 最终成像质量

| Anchor Type       | Priority | 描述                      |
| ----------------- | -------- | ------------------------- |
| `lighting`        | high     | 光线方向、强度、氛围      |
| `exposure`        | low      | 曝光                      |
| `camera_style`    | medium   | 拍摄风格/设备             |
| `depth_of_field`  | low      | 景深                      |
| `texture_realism` | medium   | 真实感/纹理还原度         |

### 7. Edit（编辑操作）— 显式修改

| Anchor Type | Priority | 描述             |
| ----------- | -------- | ---------------- |
| `remove`    | high     | 移除指定元素     |
| `replace`   | high     | 替换指定元素     |
| `preserve`  | high     | 保留指定元素     |
| `add`       | medium   | 添加指定元素     |

---

## 操作类型语义

| Operation  | 语义                                       | 典型用法                      |
| ---------- | ------------------------------------------ | ----------------------------- |
| `preserve` | 保持原样不变                               | identity, scene, background   |
| `transfer` | 将目标属性从源图迁移到最终输出             | clothing, hairstyle, objects  |
| `match`    | 匹配源图的视觉品质（质感、氛围）而非搬运具体元素 | lighting, skin_texture, hair_texture |
| `remove`   | 从最终输出中删除                           | 水印、路人、背景元素          |
| `replace`  | 用指定源替换目标                           | 用图3的小狗替换图2的小狗      |
| `add`      | 添加新元素                                 | 添加来自图4的花               |
| `modify`   | 修改现有元素                               | 改变光线强度                  |

---

## 数据模型

### Anchor（核心原子）

```python
@dataclass
class Anchor:
    type: str                 # "identity", "clothing", "dog" 等
    category: str             # subject | appearance | environment | objects | composition | photography | edit
    source: str = ""          # 来源图，如 "图1"、"图2"，空串 = 无指定来源
    operation: str = "preserve"
    priority: str = "high"    # critical | high | medium | low
    description: str = ""
    target: str = ""          # 替换/修改的目标
    object_name: str = ""     # 为 object 类型 anchor 携带物体名
    preserve_attrs: list[str] = field(default_factory=list)
    position: str = ""        # "beside_subject", "original", "foreground" 等
```

### OptimizedResult（完整输出）

```python
@dataclass
class OptimizedResult:
    raw_text: str
    anchors: list[Anchor]         # 所有视觉属性锚点
    objects: list[ObjectAnchor]   # 独立物体引用
    composition: CompositionConfig
    aspects: list[AspectConfig]   # 前端预填参考点
    references: list[ReferenceConfig]  # 前端预填参考图绑定
    canonical_prompt: str         # 最终渲染的英文 prompt
    structured_schema: dict       # 完整中间表示
    source: str = "keyword"       # "gpt" | "keyword"
```

---

## 关键词解析规则

### 规则结构

每条规则是 `(正则, anchor_type, operation, 匹配模式)` 四元组：

| 匹配模式   | 含义                                       |
| ---------- | ------------------------------------------ |
| `"ref"`    | 从 group(1) 提取图片索引（1, 2, 3...）     |
| `"desc:N"` | 从 group(N) 提取描述文本（N=整数）或用静态文本 |
| `"none"`   | 仅标记 anchor 存在，不提取额外数据         |
| `"object"` | 从 group(2) 提取物体名称                   |
| `"auto"`   | 通用 "图X 参考 Y" 模式，自动映射关键词     |

### 跨分句匹配保护

为避免贪婪匹配跨多个需求语句，带 `图(\d+)` 的规则使用 `[^；。]*?` 替代 `.*?`，确保匹配不跨越中/英文分号分隔。

### Anchor 合并策略

1. **identity 始终锁定**：identity 的 source 一旦设定不会被覆盖，priority 强制为 critical
2. **有 source 优先**：如果已有 anchor 携带 source 信息，无 source 的新匹配不会覆盖
3. **Object 去重**：通过 `object:<name>` 键防止同一物体重复

---

## Canonical Prompt 渲染

渲染器将结构化 schema 转为英文 prompt，遵循以下结构：

```
Reference image mapping:
- Image A provides: identity
- Image B provides: scene, clothing, lighting

Main subject:
Strictly preserve the facial identity from Image A...

Body proportion: small head, broad shoulders.

Appearance:
- clothing: transfer from Image B (服装款式...)

Scene and environment:
Place the subject naturally into the environment from Image B.

Objects:
- dog: transfer from Image C, preserving appearance, color, texture

Pose and composition:
- Subject pose: 站直.
- Framing: 半身构图.

Lighting:
Match the lighting direction, intensity, and mood from Image B.

Realism and camera style:
The final image should look like a realistic iPhone night photo...

Negative constraints:
Remove: watermark, text, extra people.
```

---

## 全局默认值

```python
GLOBAL_DEFAULTS = {
    "body_proportion": "small head, broad shoulders",
    "camera_style": "realistic iPhone photo",
    "realism": "natural photorealistic human appearance",
    "skin_texture": "realistic skin texture",
    "hair_texture": "realistic hair texture",
    "identity_priority": "critical",
}
```

这些默认值在 parser 未匹配到对应锚点时自动注入。

---

## API 接口

### `POST /api/anchor-optimize`

请求：

```json
{
  "text": "保持图1人物五官和长相；参考图2的场景和服装；...",
  "references": []
}
```

响应包含 `anchors`, `objects`, `composition`, `aspects`, `references`, `canonical_prompt`, `structured_schema` 等字段。

### 核心函数

```python
from idolmv_pipeline.image_tasks.optimizer import optimize

result = optimize("保持图1人物...参考图2的场景和服装...")
# result["anchors"]     → list[Anchor dict]
# result["canonical_prompt"] → str
# result["structured_schema"] → dict
```

---

## 扩展指南

### 新增视觉属性

在 `ANCHOR_TAXONOMY` 中添加条目：

```python
"new_attribute": {
    "category": "appearance",  # 或 subject/environment/...
    "priority": "high",
    "description": "中文描述",
}
```

### 新增关键词规则

在 `_build_rules()` 的 `rules_raw` 中添加四元组：

```python
(r"参考图(\d+)[的]*新属性", "new_attribute", "match", "ref"),
```

### 扩展前端映射

在 `_build_aspects()` 的 `TYPE_TO_ASPECT_KEY` 中添加映射：

```python
"new_attribute": "form_aspect_key",
```

在 `modules/anchor.js` 的 `TYPE_TO_ASPECT_KEY` 中同步添加：

```javascript
new_attribute: 'form_aspect_key',
```

---

## 文件结构

```
idolmv_pipeline/image_tasks/optimizer.py   # 核心 optimizer 引擎
idolmv_pipeline/web/handlers.py            # API 端点 /api/anchor-optimize
idolmv_pipeline/web/static/modules/anchor.js  # 前端解析器交互逻辑
idolmv_pipeline/web/static/index.html      # Optimizer 面板 HTML
idolmv_pipeline/web/static/app.css         # 映射表样式
```

---

最后更新：2026-08-11
