"""End-to-end: source video -> transcript -> AI-picked moments -> captioned vertical clips."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import captions, download, reframe, render, selector, transcribe
from .config import Config


def process(
    source: str,
    cfg: Config,
    clips_file: str | None = None,
    cookies: str | None = None,
    dry_run: bool = False,
) -> Path:
    work = Path(cfg.work_dir)
    print(f"==> Fetching {source}")
    video, title = download.fetch(source, work / "downloads", cookies=cookies)
    slug = download.slugify(title)
    out_dir = Path(cfg.output_dir) / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    total = render.duration(video)
    print(f"    {title} ({total / 60:.1f} min)")

    print(f"==> Transcribing with Whisper '{cfg.whisper_model}' (cached after the first run)")
    segments = transcribe.transcribe(video, work / "transcripts" / f"{slug}.json", cfg)
    words = transcribe.all_words(segments)
    if not words:
        raise RuntimeError("No speech found in the video.")

    if clips_file:
        print(f"==> Using clip timestamps from {clips_file}")
        raw = json.loads(Path(clips_file).read_text())
        raw = raw["clips"] if isinstance(raw, dict) else raw
        for c in raw:
            c.setdefault("title", f"Clip at {c['start']:.0f}s")
            c.setdefault("hook", "")
            c.setdefault("caption", "")
            c.setdefault("hashtags", [])
            c.setdefault("score", 50)
            c.setdefault("reason", "manual")
    else:
        print(f"==> Asking {cfg.claude.model} for the best {cfg.num_clips} moments")
        raw = selector.ask_claude(segments, cfg, title)
    clips = selector.snap_and_validate(raw, words, cfg, total)
    if not clips:
        raise RuntimeError("No usable clips were selected.")

    for i, c in enumerate(clips, 1):
        print(f"    #{i} [{c['start']:.1f}-{c['end']:.1f}s] score {c['score']}: {c['title']}")
    if dry_run:
        (out_dir / "clips.json").write_text(json.dumps(clips, indent=2, ensure_ascii=False))
        print(f"==> Dry run: wrote {out_dir / 'clips.json'}")
        return out_dir

    for i, c in enumerate(clips, 1):
        name = f"clip_{i:02d}_{download.slugify(c['title'], 40)}"
        print(f"==> Rendering {name}.mp4")
        vf = reframe.video_filter(video, c["start"], c["end"], cfg.reframe, cfg.width, cfg.height)
        ass_file = None
        if cfg.captions.enabled:
            ass_file = out_dir / f"{name}.ass"
            ass_file.write_text(
                captions.build_ass(words, c["start"], c["end"], cfg.captions, cfg.width, cfg.height, c.get("hook"))
            )
        render.render_clip(video, c["start"], c["end"], vf, ass_file, out_dir / f"{name}.mp4", cfg)
        (out_dir / f"{name}.srt").write_text(captions.build_srt(words, c["start"], c["end"]))
        if ass_file:
            ass_file.unlink()
        c["file"] = f"{name}.mp4"
        c["duration"] = round(c["end"] - c["start"], 2)

    (out_dir / "clips.json").write_text(json.dumps({"source": source, "title": title, "clips": clips}, indent=2, ensure_ascii=False))
    with open(out_dir / "clips.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "title", "caption", "hashtags", "score", "start", "end", "duration"])
        for c in clips:
            tags = " ".join(t if t.startswith("#") else f"#{t}" for t in c["hashtags"])
            writer.writerow([c["file"], c["title"], c["caption"], tags, c["score"], c["start"], c["end"], c["duration"]])
    print(f"==> Done: {len(clips)} clips in {out_dir}/")
    return out_dir
