"""Word-by-word "karaoke" captions (the active word is highlighted) as an ASS subtitle file."""
from __future__ import annotations

from .config import CaptionConfig


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[dict], per_line: int, max_gap: float = 0.8) -> list[list[dict]]:
    """Group words into short on-screen phrases, breaking on pauses and sentence ends."""
    chunks: list[list[dict]] = []
    for w in words:
        if (
            chunks
            and len(chunks[-1]) < per_line
            and w["start"] - chunks[-1][-1]["end"] < max_gap
            and not chunks[-1][-1]["word"].endswith((".", "?", "!"))
        ):
            chunks[-1].append(w)
        else:
            chunks.append([w])
    return chunks


def build_ass(
    words: list[dict],
    clip_start: float,
    clip_end: float,
    cfg: CaptionConfig,
    width: int,
    height: int,
    hook: str | None = None,
) -> str:
    """Words carry absolute timestamps; output times are relative to clip_start."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{cfg.font},{cfg.font_size},{cfg.color},{cfg.color},{cfg.outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{cfg.outline},2,2,60,60,{cfg.margin_bottom},1
Style: Hook,{cfg.font},{cfg.hook_font_size},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if hook and cfg.hook_overlay:
        events.append(f"Dialogue: 1,{_ts(0)},{_ts(cfg.hook_seconds)},Hook,,0,0,0,,{_escape(hook)}")

    clip_words = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
    for chunk in chunk_words(clip_words, cfg.words_per_line):
        for i, active in enumerate(chunk):
            start = active["start"]
            # Hold each word until the next one starts so captions never flicker off mid-phrase.
            end = chunk[i + 1]["start"] if i + 1 < len(chunk) else active["end"] + 0.1
            parts = []
            for w in chunk:
                text = _escape(w["word"].upper() if cfg.uppercase else w["word"])
                if w is active:
                    parts.append(f"{{\\c{cfg.highlight_color}\\fscx110\\fscy110}}{text}{{\\r}}")
                else:
                    parts.append(text)
            events.append(
                f"Dialogue: 0,{_ts(start - clip_start)},{_ts(min(end, clip_end) - clip_start)},"
                f"Caption,,0,0,0,,{' '.join(parts)}"
            )
    return header + "\n".join(events) + "\n"


def build_srt(words: list[dict], clip_start: float, clip_end: float, per_line: int = 6) -> str:
    """Plain SRT, handy for uploading as closed captions."""
    clip_words = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
    out = []
    for i, chunk in enumerate(chunk_words(clip_words, per_line), 1):
        a, b = chunk[0]["start"] - clip_start, chunk[-1]["end"] - clip_start
        out.append(f"{i}\n{_srt_ts(a)} --> {_srt_ts(b)}\n{' '.join(w['word'] for w in chunk)}\n")
    return "\n".join(out)


def _srt_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
