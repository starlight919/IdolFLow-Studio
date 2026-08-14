from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"

TaskKind = Literal["singing", "dance"]
TaskMode = Literal["lip_sync", "dance_lip_sync", "motion"]
SplitMode = Literal["single", "fixed", "low_energy"]
ContinuationMode = Literal["none", "last_frame", "anchor_and_last_frame"]
CameraPolicy = Literal["locked", "keep_image", "follow_video"]


@dataclass(frozen=True)
class AnchorSpec:
    key: str
    file: str
    label: str
    tags: tuple[str, ...] = ()
    prompt_variant: str | None = None


@dataclass(frozen=True)
class SegmentSpec:
    start: float
    cut_duration: float | None
    seedance_duration: int

    def __post_init__(self):
        if not isinstance(self.seedance_duration, int) or not 4 <= self.seedance_duration <= 30:
            raise ValueError("seedance_duration must be an integer from 4 to 30")


@dataclass(frozen=True)
class ReferenceSpec:
    name: str
    file: str
    audio_file: str | None = None
    audio_file_url: str | None = None
    pass_reference_audio: bool = True  # 是否上传参考音频给 Seedance 做口型同步
    pass_reference_video: bool = True  # 是否上传参考视频给 Seedance（False=纯口型，只传音频）
    trim_duration: int = 15
    split_mode: SplitMode = "single"
    segments: tuple[SegmentSpec, ...] = ()
    crop_filter: str | None = None
    pad_mode: str = "back"  # none=原始时长, front=前面补齐, back=后面补齐

    def __post_init__(self):
        if not isinstance(self.trim_duration, int) or not 4 <= self.trim_duration <= 30:
            raise ValueError("trim_duration must be an integer from 4 to 30")
        if self.split_mode == "fixed" and not self.segments:
            raise ValueError("fixed references require segments")


@dataclass(frozen=True)
class PromptVariant:
    name: str
    first_prompt: str
    continuation_prompt: str | None = None


@dataclass(frozen=True)
class CandidatePolicy:
    count: int = 4
    poll_workers: int = 4

    def __post_init__(self):
        if self.count < 1:
            raise ValueError("candidate count must be positive")
        if self.poll_workers < 1:
            raise ValueError("poll_workers must be positive")


@dataclass(frozen=True)
class PublishSpec:
    repo: Path = PROJECT_ROOT / "runtime" / "publish"
    subdirectory: str = "selected"
    filename_prefix: str = "video"


@dataclass(frozen=True)
class VideoTaskAdapter:
    name: str
    kind: TaskKind
    anchors: tuple[AnchorSpec, ...]
    references: tuple[ReferenceSpec, ...]
    prompts: tuple[PromptVariant, ...]
    mode: TaskMode | None = None
    candidate_policy: CandidatePolicy = CandidatePolicy()
    publish: PublishSpec = PublishSpec()
    lyrics_file: str | None = None
    identity_image: str | None = None
    continuation: ContinuationMode = "none"
    model: str = "sd2.5"
    ratio: str = "9:16"
    resolution: str = "720p"
    generate_audio: bool = False
    watermark: bool = False
    output_format: str = "mp4"
    camera_policy: CameraPolicy | None = None
    source_root: Path = DEFAULT_DATA_ROOT
    task_path: Path | None = None
    work_path: Path | None = None
    output_path: Path | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def task_dir(self) -> Path:
        return self.task_path or self.source_root / self.name

    @property
    def output_dir(self) -> Path:
        return self.output_path or self.task_dir / "outputs"

    @property
    def work_dir(self) -> Path:
        return self.work_path or self.task_dir / "work"

    @property
    def assets_file(self) -> Path:
        return self.task_dir / "seedance" / "assets.json"

    def to_dict(self) -> dict:
        result = asdict(self)
        result["source_root"] = str(self.source_root)
        for key in ("task_path", "work_path", "output_path"):
            if result[key] is not None:
                result[key] = str(result[key])
        result["task_dir"] = str(self.task_dir)
        result["publish"]["repo"] = str(self.publish.repo)
        return result
