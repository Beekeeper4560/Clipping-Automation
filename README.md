# Clipping Automation

Turn long videos (podcasts, interviews, streams, talks) into ready-to-post vertical shorts for
TikTok, Instagram Reels and YouTube Shorts, with as little manual work as possible.

```
 URL / file ──► download ──► transcribe ──► AI picks moments ──► reframe 9:16 ──► captions ──► clips + captions.csv
              (yt-dlp)   (Whisper, word    (Claude: hook,       (follows the     (word-by-word
                          timestamps)       payoff, score)       speaker's face)  highlight)
```

For each video you get, in `output/<video-name>/`:

| File | What it is |
|---|---|
| `clip_01_<title>.mp4` … | 1080×1920, 30 fps, H.264, loudness-normalised, captions burned in |
| `clip_01_<title>.srt` … | plain captions, if you'd rather upload them as closed captions |
| `clips.csv` | title, post caption, hashtags and viral score per clip, ready to paste or bulk-import into a scheduler |
| `clips.json` | the same plus timestamps and why Claude picked each moment |

## 1. Setup (once)

You need **Python 3.10+** and **ffmpeg**.

```bash
# macOS
brew install ffmpeg python
# Ubuntu / Debian
sudo apt install ffmpeg python3-pip
# Windows: winget install ffmpeg Python.Python.3.12

git clone https://github.com/beekeeper4560/Clipping-Automation.git
cd Clipping-Automation
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Get an API key at <https://console.anthropic.com> and set it:

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
```

The first run downloads the Whisper speech model (`small` is about 500 MB) and caches it.

## 2. Clip a video

```bash
python -m clipper run "https://www.youtube.com/watch?v=VIDEO_ID"
python -m clipper run my_podcast.mp4                    # local files work too
python -m clipper --num-clips 8 --reframe blur run URL  # 8 clips, blurred-background layout
python -m clipper --dry-run run URL                     # just show what Claude would pick
```

Already know your timestamps? Skip the AI step:

```bash
echo '[{"start": 312, "end": 350, "title": "Best story", "hook": "He almost quit"}]' > picks.json
python -m clipper run URL --clips picks.json
```

Transcripts are cached in `work/transcripts/`, so re-running a video (with different settings or
clip counts) skips straight to the AI and render steps.

## 3. Automate it

Pick whichever fits how you work:

**A. A list of videos.** Add URLs to `sources.txt` (one per line), then run:

```bash
python -m clipper queue sources.txt
```

Videos that were already clipped are skipped, so you can keep appending and re-running, for
example from cron: `0 */6 * * * cd /path/to/Clipping-Automation && .venv/bin/python -m clipper queue sources.txt`.

**B. A drop folder.** Leave this running and drop video files (or `.txt` files of URLs) into `inbox/`:

```bash
python -m clipper watch inbox/
```

Processed files move to `inbox/done/` (or `inbox/failed/`). Point Google Drive or Dropbox sync
at that folder and you can queue videos from your phone.

**C. GitHub Actions (no computer needed).** The workflow in `.github/workflows/clip.yml` runs
everything on GitHub's servers:

1. Repo → **Settings → Secrets and variables → Actions** → add `ANTHROPIC_API_KEY`.
2. Repo → **Actions → Clip videos → Run workflow**, paste a URL.
3. When it finishes, download the `clips-N` artifact from the run page.

To make it fully hands-off, uncomment the `schedule:` block in the workflow: every 6 hours it
clips any new lines in `sources.txt`. GitHub's free runners are CPU-only, so long videos are
slow with `small`; use `base` for speed, or run locally on a GPU for `medium`/`large-v3`.

> YouTube often blocks downloads from cloud servers ("Sign in to confirm you're not a bot").
> If that happens, export your YouTube cookies with a "Get cookies.txt" browser extension and
> save the file's contents as a `YT_COOKIES` repo secret (locally: `--cookies cookies.txt`).

## 4. Posting

`clips.csv` has the caption and hashtags for every clip. Upload the MP4s with your scheduler of
choice (Meta Business Suite for Instagram/Facebook, TikTok's web scheduler, YouTube Studio, or
Buffer / Metricool / Later for all at once). Fully automatic posting through the platform APIs
needs a business/creator account and app review on each platform, so it isn't wired in here.

## Tuning

All settings live in [`config.yaml`](config.yaml), with comments. The ones that matter most:

- **`niche`**: one line about your page (e.g. *"fitness podcast clips; prefer myth-busting and
  specific advice"*). This is the biggest lever on clip quality.
- **`reframe`**: `face` for talking heads, `blur` for gameplay, screen recordings and slides.
- **`min/max_clip_seconds`**: 20–60 s is the sweet spot for most platforms.
- **`captions`**: font, size, words per line, highlight colour, and the hook title overlay.
  Install a bolder font (e.g. Montserrat ExtraBold) and set `captions.font` for the classic look.

Claude (`claude-opus-5-5`) reads the whole timestamped transcript and returns clips with a hook,
caption, hashtags and a 1–100 score. A 1-hour podcast is roughly 15k input tokens per run.

> Only clip content you own or have permission to use (e.g. creator clipping programs).

## Project layout

```
clipper/
  cli.py         run / queue / watch commands
  pipeline.py    the end-to-end flow
  download.py    yt-dlp download
  transcribe.py  faster-whisper with word timestamps
  selector.py    Claude prompt + structured output, snapping to word boundaries
  reframe.py     face-tracking 9:16 crop (or centre / blurred background)
  captions.py    word-by-word highlighted ASS captions and SRT
  render.py      ffmpeg cut + encode
tests/           unit tests: python -m pytest
```
