"""Turn horizontal footage into 9:16 by following the speaker's face.

The result is a piecewise-constant crop position: the camera holds still while the speaker stays
roughly in frame and jumps (like a cut) when they move or the shot changes. That reads far better
on phones than a constantly drifting pan.
"""
from __future__ import annotations

import statistics


def probe_size(video) -> tuple[int, int]:
    import cv2

    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return w, h


def detect_face_centers(video, start: float, end: float, step: float = 0.5) -> list[tuple[float, float | None]]:
    """Sample frames and return [(t relative to start, face centre x in px or None)]."""
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    samples = []
    t = start
    while t < end:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, None, fx=0.5, fy=0.5)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])  # largest face = likely speaker
            samples.append((t - start, (x + w / 2) * 2))
        else:
            samples.append((t - start, None))
        t += step
    cap.release()
    return samples


def plan_crop(
    samples: list[tuple[float, float | None]],
    src_w: int,
    crop_w: int,
    move_threshold: float = 0.12,
    min_hold: float = 1.5,
) -> list[tuple[float, int]]:
    """Return [(t_start, crop_x)] keyframes. Missing detections hold the previous position."""
    default_x = (src_w - crop_w) // 2
    filled: list[tuple[float, float]] = []
    last = None
    for t, cx in samples:
        last = cx if cx is not None else last
        filled.append((t, last if last is not None else src_w / 2))
    if not filled:
        return [(0.0, default_x)]

    # Median filter to kill single-frame false detections.
    xs = [cx for _, cx in filled]
    smooth = [statistics.median(xs[max(0, i - 2): i + 3]) for i in range(len(xs))]

    def to_crop_x(cx: float) -> int:
        return int(min(max(cx - crop_w / 2, 0), src_w - crop_w))

    keys = [(0.0, to_crop_x(smooth[0]))]
    anchor = smooth[0]
    for (t, _), cx in zip(filled, smooth):
        if abs(cx - anchor) > move_threshold * src_w and t - keys[-1][0] >= min_hold:
            keys.append((t, to_crop_x(cx)))
            anchor = cx
    return keys


def crop_x_expr(keys: list[tuple[float, int]]) -> str:
    """Build an ffmpeg expression for the crop filter's x, evaluated per frame on `t`."""
    expr = str(keys[-1][1])
    for (t_next, _), (_, x) in zip(reversed(keys[1:]), reversed(keys[:-1])):
        expr = f"if(lt(t\\,{t_next:.2f})\\,{x}\\,{expr})"
    return expr


def video_filter(video, start: float, end: float, mode: str, out_w: int, out_h: int) -> str:
    """Return the ffmpeg -vf chain (before captions) that produces an out_w x out_h frame."""
    src_w, src_h = probe_size(video)
    target_ratio = out_w / out_h
    if src_w / src_h <= target_ratio + 0.01:  # already vertical: fit and pad
        return (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )

    if mode == "blur":
        # Full frame in the middle, blurred zoomed copy behind it (good for screen recordings).
        return (
            f"split[a][b];[a]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},gblur=sigma=30[bg];"
            f"[b]scale={out_w}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )

    crop_w = int(src_h * target_ratio) // 2 * 2
    if mode == "face":
        keys = plan_crop(detect_face_centers(video, start, end), src_w, crop_w)
    else:
        keys = [(0.0, (src_w - crop_w) // 2)]
    return f"crop={crop_w}:{src_h}:{crop_x_expr(keys)}:0,scale={out_w}:{out_h},setsar=1"
