"""Prompt Optimizer — natural language → Anchor-based Reference Mapping → canonical prompt.

Architecture
────────────
Instead of assigning a fixed "role" to each reference image (e.g. "Image 2 = scene"),
the optimizer maps every *visual attribute* (anchor) to a source image with an
operation. A single image can serve multiple anchors simultaneously.

Pipeline
────────
User text
   ↓  keyword patterns + auto-inference
Anchor extraction  →  list[Anchor]
   ↓  group by source image, resolve conflicts
Anchor graph
   ↓  inject global defaults
Structured schema
   ↓  render to English
Canonical prompt  →  gpt-image-2

Data model
──────────
Anchor = (type, category, source, operation, priority, target, description)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("optimizer")

# ═══════════════════════════════════════════════════════════════════════
# Anchor Taxonomy — 5 top-level categories
# ═══════════════════════════════════════════════════════════════════════

ANCHOR_TAXONOMY = {
    # ── SUBJECT — who the person is ──
    "identity":       {"category": "subject",    "priority": "critical", "description": "保持人物五官、脸型、骨相、年龄感与肤色完全一致"},
    "facial_features": {"category": "subject",    "priority": "medium",   "description": "面部特征"},
    "face_shape":      {"category": "subject",    "priority": "low",      "description": "脸型轮廓"},
    "hairstyle":       {"category": "subject",    "priority": "high",     "description": "发型、发际线、长度和造型与参考图一致"},
    "hair_texture":    {"category": "subject",    "priority": "medium",   "description": "头发质感、光泽和发丝细节"},
    "skin_texture":    {"category": "subject",    "priority": "medium",   "description": "皮肤质感、毛孔、肤色均匀度"},
    "body_shape":      {"category": "subject",    "priority": "low",      "description": "体型轮廓"},
    "body_proportion": {"category": "subject",    "priority": "medium",   "description": "头身比、肩宽、骨架比例"},

    # ── APPEARANCE — what the person wears ──
    "clothing":    {"category": "appearance", "priority": "high",   "description": "服装款式、版型、颜色与参考图一致"},
    "shoes":       {"category": "appearance", "priority": "low",    "description": "鞋子款式"},
    "glasses":     {"category": "appearance", "priority": "medium", "description": "眼镜框型、镜片"},
    "hat":         {"category": "appearance", "priority": "low",    "description": "帽子"},
    "earrings":    {"category": "appearance", "priority": "low",    "description": "耳饰"},
    "necklace":    {"category": "appearance", "priority": "low",    "description": "项链"},
    "bag":         {"category": "appearance", "priority": "low",    "description": "包"},
    "accessories": {"category": "appearance", "priority": "low",    "description": "配饰综合"},

    # ── ENVIRONMENT — the setting ──
    "scene":          {"category": "environment", "priority": "high",   "description": "场景背景、空间结构与参考图一致"},
    "background":     {"category": "environment", "priority": "medium", "description": "背景环境"},
    "foreground":     {"category": "environment", "priority": "low",    "description": "前景元素"},
    "furniture":      {"category": "environment", "priority": "low",    "description": "家具"},
    "architecture":   {"category": "environment", "priority": "low",    "description": "建筑结构"},
    "weather":        {"category": "environment", "priority": "low",    "description": "天气条件"},
    "time_of_day":    {"category": "environment", "priority": "low",    "description": "时间段"},
    "scene_objects":  {"category": "environment", "priority": "medium", "description": "场景中的物体（如桌子、栏杆）"},

    # ── OBJECTS — standalone items from references ──
    "object":         {"category": "objects",    "priority": "high",   "description": "独立物体（狗、椅子、吉他等）"},

    # ── COMPOSITION — how the photo is framed ──
    "pose":              {"category": "composition", "priority": "high",   "description": "人物姿态"},
    "framing":           {"category": "composition", "priority": "medium", "description": "构图（半身/全身/特写）"},
    "camera_angle":      {"category": "composition", "priority": "low",    "description": "拍摄角度"},
    "facing_direction":  {"category": "composition", "priority": "low",    "description": "朝向"},
    "subject_position":  {"category": "composition", "priority": "low",    "description": "人物在画面中的位置"},

    # ── PHOTOGRAPHY — image quality & style ──
    "lighting":         {"category": "photography", "priority": "high",   "description": "光线方向、强度、氛围"},
    "exposure":         {"category": "photography", "priority": "low",    "description": "曝光"},
    "camera_style":     {"category": "photography", "priority": "medium", "description": "拍摄风格/设备"},
    "depth_of_field":   {"category": "photography", "priority": "low",    "description": "景深"},
    "texture_realism":  {"category": "photography", "priority": "medium", "description": "真实感/纹理还原度"},

    # ── EDIT — explicit modifications ──
    "remove":  {"category": "edit", "priority": "high", "description": "移除指定元素"},
    "replace": {"category": "edit", "priority": "high", "description": "替换指定元素"},
    "preserve": {"category": "edit", "priority": "high", "description": "保留指定元素"},
    "add":      {"category": "edit", "priority": "medium", "description": "添加指定元素"},
}

# Operation types
# transfer  = move this thing over (clothing, hairstyle, object)
# preserve  = keep as-is (identity, scene, lighting)
# match     = match this visual quality (skin_texture, hair_texture, lighting)
# remove    = delete from output
# replace   = swap with another source
# add       = insert new element
# modify    = alter existing element
OPERATIONS = {"transfer", "preserve", "match", "remove", "replace", "add", "modify"}

# ═══════════════════════════════════════════════════════════════════════
# Global Defaults (user's habitual preferences)
# ═══════════════════════════════════════════════════════════════════════

GLOBAL_DEFAULTS = {
    "body_proportion": "small head, broad shoulders",
    "camera_style": "realistic iPhone photo",
    "realism": "natural photorealistic human appearance",
    "skin_texture": "realistic skin texture",
    "hair_texture": "realistic hair texture",
    "identity_priority": "critical",
}

# ═══════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class Anchor:
    """One visual attribute with its source, operation, and constraints."""
    type: str                      # e.g. "identity", "clothing", "dog"
    category: str                  # subject | appearance | environment | objects | composition | photography | edit
    source: str = ""               # "image_1", "image_2", etc.  "" = from defaults/text
    operation: str = "preserve"    # preserve | transfer | match | remove | replace | add | modify
    priority: str = "high"         # critical | high | medium | low
    description: str = ""
    target: str = ""               # optional: what to replace/modify (e.g. "dog_in_image_2")
    object_name: str = ""          # for object anchors: the object's name
    preserve_attrs: list[str] = field(default_factory=list)  # ["appearance", "color", "texture"]
    position: str = ""             # for objects: "beside_subject", "original", "foreground", etc.


@dataclass
class ObjectAnchor:
    """Detailed object reference."""
    name: str
    source: str = ""
    operation: str = "transfer"
    preserve: list[str] = field(default_factory=list)
    position: str = ""
    identity_source: str = ""
    pose_source: str = ""
    position_source: str = ""
    lighting_source: str = ""


@dataclass
class CompositionConfig:
    pose: str = ""
    facing: str = ""
    framing: str = ""
    camera_angle: str = ""
    subject_position: str = ""


@dataclass
class AspectConfig:
    """Form pre-fill for anchor aspect checkboxes."""
    key: str
    label: str
    enabled: bool
    priority: str
    description: str
    preset: str = ""


@dataclass
class ReferenceConfig:
    """Reference binding for form pre-fill."""
    id: str
    file: str
    bindings: list[dict]
    note: str
    remove_watermark: bool


@dataclass
class OptimizedResult:
    raw_text: str
    anchors: list[Anchor]
    objects: list[ObjectAnchor]
    composition: CompositionConfig
    aspects: list[AspectConfig]
    references: list[ReferenceConfig]
    canonical_prompt: str
    structured_schema: dict
    source: str = "keyword"


# ═══════════════════════════════════════════════════════════════════════
# Image label helpers
# ═══════════════════════════════════════════════════════════════════════

_IMG_LABELS = {1: "图1", 2: "图2", 3: "图3", 4: "图4", 5: "图5", 6: "图6"}
_IMG_KEY_MAP = {"图1": "image_1", "图2": "image_2", "图3": "image_3",
                "图4": "image_4", "图5": "image_5", "图6": "image_6"}


def _img_key(label: str | None) -> str:
    if not label:
        return ""
    return _IMG_KEY_MAP.get(label, label)


def _img_label(index: int) -> str:
    return _IMG_LABELS.get(index, f"图{index}")


# ═══════════════════════════════════════════════════════════════════════
# Keyword Pattern Parser
# ═══════════════════════════════════════════════════════════════════════

# Each rule: (regex_pattern, anchor_type, operation, extract_mode)
# extract_mode: "ref" = extract image index from group 1
#               "desc:N" = extract description from group N
#               "none" = just flag the anchor
#               "object" = extract object name from group 2

_RULES: list[tuple[re.Pattern, str, str, str]] = []


def _build_rules():
    global _RULES
    if _RULES:
        return

    rules_raw = [
        # ── identity (critical) ──
        (r"保持图(\d+)人物[的五官和长相]*", "identity", "preserve", "ref"),
        (r"用图(\d+)的[人人]物", "identity", "preserve", "ref"),
        (r"替换成图(\d+)人物", "identity", "replace", "ref"),
        (r"保持长相一致", "identity", "preserve", "none"),
        (r"五官[和]*长相.*参考图(\d+)", "identity", "preserve", "ref"),
        (r"图(\d+)[^；。]*参考[^；。]*五官", "identity", "preserve", "ref"),
        (r"参考图(\d+)[人人]物", "identity", "preserve", "ref"),
        (r"保持[人人]物身份", "identity", "preserve", "none"),
        (r"保持图(\d+)长相", "identity", "preserve", "ref"),

        # ── hairstyle ──
        (r"参考图(\d+)(?:的发型|的刘海|发型|刘海)", "hairstyle", "transfer", "ref"),
        (r"保持图(\d+)发型", "hairstyle", "transfer", "ref"),
        (r"发型[的]*参考图(\d+)", "hairstyle", "transfer", "ref"),
        (r"刘海.*?参考图(\d+)", "hairstyle", "transfer", "ref"),
        (r"保持[刘海发型]", "hairstyle", "transfer", "none"),
        (r"发型[参不].*?[变改]", "hairstyle", "transfer", "none"),
        (r"刘海", "hairstyle", "transfer", "none"),

        # ── hair_texture ──
        (r"头发[质毛][^；。]*?(?:参考|保持)图(\d+)", "hair_texture", "match", "ref"),
        (r"参考图(\d+)[^；。]*?头发[质毛]", "hair_texture", "match", "ref"),
        (r"保持图(\d+)[^；。]*?头发[质毛]", "hair_texture", "match", "ref"),
        (r"头发[质毛]", "hair_texture", "match", "none"),
        (r"发丝[质真]", "hair_texture", "match", "none"),
        (r"头发[光自][^；。]*?[点感]", "hair_texture", "match", "none"),

        # ── skin_texture ──
        (r"皮肤[质纹][^；。]*?(?:参考|保持)图(\d+)", "skin_texture", "match", "ref"),
        (r"参考图(\d+)[^；。]*?皮肤[质纹]", "skin_texture", "match", "ref"),
        (r"保持图(\d+)[^；。]*?皮肤[质纹]", "skin_texture", "match", "ref"),
        (r"皮肤[质纹]", "skin_texture", "match", "none"),
        (r"皮肤[真自]", "skin_texture", "match", "none"),

        # ── scene ──
        (r"[场背]景[^；。]*?(?:参考|保持)图(\d+)", "scene", "preserve", "ref"),
        (r"参考图(\d+)[^；。]*?[场背]景", "scene", "preserve", "ref"),
        (r"保持图(\d+)[^；。]*?[场背]景", "scene", "preserve", "ref"),
        (r"放到图(\d+)[^；。]*?[场背]景", "scene", "preserve", "ref"),
        (r"参考图(\d+)[的]*场景", "scene", "preserve", "ref"),
        (r"[场背]景参考图(\d+)", "scene", "preserve", "ref"),
        (r"参考图(\d+)场景", "scene", "preserve", "ref"),
        (r"保持图(\d+)[^；。]*?背景", "scene", "preserve", "ref"),
        (r"背景参考图(\d+)", "scene", "preserve", "ref"),

        # ── clothing ──
        (r"服装[^；。]*?(?:参考|保持)图(\d+)", "clothing", "transfer", "ref"),
        (r"参考图(\d+)[^；。]*?服装", "clothing", "transfer", "ref"),
        (r"保持图(\d+)[^；。]*?服装", "clothing", "transfer", "ref"),
        (r"穿图(\d+)[^；。]*?这[套]", "clothing", "transfer", "ref"),
        (r"[换衣][^；。]*?图(\d+)[^；。]*?[衣服装]", "clothing", "transfer", "ref"),
        (r"参考图(\d+)服装", "clothing", "transfer", "ref"),

        # ── lighting ──
        (r"[光光影][^；。]*?(?:参考|保持)图(\d+)", "lighting", "match", "ref"),
        (r"参考图(\d+)[^；。]*?[光光影]", "lighting", "match", "ref"),
        (r"保持图(\d+)[^；。]*?[光光影]", "lighting", "match", "ref"),
        (r"光影参考图(\d+)", "lighting", "match", "ref"),
        (r"光线参考图(\d+)", "lighting", "match", "ref"),
        (r"夜晚[真][^；。]*?[光]", "lighting", "match", "none"),

        # ── pose ──
        (r"站直", "pose", "preserve", "desc:站直"),
        (r"坐直", "pose", "preserve", "desc:坐直"),
        (r"正对镜头", "pose", "preserve", "desc:正面朝向镜头"),
        (r"[手姿][自一]", "pose", "preserve", "none"),

        # ── framing ──
        (r"上半身[可]*[见]", "framing", "preserve", "desc:半身构图，上半身清晰可见"),
        (r"半身", "framing", "preserve", "desc:半身构图"),
        (r"全身", "framing", "preserve", "desc:全身构图，人物完整入镜"),
        (r"正方形构图", "framing", "preserve", "desc:正方形构图"),
        (r"特写", "framing", "preserve", "desc:面部特写"),
        (r"中景", "framing", "preserve", "desc:中景构图"),

        # ── body_proportion ──
        (r"头小肩宽", "body_proportion", "preserve", "desc:small head, broad shoulders"),
        (r"身高.*?(\d+)", "body_proportion", "preserve", "desc:身高约{}cm"),
        (r"[腿腿].*?[长]", "body_proportion", "preserve", "desc:腿长比例优化"),
        (r"骨架.*?大", "body_proportion", "preserve", "desc:骨架宽大"),

        # ── camera_style ──
        (r"真实.*?iPhone.*?拍", "camera_style", "preserve", "desc:realistic iPhone photo"),
        (r"iPhone.*?真实.*?夜景", "camera_style", "preserve", "desc:realistic iPhone night photo"),
        (r"iPhone.*?夜", "camera_style", "preserve", "desc:realistic iPhone night photo"),
        (r"手机拍[摄]", "camera_style", "preserve", "desc:phone camera photo"),
        (r"真实.*?拍[摄照]", "camera_style", "preserve", "none"),
        (r"手机.*?拍[摄照]", "camera_style", "preserve", "none"),

        # ── glasses ──
        (r"参考图(\d+)[^；。]*?眼镜", "glasses", "transfer", "ref"),
        (r"保持图(\d+)[^；。]*?眼镜", "glasses", "transfer", "ref"),
        (r"眼镜[^；。]*?图(\d+)", "glasses", "transfer", "ref"),

        # ── accessories ──
        (r"参考图(\d+)[^；。]*?[配饰]", "accessories", "transfer", "ref"),
        (r"保持图(\d+)[^；。]*?[配饰]", "accessories", "transfer", "ref"),

        # ── objects (key: object anchor with name) ──
        (r"图(\d+)[的]*(狗|小狗|猫|宠物|椅子|桌子|手机|吉他|花|包|车|栏杆|杯子|书|伞|手表|耳机|手链|戒指)也?保留", "object", "transfer", "object"),
        (r"保留图(\d+)[的]*(狗|小狗|猫|宠物|椅子|桌子|手机|吉他|花|包|车|栏杆|杯子|书|伞|手表|耳机|手链|戒指)", "object", "transfer", "object"),
        (r"(狗|小狗|猫|宠物|椅子|桌子|手机|吉他|花|包|车|栏杆|杯子|书|伞|手表|耳机|手链|戒指).*图(\d+)", "object", "transfer", "object"),

        # ── edit: remove ──
        (r"去[掉除].*?[水印]", "remove", "remove", "desc:水印"),
        (r"去[掉除].*?文[字]", "remove", "remove", "desc:文字"),
        (r"去[掉除].*?后[面].*?[人]", "remove", "remove", "desc:背景人物"),
        (r"去[掉除].*?[耳机]", "remove", "remove", "desc:耳机"),
        (r"去[掉除].*?[书包]", "remove", "remove", "desc:书包"),
        (r"不要[水印]", "remove", "remove", "desc:水印"),
        (r"不要[文].*?[字]", "remove", "remove", "desc:文字"),

        # ── edit: preserve (scene_objects) ──
        (r"保留[前].*?(桌子|椅子|栏杆|电梯|楼梯|柜子|沙发|床|门|窗|柱子|台阶|地板|天花板|墙)", "scene_objects", "preserve", "desc:1"),
        (r"保持[前].*?(桌子|椅子|栏杆|电梯|楼梯|柜子|沙发|床|门|窗|柱子|台阶|地板|天花板|墙)", "scene_objects", "preserve", "desc:1"),
    ]

    for pattern, anchor_type, operation, mode in rules_raw:
        _RULES.append((re.compile(pattern), anchor_type, operation, mode))

    # Generic "图X 参考 Y" pattern
    _RULES.append((re.compile(r"图(\d+)\s*参考\s*(\S+)"), "auto", "preserve", "auto"))


_build_rules()

# Auto-mapping for generic "图X 参考 Y" patterns
_AUTO_MAP: dict[str, str] = {
    "五官": "identity", "长相": "identity", "脸": "identity", "脸型": "identity",
    "人物": "identity", "身份": "identity",
    "发型": "hairstyle", "刘海": "hairstyle",
    "头发质感": "hair_texture", "发丝": "hair_texture", "头发": "hair_texture",
    "发质": "hair_texture",
    "皮肤": "skin_texture", "皮肤纹理": "skin_texture", "皮肤质感": "skin_texture",
    "场景": "scene", "背景": "scene", "环境": "scene",
    "服装": "clothing", "衣服": "clothing", "穿搭": "clothing", "穿着": "clothing",
    "光线": "lighting", "光影": "lighting", "灯光": "lighting",
    "姿势": "pose", "姿态": "pose", "站姿": "pose",
    "构图": "framing",
    "质感": "camera_style", "风格": "camera_style",
    "眼镜": "glasses",
}


def _extract_image_index(pattern: re.Pattern, text: str, mode: str) -> str:
    """Extract which reference image (1, 2, 3...) is referenced."""
    m = pattern.search(text)
    if not m:
        return ""
    try:
        idx = int(m.group(1))
        return _IMG_LABELS.get(idx, f"图{idx}")
    except (ValueError, IndexError):
        return ""


def _extract_description(pattern: re.Pattern, text: str, mode: str) -> str:
    """Extract description content from matched pattern."""
    m = pattern.search(text)
    if not m:
        return ""
    if mode.startswith("desc:"):
        # mode is "desc:1" (group index), "desc:static_text" (literal), or
        # "desc:模板{}" (literal with {} placeholder filled by group 1)
        rest = mode[5:]  # everything after "desc:"
        try:
            group_idx = int(rest)
            return m.group(group_idx) or ""
        except (ValueError, IndexError):
            # 含 {} 占位符 → 用 group 1 填充（如 "身高约{}cm" + "175" → "身高约175cm"）
            if "{}" in rest and m.lastindex and m.lastindex >= 1:
                return rest.replace("{}", m.group(1) or "")
            # 否则当作字面量描述文本
            return rest
    return ""


def _infer_operation(anchor_type: str, rule_op: str) -> str:
    """Infer the appropriate operation based on anchor type.

    - identity → preserve (don't change the person)
    - clothing, hairstyle, objects → transfer (move from source)
    - skin_texture, hair_texture, lighting → match (match visual quality)
    - scene → preserve (keep the environment)
    """
    if rule_op and rule_op != "preserve":
        return rule_op  # explicit operation from rule

    if anchor_type in ("identity", "scene", "background", "body_proportion", "camera_style"):
        return "preserve"
    if anchor_type in ("clothing", "hairstyle", "glasses", "accessories",
                       "hat", "shoes", "bag", "earrings", "necklace", "object"):
        return "transfer"
    if anchor_type in ("skin_texture", "hair_texture", "lighting", "texture_realism"):
        return "match"
    return "preserve"


def parse_natural_language(text: str, reference_count: int = 3) -> OptimizedResult:
    """Parse Chinese free-form text into anchor-based structured result.

    Returns OptimizedResult with:
    - anchors: list[Anchor] — each visual attribute mapped to source+operation
    - objects: list[ObjectAnchor] — standalone objects from references
    - composition: CompositionConfig — pose/framing/etc.
    - structured_schema: dict — full intermediate representation
    - canonical_prompt: str — rendered English prompt
    """
    anchors: dict[str, Anchor] = {}  # keyed by anchor type (or "object:name" for objects)
    objects: list[ObjectAnchor] = []
    composition = CompositionConfig()
    matched_spans: set[tuple[int, int]] = set()
    general_desc: list[str] = []

    for pattern, anchor_type, operation, mode in _RULES:
        m = pattern.search(text)
        if not m:
            continue
        span = m.span()
        if span in matched_spans:
            continue
        matched_spans.add(span)

        if mode == "auto":
            # "图X 参考 Y" → map keyword to anchor type
            try:
                idx = int(m.group(1))
                keyword = m.group(2).strip()
                mapped = _AUTO_MAP.get(keyword)
                if mapped and mapped in ANCHOR_TAXONOMY:
                    img_label = _img_label(idx)
                    taxonomy = ANCHOR_TAXONOMY[mapped]
                    op = _infer_operation(mapped, operation)
                    anchors[mapped] = Anchor(
                        type=mapped, category=taxonomy["category"],
                        source=img_label, operation=op,
                        priority=taxonomy["priority"],
                        description=taxonomy["description"],
                    )
            except (ValueError, IndexError):
                pass
            continue

        if mode == "object":
            # Extract object name + image source
            try:
                img_idx = int(m.group(1))
                obj_name = m.group(2) if m.lastindex >= 2 else ""
            except (ValueError, IndexError):
                img_idx = 0
                obj_name = ""
            if obj_name and img_idx:
                img_label = _img_label(img_idx)
                obj_key = f"object:{obj_name}"
                anchors[obj_key] = Anchor(
                    type="object", category="objects",
                    source=img_label, operation="transfer",
                    priority="high", object_name=obj_name,
                    description=f"保留{obj_name}的外观、颜色和纹理",
                    preserve_attrs=["appearance", "color", "texture"],
                    position="beside_subject",
                )
                objects.append(ObjectAnchor(
                    name=obj_name, source=img_label,
                    operation="transfer",
                    preserve=["appearance", "color", "texture"],
                    position="beside_subject",
                ))
            continue

        # Standard anchor extraction
        img_label = ""
        if mode == "ref":
            img_label = _extract_image_index(pattern, text, mode)

        if anchor_type == "remove":
            desc = _extract_description(pattern, text, mode) or "指定元素"
            anchors[f"remove:{desc}"] = Anchor(
                type="remove", category="edit",
                source="", operation="remove",
                priority="high", description=desc,
            )
            continue

        if anchor_type == "scene_objects":
            desc = _extract_description(pattern, text, mode)
            key = f"scene_objects:{desc}" if desc else "scene_objects"
            anchors[key] = Anchor(
                type="scene_objects", category="environment",
                source=img_label, operation="preserve",
                priority="medium",
                description=f"保留{desc}" if desc else "保留场景中的物体",
                object_name=desc if desc else "",
            )
            continue

        if anchor_type not in ANCHOR_TAXONOMY:
            continue

        taxonomy = ANCHOR_TAXONOMY[anchor_type]
        op = _infer_operation(anchor_type, operation)

        if mode.startswith("desc:"):
            desc = _extract_description(pattern, text, mode)
            if anchor_type == "pose":
                composition.pose = desc
            elif anchor_type == "framing":
                composition.framing = desc

        # Merge: if anchor already exists, prefer the one with a source image
        # Exception: identity — never overwrite once set
        existing = anchors.get(anchor_type)
        if anchor_type == "identity" and existing and existing.source:
            continue
        if existing and existing.source and not img_label:
            continue  # keep existing source binding

        # Use parsed description for desc-mode anchors; fall back to taxonomy default
        parsed_desc = ""
        if mode.startswith("desc:"):
            parsed_desc = _extract_description(pattern, text, mode)
        final_desc = parsed_desc or taxonomy["description"]

        anchors[anchor_type] = Anchor(
            type=anchor_type, category=taxonomy["category"],
            source=img_label, operation=op,
            priority=taxonomy["priority"],
            description=final_desc,
        )

    # Collect unmatched text segments as general description
    sorted_spans = sorted(matched_spans)
    last_end = 0
    for start, end in sorted_spans:
        segment = text[last_end:start].strip(" ，。；、\n\r\t")
        if segment:
            general_desc.append(segment)
        last_end = end
    remaining = text[last_end:].strip(" ，。；、\n\r\t")
    if remaining:
        general_desc.append(remaining)

    # Post-processing: auto-detect iPhone/camera mentions
    for seg in general_desc[:]:
        if re.search(r"iPhone.*?真实|真实.*?iPhone|iPhone.*?夜|真实.*?拍[摄照]", seg):
            anchors.setdefault("camera_style", Anchor(
                type="camera_style", category="photography",
                source="", operation="preserve",
                priority="medium",
                description="realistic iPhone photo",
            ))
            general_desc.remove(seg)
        elif re.search(r"[夜景][晚]", seg):
            anchors.setdefault("lighting", Anchor(
                type="lighting", category="photography",
                source="", operation="match",
                priority="high",
                description="夜晚灯光氛围",
            ))
            tmp = re.sub(r"[夜景][晚]", "", seg).strip()
            if tmp:
                general_desc[general_desc.index(seg)] = tmp
            else:
                general_desc.remove(seg)

    # Ensure identity always present with critical priority
    if "identity" not in anchors:
        anchors["identity"] = Anchor(
            type="identity", category="subject",
            source="图1", operation="preserve",
            priority="critical",
            description=ANCHOR_TAXONOMY["identity"]["description"],
        )
    else:
        # Always lock identity to critical and ensure source is preserved
        anchors["identity"].priority = "critical"
        if not anchors["identity"].source:
            anchors["identity"].source = "图1"

    # Build structured schema
    schema = _build_structured_schema(anchors, objects, composition, general_desc)

    # Render canonical prompt
    canonical_prompt = _render_canonical_prompt(schema, reference_count)

    # Build aspect configs for form pre-fill
    aspects = _build_aspects(anchors, composition)

    # Build reference configs
    references = _build_reference_configs(anchors, objects, reference_count)

    return OptimizedResult(
        raw_text=text,
        anchors=list(anchors.values()),
        objects=objects,
        composition=composition,
        aspects=aspects,
        references=references,
        canonical_prompt=canonical_prompt,
        structured_schema=schema,
        source="keyword",
    )


def _build_structured_schema(
    anchors: dict[str, Anchor],
    objects: list[ObjectAnchor],
    composition: CompositionConfig,
    general_desc: list[str],
) -> dict:
    """Build the full structured JSON schema from anchors."""

    # Group anchors by category
    subject_anchors = {}
    appearance_anchors = {}
    environment_anchors = {}
    photography_anchors = {}
    object_anchors = {}
    composition_anchors = {}
    edit_anchors = {}

    for a in anchors.values():
        a_dict = {
            "source": _img_key(a.source),
            "operation": a.operation,
            "priority": a.priority,
            "description": a.description,
        }
        if a.object_name:
            a_dict["object_name"] = a.object_name
        if a.preserve_attrs:
            a_dict["preserve_attrs"] = a.preserve_attrs
        if a.position:
            a_dict["position"] = a.position

        cat = a.category
        if cat == "subject":
            subject_anchors[a.type] = a_dict
        elif cat == "appearance":
            appearance_anchors[a.type] = a_dict
        elif cat == "environment":
            environment_anchors[a.type] = a_dict
        elif cat == "photography":
            photography_anchors[a.type] = a_dict
        elif cat == "objects":
            object_anchors[a.type if a.type != "object" else a.object_name] = a_dict
        elif cat == "composition":
            composition_anchors[a.type] = a_dict
        elif cat == "edit":
            edit_anchors[a.type] = a_dict

    # Build object list for schema
    objects_schema = []
    for obj in objects:
        objects_schema.append({
            "name": obj.name,
            "source": _img_key(obj.source),
            "operation": obj.operation,
            "preserve": obj.preserve,
            "position": obj.position,
        })

    # Build composition
    comp_schema = {
        "pose": composition.pose or "",
        "facing": composition.facing or "",
        "framing": composition.framing or "",
        "camera_angle": composition.camera_angle or "",
        "subject_position": composition.subject_position or "",
    }
    # Filter empty values
    comp_schema = {k: v for k, v in comp_schema.items() if v}

    # Remove items
    remove_items = []
    for key, a in anchors.items():
        if key.startswith("remove:") and a.operation == "remove":
            remove_items.append(a.description)

    return {
        "task_type": "anchor_based_composite",
        "subject": subject_anchors,
        "appearance": appearance_anchors,
        "environment": environment_anchors,
        "objects": objects_schema,
        "composition": comp_schema,
        "photography": photography_anchors,
        "edit": {
            "remove": remove_items,
            "anchors": {k: {"operation": v.operation, "description": v.description} for k, v in anchors.items() if v.category == "edit"},
        },
        "global_defaults": GLOBAL_DEFAULTS,
        "extra_constraints": general_desc,
    }


def _render_canonical_prompt(schema: dict, reference_count: int) -> str:
    """Render structured schema into English canonical prompt for gpt-image-2."""

    lines = ["Create a realistic edited composite image using the provided reference images."]
    lines.append("")

    # Helper to format source references
    def _ref_label(img_key: str) -> str:
        mapping = {"image_1": "Image A", "image_2": "Image B", "image_3": "Image C",
                   "image_4": "Image D", "image_5": "Image E", "image_6": "Image F"}
        return mapping.get(img_key, img_key.replace("image_", "Image ").upper())

    def _src_ref(a_dict: dict) -> str:
        """Return ' from Image B' or ''."""
        src = a_dict.get("source", "")
        return f" from {_ref_label(src)}" if src else ""

    # ── Reference mapping summary ──
    lines.append("Reference image mapping:")
    source_groups: dict[str, list[str]] = {}

    def _collect_sources(anchor_dict: dict):
        for name, a in anchor_dict.items():
            src = a.get("source", "") if isinstance(a, dict) else ""
            if src:
                source_groups.setdefault(src, []).append(name)

    for section in ["subject", "appearance", "environment", "photography"]:
        _collect_sources(schema.get(section, {}))

    for obj in schema.get("objects", []):
        src = obj.get("source", "")
        if src:
            source_groups.setdefault(src, []).append(f"object:{obj.get('name', 'unknown')}")

    for src, attrs in sorted(source_groups.items()):
        label = _ref_label(src)
        attr_str = ", ".join(attrs)
        lines.append(f"- {label} provides: {attr_str}")

    # ── Subject section ──
    subject = schema.get("subject", {})
    identity = subject.get("identity", {})
    if identity and identity.get("operation") == "preserve":
        lines.append("")
        lines.append("Main subject:")
        src = identity.get("source", "")
        src_phrase = f" from {_ref_label(src)}" if src else ""
        lines.append(f"Strictly preserve the facial identity{src_phrase}, including face shape, eyes, nose, lips, skin tone, age appearance, and overall facial structure. Do NOT adopt facial features from any other reference image.")

    body_prop = subject.get("body_proportion", {})
    if body_prop:
        desc = body_prop.get("description", GLOBAL_DEFAULTS["body_proportion"])
        if desc:
            lines.append(f"Body proportion: {desc}.")

    # ── Appearance section ──
    appear = schema.get("appearance", {})
    appear_lines = []
    for anchor_type, a in appear.items():
        if not isinstance(a, dict):
            continue
        src_ref = _src_ref(a)
        op = a.get("operation", "transfer")
        desc = a.get("description", "")
        if op == "transfer":
            appear_lines.append(f"- {anchor_type}: transfer{src_ref} ({desc})")
        elif op == "match":
            appear_lines.append(f"- {anchor_type}: match quality{src_ref} ({desc})")
        elif op == "preserve":
            appear_lines.append(f"- {anchor_type}: preserve as in{src_ref} ({desc})")
    if appear_lines:
        lines.append("")
        lines.append("Appearance:")
        lines.extend(appear_lines)

    # ── Environment section ──
    env = schema.get("environment", {})
    scene = env.get("scene", {})
    if scene:
        src_ref = _src_ref(scene)
        lines.append("")
        lines.append("Scene and environment:")
        lines.append(f"Place the subject naturally into the environment{src_ref}. Preserve the background structure, spatial feeling, and overall setting.")

    scene_objs = {k: v for k, v in env.items() if k.startswith("scene_objects")}
    for key, sobj in scene_objs.items():
        if isinstance(sobj, dict) and sobj.get("description"):
            lines.append(f"Preserve the {sobj.get('object_name', sobj.get('description', ''))} from the scene.")

    # ── Objects section ──
    objs = schema.get("objects", [])
    if objs:
        lines.append("")
        lines.append("Objects:")
        for obj in objs:
            name = obj.get("name", "")
            src = _ref_label(obj.get("source", ""))
            op = obj.get("operation", "transfer")
            pos = obj.get("position", "")
            pos_phrase = f", positioned {pos}" if pos else ""
            preserve = obj.get("preserve", [])
            preserve_phrase = f", preserving {', '.join(preserve)}" if preserve else ""
            if op == "transfer":
                lines.append(f"- {name}: transfer from {src}{preserve_phrase}{pos_phrase}")
            elif op == "replace":
                lines.append(f"- {name}: replace with version from {src}{preserve_phrase}")
            elif op == "preserve":
                lines.append(f"- {name}: preserve from {src}{preserve_phrase}")
            elif op == "add":
                lines.append(f"- {name}: add from {src}{pos_phrase}")

    # ── Composition section ──
    comp = schema.get("composition", {})
    if comp:
        comp_parts = []
        if comp.get("pose"):
            comp_parts.append(f"Subject pose: {comp['pose']}.")
        if comp.get("framing"):
            comp_parts.append(f"Framing: {comp['framing']}.")
        if comp.get("facing"):
            comp_parts.append(f"Facing direction: {comp['facing']}.")
        if comp.get("camera_angle"):
            comp_parts.append(f"Camera angle: {comp['camera_angle']}.")
        if comp_parts:
            lines.append("")
            lines.append("Pose and composition:")
            lines.extend(f"- {p}" for p in comp_parts)

    # ── Photography section ──
    photo = schema.get("photography", {})
    lighting = photo.get("lighting", {})
    if lighting:
        src_ref = _src_ref(lighting)
        lines.append("")
        lines.append("Lighting:")
        src_phrase = src_ref if src_ref else ""
        lines.append(f"Match the lighting direction, intensity, and mood{src_phrase}. Keep the lighting realistic and natural.")

    camera = photo.get("camera_style", {})
    cam_desc = camera.get("description", GLOBAL_DEFAULTS["camera_style"]) if camera else GLOBAL_DEFAULTS["camera_style"]
    lines.append("")
    lines.append("Realism and camera style:")
    lines.append(f"The final image should look like a {cam_desc}, with natural human detail, realistic skin texture, realistic hair texture, and believable lighting.")

    # ── Edit section ──
    edit = schema.get("edit", {})
    removes = edit.get("remove", [])
    lines.append("")
    lines.append("Negative constraints:")
    negs = list(removes) if removes else ["watermark", "text", "extra people"]
    lines.append(f"Remove: {', '.join(negs)}.")
    lines.append("Do not add unrelated accessories, extra people, watermark, or visible text unless explicitly requested.")

    return "\n".join(lines)


def _build_aspects(anchors: dict[str, Anchor], composition: CompositionConfig) -> list[AspectConfig]:
    """Convert anchors to form-pre-fill aspect configs."""
    aspects = []

    # Map anchor types to existing aspect keys in the form
    TYPE_TO_ASPECT_KEY = {
        "identity": "identity_face",
        "hairstyle": "hair_style",
        "hair_texture": "hair_texture",
        "skin_texture": "skin_texture",
        "clothing": "wardrobe",
        "scene": "scene",
        "lighting": "lighting",
        "pose": "pose_expression",
        "framing": "composition_camera",
        "body_proportion": "composition_camera",
        "camera_style": "visual_style",
        "glasses": "wardrobe",
        "accessories": "wardrobe",
    }

    seen_keys = set()
    for anchor_type, anchor in anchors.items():
        # Skip edit anchors and object anchors
        if anchor.category in ("edit",):
            continue
        if anchor.type == "object":
            continue
        if anchor_type.startswith("scene_objects:"):
            continue

        aspect_key = TYPE_TO_ASPECT_KEY.get(anchor_type)
        if not aspect_key or aspect_key in seen_keys:
            continue
        seen_keys.add(aspect_key)

        # Merge descriptions if multiple anchors map to same aspect key
        existing = next((a for a in aspects if a.key == aspect_key), None)
        if existing:
            if anchor.description and anchor.description not in existing.description:
                existing.description = f"{existing.description}；{anchor.description}"
            continue

        aspects.append(AspectConfig(
            key=aspect_key,
            label=anchor_type,
            enabled=True,
            priority=anchor.priority if anchor.priority != "critical" else "locked",
            description=anchor.description,
        ))

    return aspects


def _build_reference_configs(
    anchors: dict[str, Anchor],
    objects: list[ObjectAnchor],
    reference_count: int,
) -> list[ReferenceConfig]:
    """Build reference binding configs for form pre-fill.

    Each reference image gets bindings for ALL anchors it sources,
    including multiple anchors per image.
    """
    # Group anchors by source image
    source_map: dict[str, list[dict]] = {}
    for a in anchors.values():
        if not a.source:
            continue
        src_key = a.source  # e.g. "图1", "图2"
        if src_key not in source_map:
            source_map[src_key] = []
        source_map[src_key].append({
            "aspect": a.type,
            "content": a.description,
            "constraint": f"operation={a.operation}, priority={a.priority}",
        })

    for obj in objects:
        if not obj.source:
            continue
        src_key = obj.source
        if src_key not in source_map:
            source_map[src_key] = []
        source_map[src_key].append({
            "aspect": f"object:{obj.name}",
            "content": f"保留{obj.name}的外观、颜色和纹理",
            "constraint": f"operation=transfer, position={obj.position}",
        })

    configs = []
    for i in range(1, reference_count + 1):
        label = _img_label(i)
        bindings = source_map.get(label, [])
        if not bindings:
            continue
        configs.append(ReferenceConfig(
            id=f"ref-{i}",
            file=label,
            bindings=bindings,
            note="",
            remove_watermark=any(
                k.startswith("remove:") and "水印" in a.description
                for k, a in anchors.items()
            ),
        ))

    return configs


# ═══════════════════════════════════════════════════════════════════════
# GPT-based Optimizer (optional)
# ═══════════════════════════════════════════════════════════════════════

OPTIMIZER_SYSTEM_PROMPT = """You are a prompt optimizer for multi-reference image editing requests.

Your job is to convert the user's natural-language request into:
1. a structured JSON representation using anchor-based reference mapping
2. a final canonical image prompt that can be sent to an image generation model

Key concepts:
- Each visual attribute (anchor) is independently mapped to a source reference image
- A single reference image can provide multiple anchors simultaneously
- Operations: preserve (keep as-is), transfer (move from source), match (match quality), remove, replace, add, modify

Anchor taxonomy:
- subject: identity, facial_features, face_shape, hairstyle, hair_texture, skin_texture, body_shape, body_proportion
- appearance: clothing, shoes, glasses, hat, earrings, necklace, bag, accessories
- environment: scene, background, foreground, furniture, architecture, weather, time_of_day, scene_objects
- objects: standalone items (dog, chair, phone, guitar, etc.)
- composition: pose, framing, camera_angle, facing_direction, subject_position
- photography: lighting, exposure, camera_style, depth_of_field, texture_realism
- edit: remove, replace, preserve, add

Important rules:
- identity is ALWAYS critical priority, operation=preserve
- clothing/hairstyle/objects use operation=transfer
- skin_texture/hair_texture/lighting use operation=match
- scene uses operation=preserve
- Default body_proportion: small head, broad shoulders
- Default camera_style: realistic iPhone photo
- Default realism: natural photorealistic human appearance
- Objects should have preserve=["appearance", "color", "texture"]

Return JSON with:
{
  "anchors": [{"type": "...", "category": "...", "source": "image_N", "operation": "...", "priority": "...", "description": "..."}],
  "objects": [{"name": "...", "source": "image_N", "operation": "transfer", "preserve": [...], "position": "..."}],
  "composition": {"pose": "...", "facing": "...", "framing": "...", "camera_angle": "..."},
  "canonical_prompt": "..."
}"""


def gpt_optimize(text: str, reference_count: int = 3) -> OptimizedResult | None:
    """Use GPT to parse the user's request into anchor-based format."""
    try:
        from idolmv_pipeline.config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not configured, skipping GPT optimizer")
            return None
    except ImportError:
        return None

    try:
        import requests
    except ImportError:
        return None

    ref_hint = "、".join([f"图{i+1}" for i in range(reference_count)])
    user_message = f"用户输入：{text}\n\n可用的参考图：{ref_hint}"

    try:
        resp = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": OPTIMIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(raw)
    except Exception as e:
        logger.warning("GPT optimizer failed: %s", e)
        return None

    # Convert GPT output to OptimizedResult
    gpt_anchors = result.get("anchors", [])
    gpt_objects = result.get("objects", [])
    gpt_composition = result.get("composition", {})
    canonical_prompt = result.get("canonical_prompt", "")

    anchors = []
    for a in gpt_anchors:
        anchor_type = a.get("type", "")
        if anchor_type not in ANCHOR_TAXONOMY:
            continue
        taxonomy = ANCHOR_TAXONOMY[anchor_type]
        anchors.append(Anchor(
            type=anchor_type,
            category=a.get("category", taxonomy["category"]),
            source=a.get("source", ""),
            operation=a.get("operation", _infer_operation(anchor_type, "")),
            priority=a.get("priority", taxonomy["priority"]),
            description=a.get("description", taxonomy["description"]),
            object_name=a.get("object_name", ""),
            preserve_attrs=a.get("preserve_attrs", []),
            position=a.get("position", ""),
        ))

    objects = []
    for o in gpt_objects:
        objects.append(ObjectAnchor(
            name=o.get("name", ""),
            source=o.get("source", ""),
            operation=o.get("operation", "transfer"),
            preserve=o.get("preserve", []),
            position=o.get("position", ""),
        ))

    composition = CompositionConfig(
        pose=gpt_composition.get("pose", ""),
        facing=gpt_composition.get("facing", ""),
        framing=gpt_composition.get("framing", ""),
        camera_angle=gpt_composition.get("camera_angle", ""),
    )

    # Build anchors dict for schema construction
    anchors_dict = {}
    for a in anchors:
        key = f"object:{a.object_name}" if a.type == "object" and a.object_name else a.type
        anchors_dict[key] = a

    schema = _build_structured_schema(anchors_dict, objects, composition, [])
    if not canonical_prompt:
        canonical_prompt = _render_canonical_prompt(schema, reference_count)

    aspects = _build_aspects(anchors_dict, composition)
    references = _build_reference_configs(anchors_dict, objects, reference_count)

    return OptimizedResult(
        raw_text=text,
        anchors=anchors,
        objects=objects,
        composition=composition,
        aspects=aspects,
        references=references,
        canonical_prompt=canonical_prompt,
        structured_schema=schema,
        source="gpt",
    )


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


def optimize(text: str, reference_names: list[str] | None = None) -> dict:
    """Main entry point: optimize user text into anchor-based structured output.

    Returns a dict with:
    - anchors: list of anchor objects with type/category/source/operation/priority
    - objects: list of standalone object references
    - composition: pose/framing/facing/camera_angle
    - aspects: form pre-fill configs
    - references: reference binding configs
    - canonical_prompt: rendered English prompt
    - structured_schema: full intermediate representation
    - source: "gpt" | "keyword"
    - global_defaults: current defaults
    """
    ref_count = len(reference_names) if reference_names else 3
    text = text.strip()
    if not text:
        raise ValueError("请提供图文合成描述")

    # Try GPT first
    result = gpt_optimize(text, ref_count)
    source = "gpt"

    if result is None:
        result = parse_natural_language(text, ref_count)
        source = "keyword"

    # Map reference image indices to actual filenames if provided
    references_out = [asdict(r) for r in result.references]
    if reference_names:
        references_out = _map_reference_names(references_out, reference_names)

    return {
        "anchors": [asdict(a) for a in result.anchors],
        "objects": [asdict(o) for o in result.objects],
        "composition": asdict(result.composition),
        "aspects": [asdict(a) for a in result.aspects],
        "references": references_out,
        "canonical_prompt": result.canonical_prompt,
        "structured_schema": result.structured_schema,
        "source": source,
        "global_defaults": GLOBAL_DEFAULTS,
    }


def _map_reference_names(
    refs: list[dict], names: list[str],
) -> list[dict]:
    """Replace placeholder image keys with actual filenames."""
    img_label_to_idx = {"图1": 0, "图2": 1, "图3": 2, "图4": 3, "图5": 4, "图6": 5}
    for ref in refs:
        idx = img_label_to_idx.get(ref.get("file", ""), -1)
        if 0 <= idx < len(names):
            ref["file"] = names[idx]
    return refs
