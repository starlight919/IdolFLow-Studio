from __future__ import annotations

from dataclasses import asdict, dataclass

ASPECTS = {
    "identity_face": "人物五官",
    "hair_style": "发型",
    "hair_texture": "头发质感",
    "skin_texture": "皮肤质感",
    "wardrobe": "服装",
    "scene": "场景",
    "lighting": "光线",
    "pose_expression": "姿势与表情",
    "composition_camera": "构图与镜头",
    "visual_style": "整体质感",
}
PRIORITIES = {"locked", "required", "preferred"}
SIZES = {"1024x1024", "1792x1024", "1024x1792"}


@dataclass(frozen=True)
class AnchorAspect:
    key: str
    description: str = ""
    priority: str = "required"
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "AnchorAspect":
        key = str(data.get("key", "")).strip()
        description = str(data.get("description", "")).strip()
        priority = str(data.get("priority", "required"))
        label = str(data.get("label", "")).strip()
        if not key:
            raise ValueError("aspect key is required")
        if key not in ASPECTS and not label:
            raise ValueError(f"custom aspect requires a label: {key}")
        if priority not in PRIORITIES:
            raise ValueError(f"invalid aspect priority: {priority}")
        return cls(key, description, priority, label)


@dataclass(frozen=True)
class AnchorReferenceBinding:
    aspect: str
    content: str = ""
    constraint: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "AnchorReferenceBinding":
        aspect = str(data.get("aspect", "")).strip()
        if not aspect:
            raise ValueError("reference binding aspect is required")
        return cls(
            aspect,
            str(data.get("content", "")).strip(),
            str(data.get("constraint", "")).strip(),
        )


@dataclass(frozen=True)
class AnchorReference:
    id: str
    file: str
    bindings: tuple[AnchorReferenceBinding, ...]
    note: str = ""
    remove_watermark: bool = False

    @property
    def aspects(self) -> tuple[str, ...]:
        return tuple(binding.aspect for binding in self.bindings)

    @classmethod
    def from_dict(cls, data: dict) -> "AnchorReference":
        reference_id = str(data.get("id", "")).strip()
        file = str(data.get("file", "")).strip()
        if "bindings" in data:
            bindings = tuple(AnchorReferenceBinding.from_dict(item) for item in data.get("bindings", []))
        else:
            bindings = tuple(
                AnchorReferenceBinding(str(value).strip())
                for value in data.get("aspects", [])
                if str(value).strip()
            )
        if not reference_id or not file:
            raise ValueError("reference id and file are required")
        if not bindings:
            raise ValueError(f"reference {reference_id} must select at least one aspect")
        aspects = [binding.aspect for binding in bindings]
        if len(aspects) != len(set(aspects)):
            raise ValueError(f"reference {reference_id} has duplicate aspect bindings")
        return cls(
            reference_id,
            file,
            bindings,
            str(data.get("note", "")).strip(),
            bool(data.get("remove_watermark", False)),
        )


@dataclass(frozen=True)
class AnchorTask:
    id: str
    name: str
    description: str
    negative: str
    size: str
    resolution: str
    candidates: int
    aspects: tuple[AnchorAspect, ...]
    references: tuple[AnchorReference, ...]
    model: str = "gpt-image-2"

    @classmethod
    def from_dict(cls, data: dict) -> "AnchorTask":
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("anchor task name is required")
        task_id = str(data.get("id") or name).strip()
        model = str(data.get("model", "gpt-image-2")).strip()
        if model != "gpt-image-2":
            raise ValueError("anchor model must be gpt-image-2")
        size = str(data.get("size", "1024x1792"))
        if size not in SIZES:
            raise ValueError(f"invalid anchor size: {size}")
        resolution = str(data.get("resolution", "2K")).upper()
        if resolution not in {"1K", "2K", "4K"}:
            raise ValueError(f"invalid anchor resolution: {resolution}")
        if size == "1024x1024" and resolution == "4K":
            raise ValueError("1:1 anchors do not support 4K")
        aspects = tuple(AnchorAspect.from_dict(item) for item in data.get("aspects", []))
        references = tuple(AnchorReference.from_dict(item) for item in data.get("references", []))
        if len(references) > 16:
            raise ValueError("gpt-image-2 accepts at most 16 reference images")
        keys = [item.key for item in aspects]
        if len(keys) != len(set(keys)):
            raise ValueError("aspect keys must be unique")
        reference_ids = [item.id for item in references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("reference ids must be unique")
        known = set(keys)
        for reference in references:
            unknown = set(reference.aspects) - known
            if unknown:
                raise ValueError(f"reference {reference.id} has unknown aspects: {', '.join(sorted(unknown))}")
        description = str(data.get("description", "")).strip()
        if not description and not any(item.description for item in aspects) and not references:
            raise ValueError("describe the anchor or provide a reference image")
        return cls(
            task_id, name, description, str(data.get("negative", "")).strip(), size, resolution,
            max(1, int(data.get("candidates", 4))), aspects, references, model,
        )

    def to_dict(self) -> dict:
        return asdict(self)
