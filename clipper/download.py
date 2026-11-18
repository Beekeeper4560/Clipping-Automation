"""Fetch the source video (YouTube, Twitch VODs, podcasts... anything yt-dlp supports) or use a local file."""
from __future__ import annotations

import re
from pathlib import Path


def is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source))


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:max_len].strip("-") or "video"


def fetch(source: str, work_dir: Path, cookies: str | None = None) -> tuple[Path, str]:
    """Return (path to video file, human title)."""
    if not is_url(source):
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        return path, path.stem

    import yt_dlp

    work_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        # Best video up to 1080p + best audio, merged into mp4.
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    if not path.exists():  # merged file may keep a different extension
        matches = sorted(work_dir.glob(f"{info['id']}.*"))
        path = next(p for p in matches if p.suffix in (".mp4", ".mkv", ".webm"))
    return path, info.get("title") or info["id"]
