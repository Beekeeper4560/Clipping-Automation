"""Speech-to-text with word-level timestamps (faster-whisper), cached next to the work files."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config


def transcribe(video: Path, cache: Path, cfg: Config) -> list[dict]:
    """Return segments: [{"start", "end", "text", "words": [{"word", "start", "end"}]}]."""
    if cache.exists():
        return json.loads(cache.read_text())

    from faster_whisper import WhisperModel

    device = cfg.whisper_device
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel(cfg.whisper_model, device=device, compute_type=compute_type)
    seg_iter, info = model.transcribe(
        str(video),
        language=cfg.language,
        word_timestamps=True,
        vad_filter=True,
    )
    segments = []
    for seg in seg_iter:
        words = [
            {"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        segments.append(
            {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(), "words": words}
        )
        print(f"  [{seg.start:7.1f}s] {seg.text.strip()[:80]}", flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(segments, ensure_ascii=False, indent=1))
    return segments


def all_words(segments: list[dict]) -> list[dict]:
    return [w for s in segments for w in s["words"]]
