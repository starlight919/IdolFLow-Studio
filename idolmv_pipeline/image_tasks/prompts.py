from __future__ import annotations

from idolmv_pipeline.image_tasks.models import ASPECTS, AnchorTask

PRESETS = {
    "identity_face": {
        "same_person": "保持与参考图完全相同的人物身份、五官、骨相、年龄感和肤色，不换脸，不发生人物漂移。",
        "natural_face": "自然真实的人脸比例与五官，避免网红化、欧美化或过度美化。",
    },
    "hair_style": {
        "same_hair": "保持参考图中的发型、发际线、长度和造型。",
        "natural_hair": "发型自然利落，符合人物气质和真实摄影状态。",
    },
    "hair_texture": {"real_hair": "保留真实细密发丝、自然蓬松度与高光，不要塑料假发质感。"},
    "skin_texture": {"real_skin": "保留真实皮肤纹理和自然妆感，不过度磨皮，不要塑料皮肤。"},
    "wardrobe": {
        "stage_dark": "深色高级舞台服，版型修身，材质有真实细节，克制而上镜。",
        "casual_clean": "简洁清爽的日常服装，真实自然，不夸张。",
    },
    "scene": {
        "clean_studio": "简洁干净的真实摄影棚背景，背景不抢人物。",
        "outdoor_stage": "真实室外音乐会舞台，有克制的舞台结构和自然环境氛围。",
        "bedroom": "有真实生活感的卧室，不是样板间或酒店，背景干净克制。",
    },
    "lighting": {
        "soft_natural": "柔和自然光，面部清楚，明暗过渡真实。",
        "cinematic_side": "电影感侧光，方向明确，保留暗部细节和真实人脸塑形。",
        "stage_light": "真实舞台灯光，人物面部清晰，避免夜店霓虹和科幻色光。",
    },
    "pose_expression": {
        "front_relaxed": "人物正面或接近正面，姿态放松，表情自然，不僵硬摆拍。",
        "singing": "自然演唱状态，嘴部清楚，手部与话筒关系合理。",
    },
    "composition_camera": {
        "close_portrait": "近景到中近景，突出脸部、肩颈和自然表情，浅景深。",
        "half_body": "半身构图，身体比例、双手和透视自然。",
        "full_body": "全身构图，人物完整入镜，肢体比例和站姿自然。",
        "small_head_wide_shoulders": "头小肩宽比例，上下半身匀称，站姿挺拔舒展，视觉上显高挑。",
    },
    "visual_style": {"photoreal": "超写实真人摄影，真实皮肤、头发和布料细节，避免插画、CG 和 AI 塑料感。"},
}

PRIORITY_TEXT = {"locked": "必须严格保持", "required": "必须满足", "preferred": "优先参考"}

# ── Quality / Style presets (multi-select) ──
QUALITY_PRESETS = {
    "iphone_shot": "真实iPhone手机拍摄画面",
    "raw_camera": "原相机直出质感",
    "real_person": "真人实拍，非CG/AI生成感",
    "live_stage": "真实舞台/演出现场氛围",
    "warm_tone": "暖色调，电影感调色",
    "clean_frame": "画面干净无杂物，构图精炼",
    "high_detail": "高分辨率，细节锐利，布料/发丝纹理可见",
    "natural_blur": "真实光学浅景深，非后期高斯模糊",
}

# ── Negative constraints presets (multi-select) ──
NEGATIVE_PRESETS = {
    "no_watermark": "不要水印、台标、角标",
    "no_text": "不要任何文字、字幕、logo",
    "no_deformed_hands": "不要畸形手指、多余手指、断指",
    "no_blur": "不要模糊、跑焦、运动模糊",
    "no_cg": "不要AI塑料感、CG渲染感、过度平滑",
    "no_extra_people": "不要画面中出现其他人",
    "no_nsfw": "不要裸露、低俗、不雅内容",
    "no_border": "不要边框、相框、白边",
}


def preset_options() -> dict:
    return {
        "aspects": {key: {"label": ASPECTS[key], "presets": values} for key, values in PRESETS.items()},
        "quality": QUALITY_PRESETS,
        "negative": NEGATIVE_PRESETS,
    }


def build_anchor_prompt(task: AnchorTask) -> tuple[str, list[dict]]:
    lines = ["生成一张可直接用于视频生成的高质量 Anchor 图片。"]
    if task.description:
        lines.append(f"整体目标：{task.description}")
    aspect_map = {item.key: item for item in task.aspects}
    if task.aspects:
        lines.append("分维度约束：")
        for aspect in task.aspects:
            label = ASPECTS.get(aspect.key, aspect.label or aspect.key)
            description = aspect.description or "按关联参考图执行"
            lines.append(f"- {label}（{PRIORITY_TEXT[aspect.priority]}）：{description}")
    mapping = []
    if task.references:
        lines.append("参考图使用规则：")
        for index, reference in enumerate(task.references, 1):
            labels = [ASPECTS.get(binding.aspect, aspect_map[binding.aspect].label or binding.aspect) for binding in reference.bindings]
            ignored = [ASPECTS.get(key, item.label or key) for key, item in aspect_map.items() if key not in reference.aspects]
            lines.append(f"- 参考图 {index} 只用于：{'、'.join(labels)}。")
            for binding in reference.bindings:
                label = ASPECTS.get(binding.aspect, aspect_map[binding.aspect].label or binding.aspect)
                details = []
                if binding.content:
                    details.append(f"参考内容：{binding.content}")
                if binding.constraint:
                    details.append(f"约束：{binding.constraint}")
                lines.append(f"  - {label}：{'；'.join(details) if details else '按该图与全局维度要求执行'}。")
            if ignored:
                lines.append(f"  - 不要从该图继承{'、'.join(ignored)}。")
            if reference.note:
                lines.append(f"  - 全图规则：{reference.note}")
            if reference.remove_watermark:
                lines.append("  - 该参考图含有水印或文字标记；只提取绑定的视觉特征，忽略并去除水印、文字、Logo、角标及其遮挡痕迹，不要复制到生成结果。")
            lines.append("")
            mapping.append({
                "index": index,
                "id": reference.id,
                "file": reference.file,
                "bindings": [
                    {
                        "aspect": binding.aspect,
                        "content": binding.content,
                        "constraint": binding.constraint,
                    }
                    for binding in reference.bindings
                ],
                "note": reference.note,
                "remove_watermark": reference.remove_watermark,
            })
        lines.append("多张参考图描述的是同一个最终人物和画面，各自只提供已标注维度的互补证据，不要生成多个人物或拼贴画面。")
    lines.append("画面必须完整、自然、可直接作为后续视频首帧；避免畸形手、额外肢体、重复人物、文字、字幕、Logo 和水印。")
    if task.negative:
        lines.append(f"禁止项：{task.negative}")
    return "\n".join(lines), mapping
