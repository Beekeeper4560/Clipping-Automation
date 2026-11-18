"""Settings for the clipping pipeline, loaded from config.yaml with sane defaults."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CaptionConfig:
    enabled: bool = True
    font: str = "DejaVu Sans"
    font_size: int = 86
    words_per_line: int = 3
    uppercase: bool = True
    # ASS colours are &HAABBGGRR
    color: str = "&H00FFFFFF"
    highlight_color: str = "&H0000E5FF"  # yellow
    outline_color: str = "&H00000000"
    outline: int = 6
    # Distance of the caption block from the bottom of the frame, in pixels.
    margin_bottom: int = 520
    hook_overlay: bool = True  # show the clip's hook as a title for the first seconds
    hook_seconds: float = 3.0
    hook_font_size: int = 72


@dataclass
class ClaudeConfig:
    model: str = "claude-opus-5-5"
    effort: str = "high"
    # Server-side refusal fallback; set to false to disable.
    fallbacks: bool = True


@dataclass
class Config:
    output_dir: str = "output"
    work_dir: str = "work"
    whisper_model: str = "small"  # tiny | base | small | medium | large-v3
    whisper_device: str = "auto"  # auto | cpu | cuda
    language: str | None = None  # None = auto-detect
    num_clips: int = 5
    min_clip_seconds: float = 20
    max_clip_seconds: float = 60
    width: int = 1080
    height: int = 1920
    reframe: str = "face"  # face | center | blur
    crf: int = 20
    preset: str = "veryfast"
    loudnorm: bool = True
    # Free-text guidance for picking clips, e.g. "finance podcast, prefer contrarian money takes".
    niche: str = ""
    captions: CaptionConfig = field(default_factory=CaptionConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)


def _merge(obj: Any, data: dict) -> Any:
    known = {f.name: f for f in fields(obj)}
    for key, value in (data or {}).items():
        if key not in known:
            raise ValueError(f"Unknown config key: {key}")
        current = getattr(obj, key)
        if is_dataclass(current) and isinstance(value, dict):
            _merge(current, value)
        else:
            setattr(obj, key, value)
    return obj


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Config:
    cfg = Config()
    if path is None and Path("config.yaml").exists():
        path = "config.yaml"
    if path:
        with open(path) as fh:
            _merge(cfg, yaml.safe_load(fh) or {})
    if overrides:
        _merge(cfg, {k: v for k, v in overrides.items() if v is not None})
    if cfg.reframe not in ("face", "center", "blur"):
        raise ValueError("reframe must be one of: face, center, blur")
    if cfg.min_clip_seconds >= cfg.max_clip_seconds:
        raise ValueError("min_clip_seconds must be smaller than max_clip_seconds")
    return cfg
