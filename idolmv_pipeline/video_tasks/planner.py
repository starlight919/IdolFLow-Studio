"""AssetPlanner —— 统一的素材缓存决策引擎

设计依据：`docs/guides/Asset_Design.md` §7。

职责：
- 对每个素材（Anchor 图 / 参考音频 / 参考视频切片），结合
  Source / Artifact / Remote Asset / Snapshot 的存在与状态，
  决定本次提交应该执行的 5 种 Asset Action 之一。
- 后端 Status API 与 Runner 共用本决策引擎（单一决策来源），
  避免"UI 显示复用、Runner 实际失败"的不一致。

本模块是**纯决策逻辑**：不执行文件 I/O、不上传。调用方（runner/handler）
负责完成 inspect（把磁盘/云端状态解析为 InspectedMaterial）后传入。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Asset Action（V2 §33）
# ---------------------------------------------------------------------------
REUSE_REMOTE = "REUSE_REMOTE"                     # 直接复用已上传的云端 asset
UPLOAD_EXISTING_ARTIFACT = "UPLOAD_EXISTING_ARTIFACT"  # 产物已有效，仅上传产物
BUILD_AND_UPLOAD = "BUILD_AND_UPLOAD"             # 需重建产物并上传
NEED_SOURCE_FOR_REBUILD = "NEED_SOURCE_FOR_REBUILD"   # 源缺失但需重 build
NEED_MATERIAL_REBIND = "NEED_MATERIAL_REBIND"     # 素材不可识别/缺失，需重选

# ---------------------------------------------------------------------------
# Reason Code（V2 §59）
# ---------------------------------------------------------------------------
REASON_CACHE_HIT = "CACHE_HIT"
REASON_FIRST_UPLOAD = "FIRST_UPLOAD"
REASON_SOURCE_CHANGED = "SOURCE_CHANGED"
REASON_TRANSFORM_CHANGED = "TRANSFORM_CHANGED"
REASON_ARTIFACT_MISSING = "ARTIFACT_MISSING"
REASON_REMOTE_ASSET_MISSING = "REMOTE_ASSET_MISSING"
REASON_SOURCE_MISSING_REMOTE_REUSE = "SOURCE_MISSING_REMOTE_REUSE"
REASON_SOURCE_REQUIRED_FOR_REBUILD = "SOURCE_REQUIRED_FOR_REBUILD"
REASON_REMOTE_ASSET_OPAQUE = "REMOTE_ASSET_OPAQUE"
REASON_MATERIAL_MISSING = "MATERIAL_MISSING"

# ---------------------------------------------------------------------------
# 状态枚举
# ---------------------------------------------------------------------------
SOURCE_PRESENT = "PRESENT"
SOURCE_MISSING = "MISSING"

ARTIFACT_VALID = "VALID"
ARTIFACT_STALE = "STALE"
ARTIFACT_MISSING = "MISSING"

ASSET_AVAILABLE = "AVAILABLE"
ASSET_MISSING = "MISSING"

VISIBILITY_IDENTIFIABLE = "IDENTIFIABLE"
VISIBILITY_OPAQUE = "OPAQUE"
VISIBILITY_UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# 输入结构（由调用方 inspect 后填充）
# ---------------------------------------------------------------------------
@dataclass
class InspectedMaterial:
    """一个素材在 plan 时点的全部相关状态（不含原始数据）。"""

    material_id: str                     # 稳定身份（Phase 2 暂用 asset_key）
    asset_key: str
    source_exists: bool = False          # 本地 Source 是否在
    artifact_valid: bool = False         # Artifact 存在且签名匹配 desired
    artifact_transform: dict | None = None   # Artifact 记录的 transform（若可读）
    asset_exists: bool = False           # 云端 Remote Asset 是否已上传
    asset_transform: dict | None = None  # Remote Asset 记录的 transform
    visibility: str = VISIBILITY_UNKNOWN # IDENTIFIABLE / OPAQUE / UNKNOWN
    desired_transform: dict | None = None   # resolve 后的期望 transform

    def has_source(self) -> bool:
        return self.source_exists

    def has_artifact(self) -> bool:
        return self.artifact_valid or self.artifact_transform is not None

    def artifact_matches(self) -> bool:
        return self.artifact_valid

    def has_asset(self) -> bool:
        return self.asset_exists

    def transform_matches(self, transform: dict | None) -> bool:
        return bool(transform) and bool(self.desired_transform) and transform == self.desired_transform

    def is_identifiable(self) -> bool:
        return self.visibility == VISIBILITY_IDENTIFIABLE


# ---------------------------------------------------------------------------
# 输出结构
# ---------------------------------------------------------------------------
@dataclass
class AssetDecision:
    material_id: str
    asset_key: str
    action: str
    reason: str

    source_state: str = SOURCE_MISSING
    artifact_state: str = ARTIFACT_MISSING
    asset_state: str = ASSET_MISSING
    visibility_state: str = VISIBILITY_UNKNOWN

    current_transform: dict | None = None
    cached_transform: dict | None = None
    preview_url: str | None = None

    can_submit: bool = True
    requires_source: bool = False
    block_reason: str | None = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 决策引擎（V2 §39-41 Decision Matrix）
# ---------------------------------------------------------------------------
def plan_material(m: InspectedMaterial) -> AssetDecision:
    """依据 V2 §39 伪代码 + §41 Decision Matrix，返回该素材的决策。"""
    d = AssetDecision(
        material_id=m.material_id,
        asset_key=m.asset_key,
        action=REUSE_REMOTE,
        reason=REASON_CACHE_HIT,
        source_state=SOURCE_PRESENT if m.source_exists else SOURCE_MISSING,
        artifact_state=ARTIFACT_VALID if m.artifact_valid else (ARTIFACT_STALE if m.artifact_transform is not None else ARTIFACT_MISSING),
        asset_state=ASSET_AVAILABLE if m.asset_exists else ASSET_MISSING,
        visibility_state=m.visibility,
        current_transform=m.desired_transform,
        cached_transform=m.asset_transform if m.asset_exists else m.artifact_transform,
    )

    # ── 有 Source：可计算完整 desired signature ──
    if m.has_source():
        asset_matches = m.transform_matches(m.asset_transform)
        # 产物签名匹配 → 复用云端 asset（或上传产物）
        if m.has_asset() and (m.artifact_matches() or asset_matches):
            d.action, d.reason = REUSE_REMOTE, REASON_CACHE_HIT
        elif m.artifact_matches():
            d.action, d.reason = UPLOAD_EXISTING_ARTIFACT, REASON_CACHE_HIT
        elif m.has_asset():
            # asset 已存在且其 transform 与当前一致 → 复用（兼容产物 marker 缺失的旧资产）
            if asset_matches:
                d.action, d.reason = REUSE_REMOTE, REASON_CACHE_HIT
            else:
                d.action, d.reason = BUILD_AND_UPLOAD, REASON_TRANSFORM_CHANGED
        else:
            d.action, d.reason = BUILD_AND_UPLOAD, REASON_FIRST_UPLOAD
        return d

    # ── Source 缺失 ──
    if m.has_asset():
        # 不可识别 → 需重选
        if not m.is_identifiable():
            d.action, d.reason = NEED_MATERIAL_REBIND, REASON_REMOTE_ASSET_OPAQUE
            d.can_submit = False
            d.block_reason = "无法识别此历史素材，请重新选择"
            d.requires_source = True
            return d
        # 可识别 + transform 匹配 → 复用云端 asset（无需源）
        if m.transform_matches(m.asset_transform):
            d.action, d.reason = REUSE_REMOTE, REASON_SOURCE_MISSING_REMOTE_REUSE
            d.requires_source = False
            return d
        # 可识别 + transform 变化 → 需源重建
        d.action, d.reason = NEED_SOURCE_FOR_REBUILD, REASON_SOURCE_REQUIRED_FOR_REBUILD
        d.can_submit = False
        d.block_reason = "仅云端版本已不能满足当前处理参数，需重新提供源文件"
        d.requires_source = True
        return d

    # ── 云端 asset 不存在 ──
    if m.has_artifact():
        # 本地产物可用
        if m.transform_matches(m.artifact_transform):
            d.action, d.reason = UPLOAD_EXISTING_ARTIFACT, REASON_CACHE_HIT
        else:
            d.action, d.reason = NEED_SOURCE_FOR_REBUILD, REASON_SOURCE_REQUIRED_FOR_REBUILD
            d.can_submit = False
            d.block_reason = "处理参数已变化，需重新提供源文件"
            d.requires_source = True
        return d

    # 全缺失
    d.action, d.reason = NEED_MATERIAL_REBIND, REASON_MATERIAL_MISSING
    d.can_submit = False
    d.block_reason = "素材缺失，请重新选择"
    d.requires_source = True
    return d
