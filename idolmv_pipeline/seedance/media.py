from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def find_low_energy_cut(audio_path: Path, min_t: float, max_t: float, total: float) -> float:
    result = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-af", "silencedetect=noise=-30dB:d=0.1", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    candidates = [
        float(match.group(1)) for match in re.finditer(r"silence_start: ([0-9.]+)", result.stderr)
        if min_t <= float(match.group(1)) <= max_t
    ]
    if candidates:
        return round(min(candidates, key=lambda value: abs(value - total / 2)), 3)
    best_time, lowest_volume = round(total / 2, 3), float("inf")
    for index in range(int((max_t - min_t) / 0.5) + 1):
        sample_time = round(min_t + index * 0.5, 1)
        sample = subprocess.run(
            ["ffmpeg", "-ss", str(sample_time), "-t", "0.5", "-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        match = re.search(r"mean_volume: (-?[0-9.]+)", sample.stderr)
        if match and float(match.group(1)) < lowest_volume:
            lowest_volume, best_time = float(match.group(1)), sample_time
    return best_time


def extract_audio(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(source), "-q:a", "0", "-map", "a", str(destination)], check=True, capture_output=True)


def trim_reference(source: Path, destination: Path, start: float, duration: float, crop_filter: str | None = None, pad_mode: str = "back", original_duration: float | None = None) -> None:
    """Trim video to [start, start+duration], then pad to `duration` total length.
    pad_mode: none=no padding (use original), front=clone first frame at start, back=clone last frame at end.
    original_duration: actual media duration, used to calculate pad amount (duration - original_duration)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + ".tmp.mp4")
    # 1. 截取视频
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", str(source), "-an",
         "-vf", crop_filter or "scale=480:854",
         "-c:v", "mpeg4", "-q:v", "5", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)],
        check=True, capture_output=True,
    )
    if pad_mode == "none":
        tmp.replace(destination)
        return
    # 2. 计算需要补的时长
    if original_duration is not None:
        pad_amount = max(0, duration - original_duration)
    else:
        pad_amount = duration  # fallback: 全部当 padding
    if pad_amount < 0.01:
        tmp.replace(destination)
        return
    # 3. 补帧到目标时长
    if pad_mode == "front":
        vf = f"tpad=start_mode=clone:start_duration={pad_amount}:stop_duration=0"
    else:  # back
        vf = f"tpad=stop_mode=clone:stop_duration={pad_amount}:start_duration=0"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp),
         "-vf", vf,
         "-an", "-c:v", "mpeg4", "-q:v", "5", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)],
        check=True, capture_output=True,
    )
    tmp.unlink(missing_ok=True)


def extract_last_frame(video: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-sseof", "-0.1", "-i", str(video), "-vframes", "1", "-q:v", "2", str(destination)], check=True, capture_output=True)


def extract_check_frame(video: Path, destination: Path, at_seconds: float = 1.0) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video), "-vframes", "1", "-q:v", "2", str(destination)], check=True, capture_output=True)


def mux_audio(video: Path, audio: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(destination)], check=True, capture_output=True)


def concat_videos(videos: list[Path], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    concat_file = destination.parent / "concat.txt"
    concat_file.write_text("".join(f"file '{path.resolve()}'\n" for path in videos))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(destination)], check=True, capture_output=True)


def pad_audio_to(source: Path, destination: Path, target_duration: float, pad_mode: str = "back") -> None:
    """Pad audio to reach target_duration. pad_mode: none=no padding, front=silence at start, back=silence at end."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    actual = probe_duration(source)
    pad = target_duration - actual
    if pad <= 0 or pad_mode == "none":
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(source), "-c:a", "libmp3lame", "-q:a", "0", str(destination)],
            check=True, capture_output=True,
        )
        return
    if pad_mode == "front":
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={pad}",
             "-i", str(source),
             "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
             "-c:a", "libmp3lame", "-q:a", "0", str(destination)],
            check=True, capture_output=True,
        )
    else:  # back
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(source),
             "-af", f"apad=whole_dur={target_duration}",
             "-c:a", "libmp3lame", "-q:a", "0", str(destination)],
            check=True, capture_output=True,
        )
