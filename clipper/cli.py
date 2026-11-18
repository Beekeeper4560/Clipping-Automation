"""Command line entry point.

  python -m clipper run <url-or-file>     clip one video
  python -m clipper queue sources.txt     clip every new URL in a list (skips ones already done)
  python -m clipper watch inbox/          keep watching a folder and clip any video dropped into it
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

from .config import load_config
from .pipeline import process

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
STATE_FILE = ".clipper_done.json"


def _load_state(cfg) -> dict:
    path = Path(cfg.work_dir) / STATE_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def _save_state(cfg, state: dict) -> None:
    path = Path(cfg.work_dir) / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _run_one(source: str, cfg, args) -> bool:
    try:
        out = process(source, cfg, clips_file=getattr(args, "clips", None), cookies=args.cookies, dry_run=args.dry_run)
        state = _load_state(cfg)
        state[source] = {"output": str(out), "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        _save_state(cfg, state)
        return True
    except Exception:
        traceback.print_exc()
        print(f"!! Failed: {source}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clipper", description="Turn long videos into captioned vertical shorts.")
    parser.add_argument("--config", help="Path to config.yaml (default: ./config.yaml if present)")
    parser.add_argument("--num-clips", type=int, dest="num_clips")
    parser.add_argument("--reframe", choices=["face", "center", "blur"])
    parser.add_argument("--whisper-model", dest="whisper_model")
    parser.add_argument("--language", help="Force transcription language, e.g. en, hi, es")
    parser.add_argument("--output-dir", dest="output_dir")
    parser.add_argument("--cookies", help="cookies.txt for yt-dlp (needed when YouTube asks to sign in)")
    parser.add_argument("--dry-run", action="store_true", help="Pick clips and write clips.json, but don't render")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Clip a single URL or local file")
    p_run.add_argument("source")
    p_run.add_argument("--clips", help="JSON file with your own [{start, end, ...}] instead of asking Claude")

    p_queue = sub.add_parser("queue", help="Clip every not-yet-processed URL/path in a text file")
    p_queue.add_argument("file")

    p_watch = sub.add_parser("watch", help="Watch a folder and clip new videos dropped into it")
    p_watch.add_argument("folder")
    p_watch.add_argument("--interval", type=int, default=30, help="Seconds between scans")

    args = parser.parse_args(argv)
    cfg = load_config(
        args.config,
        {
            "num_clips": args.num_clips,
            "reframe": args.reframe,
            "whisper_model": args.whisper_model,
            "language": args.language,
            "output_dir": args.output_dir,
        },
    )

    if args.command == "run":
        return 0 if _run_one(args.source, cfg, args) else 1

    if args.command == "queue":
        sources = [
            line.strip() for line in Path(args.file).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        done = _load_state(cfg)
        todo = [s for s in sources if s not in done]
        print(f"{len(todo)} new of {len(sources)} sources")
        failures = sum(not _run_one(s, cfg, args) for s in todo)
        return 1 if failures else 0

    if args.command == "watch":
        folder = Path(args.folder)
        (folder / "done").mkdir(parents=True, exist_ok=True)
        (folder / "failed").mkdir(exist_ok=True)
        print(f"Watching {folder}/ every {args.interval}s. Drop videos (or .txt files of URLs) in. Ctrl+C to stop.")
        sizes: dict[Path, int] = {}
        while True:
            for path in sorted(folder.iterdir()):
                if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS | {".txt"}:
                    continue
                size = path.stat().st_size
                if sizes.get(path) != size:  # still being copied; check again next scan
                    sizes[path] = size
                    continue
                if path.suffix == ".txt":
                    urls = [u.strip() for u in path.read_text().splitlines() if u.strip()]
                    ok = all([_run_one(u, cfg, args) for u in urls])
                else:
                    ok = _run_one(str(path), cfg, args)
                shutil.move(str(path), folder / ("done" if ok else "failed") / path.name)
                sizes.pop(path, None)
            time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
