"""Ask Claude to pick the most clip-worthy moments from a timestamped transcript."""
from __future__ import annotations

import json

from .config import Config

SYSTEM_PROMPT = """You are a senior short-form video editor who finds the moments in long videos \
(podcasts, interviews, streams, talks) that will perform as TikTok / Instagram Reels / YouTube Shorts.

A good clip:
- Opens on a hook in its first 1-3 seconds: a bold claim, a question, a surprising number, conflict, \
or an emotional beat. Never start mid-sentence or on filler ("so", "um", "yeah").
- Is self-contained: a viewer with zero context understands it. Include the setup a payoff needs.
- Ends on a payoff, punchline or complete thought, not trailing off.
- Has one clear idea. Prefer story, strong opinion, practical value, humour, or controversy over small talk.

Timestamps in the transcript are in seconds. Choose start/end times that sit on the segment \
boundaries shown, so cuts land between sentences. Clips must not overlap. Score each clip 1-100 \
for viral potential, honestly: not every video has many great moments, so return fewer clips \
rather than padding with weak ones."""

CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number", "description": "Clip start, seconds"},
                    "end": {"type": "number", "description": "Clip end, seconds"},
                    "title": {"type": "string", "description": "Short internal title"},
                    "hook": {"type": "string", "description": "On-screen hook text, max 8 words"},
                    "caption": {"type": "string", "description": "Post caption, 1-2 sentences"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "score": {"type": "integer", "description": "Viral potential 1-100"},
                    "reason": {"type": "string", "description": "Why this moment works"},
                },
                "required": ["start", "end", "title", "hook", "caption", "hashtags", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def format_transcript(segments: list[dict]) -> str:
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)


def build_prompt(segments: list[dict], cfg: Config, title: str) -> str:
    niche = f"\nChannel / niche guidance: {cfg.niche}\n" if cfg.niche else ""
    return (
        f"Video title: {title}\n{niche}\n"
        f"Find up to {cfg.num_clips} clips, each between {cfg.min_clip_seconds:g} and "
        f"{cfg.max_clip_seconds:g} seconds long. Best clips first.\n\n"
        f"<transcript>\n{format_transcript(segments)}\n</transcript>"
    )


def ask_claude(segments: list[dict], cfg: Config, title: str) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic()
    kwargs = {}
    if cfg.claude.fallbacks:
        kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    response = client.beta.messages.create(
        model=cfg.claude.model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": cfg.claude.effort, "format": {"type": "json_schema", "schema": CLIP_SCHEMA}},
        messages=[{"role": "user", "content": build_prompt(segments, cfg, title)}],
        **kwargs,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to select clips: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Clip selection was cut off (max_tokens); lower num_clips and retry.")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["clips"]


def snap_and_validate(clips: list[dict], words: list[dict], cfg: Config, video_duration: float) -> list[dict]:
    """Snap clip edges to word boundaries, enforce length limits and drop overlaps."""
    result: list[dict] = []
    for clip in sorted(clips, key=lambda c: -c.get("score", 0)):
        start, end = float(clip["start"]), float(clip["end"])
        inside = [w for w in words if w["end"] > start and w["start"] < end]
        if inside:
            # Start a hair before the first word, end shortly after the last one.
            start = max(0.0, inside[0]["start"] - 0.15)
            end = min(video_duration, inside[-1]["end"] + 0.35)
        end = min(end, start + cfg.max_clip_seconds)
        if inside and end < inside[-1]["end"]:
            # Trimmed by max length: cut after the last word that still fits.
            fitting = [w for w in inside if w["end"] <= end]
            if fitting:
                end = fitting[-1]["end"] + 0.2
        if end - start < min(cfg.min_clip_seconds, 5):
            continue
        if any(start < r["end"] and end > r["start"] for r in result):
            continue
        result.append({**clip, "start": round(start, 3), "end": round(end, 3)})
        if len(result) >= cfg.num_clips:
            break
    return result
