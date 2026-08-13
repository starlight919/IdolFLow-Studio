"""
Seedance Prompt — V2 七层语义架构
===================================

设计目标：不再按素材类型堆叠，而是按模型需要完成的任务组织。

    Layer 1  TASK               — 定义任务目标
    Layer 2  REFERENCE MAP      — 各素材职责分工
    Layer 3  PERFORMANCE        — 动作 / 口型契约
    Layer 4  PRESERVATION       — 人物、场景保持
    Layer 5  CAMERA             — 镜头策略
    Layer 6  QUALITY            — 全局质量约束
    Layer 7  CUSTOM             — 歌词 + 用户自定义

核心原则：
    1. 先讲任务，再讲限制（正向描述优先）
    2. Reference Ownership — 人物/场景/动作单一职责
    3. 口型多源融合 — Lyrics + Audio + Video 共同约束
    4. 时间轴显式强调 — from start to end, same timeline

详见 docs/guides/Prompt_Design.md
"""

from __future__ import annotations

from idolmv_pipeline.video_tasks.models import TaskMode, CameraPolicy

# ── 分隔符 ────────────────────────────────────────────────────────────────────
_SEP = "\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1 — Task Contract
# ═══════════════════════════════════════════════════════════════════════════════

_TASK: dict[TaskMode, str] = {
    "lip_sync": (
        "让图片1中的人物在保持原人物、场景和构图的情况下，"
        "按照参考视频、参考音频和给定歌词完成自然准确的演唱/说话口型。"
    ),
    "motion": (
        "让图片1中的人物完整模仿视频1中的身体动作，"
        "同时保持图片1中的人物身份、服装、场景和整体视觉效果。"
    ),
    "dance_lip_sync": (
        "让图片1中的人物完整模仿视频1中的身体动作，"
        "同时结合参考视频、参考音频和歌词完成准确对口型。"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 2 — Reference Map
# ═══════════════════════════════════════════════════════════════════════════════

def _build_ref_map(mode: TaskMode, has_audio: bool, has_video: bool = True) -> str:
    lines = ["参考分工："]

    if mode == "lip_sync":
        lines.append("- 图片1：负责人物身份、脸部、肤色、发型、服装、体型、场景、构图和光线。")
        if has_video:
            lines.append("- 视频1：负责参考嘴形、嘴部开合、唇形变化以及对应的视觉口型时间。")
        if has_audio:
            lines.append("- 参考音频：负责实际发音、音节、节奏、持续时间、发音起止和停顿。")
        lines.append("- 歌词：负责准确的字词、音节内容和发音顺序。")

    elif mode == "motion":
        lines.append("- 图片1：负责人物身份、脸部、发型、服装、体型、场景、构图和光线。")
        lines.append("- 视频1：仅负责身体动作、姿态变化、动作顺序、运动轨迹、动作幅度和节奏。")

    elif mode == "dance_lip_sync":
        lines.append("- 图片1：负责人物身份、脸部、发型、服装、体型、场景、构图和光线。")
        lines.append("- 视频1：负责身体动作，同时提供视觉嘴形与口型时间参考。")
        if has_audio:
            lines.append("- 参考音频：负责实际发音、节奏、音节持续时间、起止和停顿。")
        lines.append("- 歌词：负责准确的演唱/说话内容和发音顺序。")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 3 — Performance Contract
# ═══════════════════════════════════════════════════════════════════════════════

# ── 口型契约 ──

def _lip_sync_contract(has_audio: bool, has_video: bool) -> str:
    """多源口型融合：Lyrics(linguistic) + Audio(acoustic+temporal) + Video(visual+temporal)"""
    parts = []

    # 三重约束
    if has_audio and has_video:
        parts.append(
            "对口型必须同时结合歌词、参考音频和视频1。"
            "歌词用于确定准确的字词、音节和发音顺序，"
            "不得漏字、错字、吞字或增加额外内容。"
            "参考音频用于确定实际发音、节奏、每个音节的持续时间、发音起止、停顿以及整体时间轴。"
            "视频1用于确定每个发音对应的嘴形、嘴部开合幅度、唇形转换、闭口时机和连续口型变化。"
            "生成口型必须同时满足：正确的歌词内容、正确的发音时间，以及对应时间点正确自然的视觉嘴形。"
            "不得只依据其中任意一种参考生成口型。"
        )
    elif has_video:
        parts.append(
            "歌词负责文字和发音顺序；视频1共同提供实际口型、发音节奏、嘴形变化和时间节点。"
            "生成口型必须同时满足正确歌词内容以及对应时间点正确自然的视觉嘴形。"
        )
    elif has_audio:
        parts.append(
            "歌词负责准确字词与发音顺序；参考音频负责实际发音、节奏、持续时间、起止和停顿。"
            "根据歌词与参考音频生成自然、符合真实发音规律的嘴形变化。"
        )

    # 时间同步
    if has_audio and has_video:
        parts.append(
            "参考音频和视频1共同约束口型时间。"
            "音频用于确认发音实际开始、持续和结束的时间；"
            "视频用于确认对应时间点嘴部开始运动、展开、转换和闭合的时机。"
            "保持声音与嘴部动作处于同一时间轴，"
            "避免声音开始后嘴仍未运动、声音结束后嘴仍持续发音，"
            "或嘴部动作相对参考出现明显提前或延迟。"
        )

    # 自然微动作（lip_sync 模式）
    parts.append(
        "除口型外，仅保留自然眨眼、轻微面部表情、"
        "正常呼吸和极小幅度的自然头部微动。"
        "身体主体保持稳定，不主动增加明显手势或大幅身体动作。"
    )

    return "\n".join(parts)


# ── 动作契约 ──

_MOTION_CONTRACT = (
    "完整复现视频1从开始到结束的动作编排。"
    "保持相同的动作顺序、动作节奏、速度变化、身体朝向、"
    "重心变化、手臂轨迹、腿部动作、动作幅度、关键姿态与卡点。"
    "不得遗漏动作、交换动作顺序、增加额外动作、重复动作或自行重新编排。"
)

_MOTION_BODY_ADAPT = (
    "动作需要自然适配图片1人物原有的身体比例和当前构图。"
    "优先保持动作语义、节奏、方向、轨迹和关键姿态的一致，"
    "不要为了机械复制参考人物的绝对空间位置而拉伸、扭曲或改变目标人物身体结构。"
)


def _motion_contract() -> str:
    return "\n".join([_MOTION_CONTRACT, _MOTION_BODY_ADAPT])


# ── 动作 + 口型对齐 ──

_MOTION_LIP_ALIGNMENT = (
    "身体动作与口型保持在同一完整时间轴中。"
    "不得因身体动作导致口型提前或延迟，"
    "也不得为了口型同步而跳过、重复或重新排序身体动作。"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 4 — Preservation Contract
# ═══════════════════════════════════════════════════════════════════════════════

_PRESERVATION = (
    "始终保持图片1中的同一人物。"
    "全程保持人物脸型、五官、肤色、发型、发色、服装、体型和身体比例稳定。"
    "保持图片1中的原始场景、主要背景元素、光线和视觉风格。"
    "参考视频中的人物身份、服装和场景不得替换图片1中的对应内容。"
)

_PRESERVATION_MOTION_EXTRA = (
    "即使发生转头、抬手、快速运动、身体旋转或局部遮挡，"
    "人物脸部身份和整体外观仍需保持稳定。"
)


def _build_preservation(mode: TaskMode) -> str:
    parts = [_PRESERVATION]
    if mode in ("motion", "dance_lip_sync"):
        parts.append(_PRESERVATION_MOTION_EXTRA)
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 5 — Camera Policy
# ═══════════════════════════════════════════════════════════════════════════════

_CAMERA: dict[CameraPolicy, str] = {
    "locked": (
        "镜头固定，保持图片1原始视角和构图。"
        "不进行推拉、摇移、旋转、缩放或主动重新构图。"
    ),
    "keep_image": (
        "整体保持图片1的原始镜头、视角和构图。"
        "允许为了完整容纳人物动作产生必要的小幅构图适配，"
        "但不主动增加额外电影式运镜。"
    ),
    "follow_video": (
        "人物动作和镜头运动均参考视频1，"
        "同时保持图片1中的人物身份、服装、场景和视觉外观。"
    ),
}

_CAMERA_DEFAULTS: dict[TaskMode, CameraPolicy] = {
    "lip_sync": "locked",
    "motion": "keep_image",
    "dance_lip_sync": "keep_image",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 6 — Quality Guard
# ═══════════════════════════════════════════════════════════════════════════════

_QUALITY = (
    "保持人物动作连续自然，脸部、身体和手部结构稳定。"
    "避免身份漂移、五官变化、关节扭曲、肢体拉伸、穿模、机械抖动、画面闪烁和背景形变。"
    "保持真实自然的皮肤与头发质感，避免明显塑料感、过度平滑和不自然AI纹理。"
    "不得生成字幕、歌词文字、水印、logo、贴纸、平台图标或原画面不存在的叠加元素。"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 7 — Lyrics & Custom
# ═══════════════════════════════════════════════════════════════════════════════

def _build_plain_lyrics(lyrics: str) -> str:
    return f"演唱/说话内容：\n{lyrics}"


def _has_lyrics_timestamps(lyrics_timestamps) -> bool:
    """是否存在至少一个有效人工时间点（time 非 None）。

    数组可能为空、不存在，或全部 time == None，这些都视为「无时间戳」。
    """
    return bool(
        lyrics_timestamps
        and any(item.get("time") is not None for item in lyrics_timestamps)
    )


def _build_timestamped_lyrics(lyrics: str, lyrics_timestamps, timestamp_offset: float = 0.0) -> str:
    """带人工时间点的歌词渲染。

    设计见 docs/guides/Prompt_Design.md §12.2：
    - 全部歌词都有时间：直接输出「时间 + 歌词」。
    - 部分歌词有时间：完整歌词写一遍，再单独列出已标注的时间点。
    不把 null / onset / end_time 等工程字段写进 prompt。

    timestamp_offset：时间戳偏移量（秒）。当 pad_mode="front" 时，
    音频前面补了静音，实际起唱时间整体后移，需把每个时间点加上该偏移。
    """
    items = [
        item for item in (lyrics_timestamps or [])
        if str(item.get("text", "")).strip()
    ]
    timed = [item for item in items if item.get("time") is not None]

    def _ts(item):
        return item["time"] + timestamp_offset

    if items and len(timed) == len(items):
        # 全部歌词都有时间
        lines = ["全程自然对口型唱歌，严格按以下歌词和时间对口型："]
        lines += [
            f'{_ts(item):.2f}s开始唱“{str(item["text"]).strip()}”；'
            for item in items
        ]
    else:
        # 部分歌词有时间（或时间戳文本与歌词框不一致时的兜底）
        lines = ["演唱/说话内容：", lyrics]
        if timed:
            lines += [
                "",
                "严格按以下已标注时间对口型：",
                *(
                    f'{_ts(item):.2f}s开始唱“{str(item["text"]).strip()}”；'
                    for item in timed
                ),
                "其余歌词按原顺序结合参考音频和视频自然衔接。",
            ]

    lines += [
        "保持整体演唱节奏、停顿和嘴部动作与参考音频、视频一致。",
        "唱完后自然收尾。",
    ]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Build
# ═══════════════════════════════════════════════════════════════════════════════

def build_prompt(
    mode: TaskMode,
    lyrics: str | None = "",
    constraints: str | None = "",
    has_audio_ref: bool = False,
    has_video_ref: bool = True,
    camera_policy: CameraPolicy | None = None,
    lyrics_timestamps: list[dict] | None = None,
    timestamp_offset: float = 0.0,
) -> str:
    """按 V2 七层语义架构构建 Seedance prompt。

    Args:
        mode: 生成模式
        lyrics: 歌词文本，对口型模式必填
        constraints: 用户自定义约束
        has_audio_ref: 是否有参考音频
        has_video_ref: 是否有参考视频（纯音频对口型时为 False）
        camera_policy: 镜头策略，None 时使用模式默认值
        lyrics_timestamps: 歌词人工时间点（可选），格式 [{text, time}]，
            time 为秒（float），未打点为 None。仅当存在有效 time 时才进入
            带时间戳的歌词分支，否则退化为普通歌词。
        timestamp_offset: 时间戳偏移量（秒）。pad_mode="front" 时音频前面
            补静音导致起唱时间后移，需传入 ceil(total)-total 作为偏移。
    """
    lyrics = str(lyrics or "").strip()
    constraints = str(constraints or "").strip()
    if mode in {"lip_sync", "dance_lip_sync"} and not lyrics:
        raise ValueError(f"{mode} requires lyrics")
    camera = camera_policy or _CAMERA_DEFAULTS[mode]

    parts: list[str] = []

    # Layer 1 — Task
    parts.append(_TASK[mode])

    # Layer 2 — Reference Map
    parts.append(_build_ref_map(mode, has_audio_ref, has_video_ref))

    # Layer 3 — Performance
    if mode == "lip_sync":
        parts.append(_lip_sync_contract(has_audio_ref, has_video_ref))
    elif mode == "motion":
        parts.append(_motion_contract())
    elif mode == "dance_lip_sync":
        parts.append(_motion_contract())
        parts.append(_lip_sync_contract(has_audio_ref, has_video_ref))
        parts.append(_MOTION_LIP_ALIGNMENT)

    # Layer 4 — Preservation
    parts.append(_build_preservation(mode))

    # Layer 5 — Camera
    parts.append(_CAMERA[camera])

    # Layer 6 — Quality
    parts.append(_QUALITY)

    # Layer 7 — Lyrics & Custom
    if lyrics:
        if _has_lyrics_timestamps(lyrics_timestamps):
            parts.append(_build_timestamped_lyrics(lyrics, lyrics_timestamps, timestamp_offset))
        else:
            parts.append(_build_plain_lyrics(lyrics))
    if constraints:
        parts.append(f"额外要求：\n{constraints}")

    return _SEP.join(parts)
