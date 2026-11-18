"""Cut, reframe, caption and encode one clip with ffmpeg."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import Config


def duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def has_audio(video: Path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    return bool(out.strip())


def _filter_path(path: Path) -> str:
    # Escape for use inside an ffmpeg filtergraph argument.
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def render_clip(
    video: Path,
    start: float,
    end: float,
    vf: str,
    ass_file: Path | None,
    out_file: Path,
    cfg: Config,
) -> Path:
    if ass_file is not None:
        vf = f"{vf},ass={_filter_path(ass_file)}"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video),
        "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]",
        "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
        "-pix_fmt", "yuv420p", "-r", "30",
    ]
    if has_audio(video):
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
        if cfg.loudnorm:
            cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]  # platform-friendly loudness
    cmd += ["-movflags", "+faststart", str(out_file)]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    return out_file
