import json
from types import SimpleNamespace

import pytest

from clipper import captions, reframe, selector
from clipper.config import CaptionConfig, Config, load_config


def words_from(text: str, start: float = 0.0, step: float = 0.5):
    out = []
    for i, w in enumerate(text.split()):
        out.append({"word": w, "start": start + i * step, "end": start + i * step + 0.4})
    return out


def test_plan_crop_holds_then_jumps():
    # Face on the left for 4s, then on the right.
    samples = [(t / 2, 400.0) for t in range(8)] + [(4 + t / 2, 1500.0) for t in range(8)]
    keys = reframe.plan_crop(samples, src_w=1920, crop_w=606)
    assert len(keys) == 2
    assert keys[0] == (0.0, 97)
    assert keys[1][0] == pytest.approx(4.0, abs=1.0)
    assert keys[1][1] == 1500 - 303  # crop centred on the face


def test_plan_crop_without_faces_is_centred():
    keys = reframe.plan_crop([(0.0, None), (0.5, None)], src_w=1920, crop_w=606)
    assert keys == [(0.0, (1920 - 606) // 2)]


def test_crop_expression():
    assert reframe.crop_x_expr([(0.0, 10)]) == "10"
    expr = reframe.crop_x_expr([(0.0, 10), (2.0, 20), (5.0, 30)])
    assert expr == "if(lt(t\\,2.00)\\,10\\,if(lt(t\\,5.00)\\,20\\,30))"


def test_snap_drops_overlaps_and_enforces_lengths():
    cfg = Config(num_clips=3, min_clip_seconds=5, max_clip_seconds=10)
    words = words_from(" ".join(["word"] * 80))  # 0..40s
    clips = [
        {"start": 1.1, "end": 8.0, "score": 90},
        {"start": 5.0, "end": 12.0, "score": 80},  # overlaps the first -> dropped
        {"start": 15.0, "end": 39.0, "score": 70},  # too long -> trimmed to 10s
        {"start": 30.0, "end": 31.0, "score": 60},  # too short -> dropped
    ]
    out = selector.snap_and_validate(clips, words, cfg, video_duration=40)
    assert [c["score"] for c in out] == [90, 70]
    assert out[0]["start"] == pytest.approx(0.85)  # snapped before the first word
    assert out[1]["end"] - out[1]["start"] <= 10.5


def test_chunks_break_on_sentence_end():
    chunks = captions.chunk_words(words_from("hello there. how are you doing"), per_line=3)
    assert [[w["word"] for w in c] for c in chunks] == [["hello", "there."], ["how", "are", "you"], ["doing"]]


def test_ass_highlights_each_word_relative_to_clip():
    ass = captions.build_ass(words_from("one two three", start=10), 10, 12, CaptionConfig(), 1080, 1920, hook="Hi")
    lines = [line for line in ass.splitlines() if line.startswith("Dialogue")]
    assert len(lines) == 4  # hook + one event per word
    assert lines[1].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,Caption")
    assert "{\\c&H0000E5FF\\fscx110\\fscy110}ONE{\\r} TWO THREE" in lines[1]


def test_srt_timestamps():
    srt = captions.build_srt(words_from("a b", start=3661.0), 3600, 3700)
    assert "00:01:01,000 --> 00:01:01,900" in srt


def test_config_overrides(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("num_clips: 2\ncaptions:\n  words_per_line: 4\n")
    cfg = load_config(p, {"reframe": "blur", "language": None})
    assert (cfg.num_clips, cfg.captions.words_per_line, cfg.reframe) == (2, 4, "blur")
    p.write_text("nope: 1\n")
    with pytest.raises(ValueError):
        load_config(p)


def test_ask_claude_request_shape(monkeypatch):
    sent = {}
    result = {"clips": [{"start": 1, "end": 30, "title": "t", "hook": "h", "caption": "c",
                         "hashtags": ["x"], "score": 80, "reason": "r"}]}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn", stop_details=None,
                content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=json.dumps(result))],
            )

    class FakeClient:
        beta = SimpleNamespace(messages=FakeMessages())

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: FakeClient())
    segments = [{"start": 0.0, "end": 5.0, "text": "hello world", "words": []}]
    clips = selector.ask_claude(segments, Config(niche="finance"), "My video")
    assert clips == result["clips"]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["fallbacks"] == "default"
    assert sent["output_config"]["format"]["schema"] == selector.CLIP_SCHEMA
    assert "[0.0-5.0] hello world" in sent["messages"][0]["content"]
    assert "finance" in sent["messages"][0]["content"]
