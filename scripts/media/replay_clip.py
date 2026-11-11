"""Animated ward replay clip (MP4 + GIF) drawn from web/public/replay.json.

    uv run python scripts/media/replay_clip.py      # -> data/media/ward-replay.mp4 / .gif
"""

from __future__ import annotations

import bisect
import json

from common import (
    AMBER_FILL,
    AMBER_INK,
    AMBER_RING,
    EMPTY_FILL,
    FPS,
    GREEN_FILL,
    GREEN_INK,
    GREEN_RING,
    INK,
    LINE,
    MUTED,
    OUT,
    ROOT,
    VIOLET_FILL,
    VIOLET_INK,
    VIOLET_RING,
    WHITE,
    H,
    VideoWriter,
    W,
    blend,
    canvas,
    ease,
    font,
    synthetic_banner,
    to_gif,
    window,
    wrap,
)
from PIL import ImageDraw

SECONDS = 20.0
PLAY_FROM, PLAY_TO = 0.6, 15.6      # seconds over which the whole replay runs; then the summary
FADE_HOURS = 5.0                    # a bed eases into its new colour over this many sim hours
CONDITION = {"aki": "Acute kidney injury", "sepsis": "Sepsis", "hyponatremia": "Hyponatremia",
             "abla": "Acute blood loss anemia", "arf": "Acute hypoxic respiratory failure",
             "hf": "Acute systolic heart failure"}
STATE_STYLE = {
    "stable": (WHITE, LINE, MUTED), "gap": (AMBER_FILL, AMBER_RING, AMBER_INK),
    "with_physician": (VIOLET_FILL, VIOLET_RING, VIOLET_INK), "resolved": (GREEN_FILL, GREEN_RING, GREEN_INK),
    "open": ((226, 232, 240), (100, 116, 139), (51, 65, 85)),  # slate: clearly not amber
}


def clock(hour: float) -> str:
    return f"Day {int(hour // 24) + 1} · {int(hour % 24):02d}:00"


def describe(e: dict) -> str:
    name = CONDITION.get(e.get("condition", ""), "")
    if e["type"] == "flag":
        return (f"{name}: evidence found ({e['evidence']}), not in the notes" if e["kind"] == "missing_dx"
                else f"{name}: documented, but the chart does not support it")
    if e["type"] == "query_sent":
        return f"{name}: query approved and sent to the physician"
    if not e["resolved"]:
        return f"{name}: physician answered “{e['answer']}”. Still open"
    if e["drg_from"] == e["drg_to"]:
        return f"{name}: resolved; record accurate, billing category unchanged"
    return f"{name}: resolved, billing category {e['drg_from']} → {e['drg_to']}"


class Replay:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.events = data["events"]
        self.times = [e["t"] for e in self.events]
        self.stays = data["encounters"]

    def at(self, hour: float) -> dict:
        past = self.events[: bisect.bisect_right(self.times, hour)]
        state: dict[str, tuple[str, float]] = {}
        for e in past:
            kind = {"flag": "gap", "query_sent": "with_physician"}.get(e["type"])
            if e["type"] == "answered":
                kind = "resolved" if e["resolved"] else "open"
            if kind:
                state[e["encounter_id"]] = (kind, e["t"])
        beds = [None] * self.data["beds"]
        for s in self.stays:
            if s["admit"] <= hour < s["discharge"]:
                beds[s["bed"]] = s
        answered = [e for e in past if e["type"] == "answered"]
        return {
            "beds": beds, "state": state,
            "feed": [e for e in past if e["type"] in ("flag", "query_sent", "answered")][-4:][::-1],
            "counts": [sum(b is not None for b in beds), sum(e["type"] == "flag" for e in past),
                       sum(e["type"] == "query_sent" for e in past), sum(e["resolved"] for e in answered),
                       sum(e["resolved"] and e["drg_from"] != e["drg_to"] for e in answered)],
        }


def draw_frame(rep: Replay, hour: float, outro: float) -> ImageDraw.ImageDraw:
    img, d = canvas()
    synthetic_banner(d)
    view = rep.at(hour)
    d.text((80, 78), "Ward replay", font=font(58, "Bold"), fill=INK)
    sub = (f"{len(rep.stays)} synthetic patients · {rep.data['admit_days']} days of admissions "
           f"· {rep.data['beds']}-bed unit · gaps caught while patients are still in bed")
    d.text((82, 150), sub, font=font(24), fill=MUTED)
    clk = clock(hour)
    d.text((W - 80 - d.textlength(clk, font=font(56, "Medium", True)), 80), clk,
           font=font(56, "Medium", True), fill=INK)

    labels = ["Patients in beds", "Gaps caught", "Queries sent", "Resolved", "Billing categories corrected"]
    tones = [INK, AMBER_INK, VIOLET_INK, GREEN_INK, INK]
    x0, bw = 80, (W - 160) / 5
    d.rounded_rectangle([80, 205, W - 80, 320], radius=16, fill=WHITE, outline=LINE, width=2)
    for i, (label, value) in enumerate(zip(labels, view["counts"])):
        x = x0 + i * bw + 28
        if i:
            d.line([x0 + i * bw, 222, x0 + i * bw, 303], fill=LINE, width=2)
        d.text((x, 216), str(value), font=font(54, "Medium", True), fill=tones[i])
        d.text((x, 282), label.upper(), font=font(17, "Medium"), fill=MUTED)

    cols, gap, gx, gy, gw = 8, 12, 80, 350, 1180
    tw = (gw - gap * (cols - 1)) / cols
    th = 72
    for b, stay in enumerate(view["beds"]):
        x = gx + (b % cols) * (tw + gap)
        y = gy + (b // cols) * (th + gap)
        if stay is None:
            d.rounded_rectangle([x, y, x + tw, y + th], radius=10, fill=EMPTY_FILL)
            d.text((x + 12, y + 8), str(b + 1), font=font(16), fill=(190, 198, 210))
            continue
        kind, since = view["state"].get(stay["id"], ("stable", stay["admit"]))
        fill, ring, ink = STATE_STYLE[kind]
        k = ease((hour - since) / FADE_HOURS) if kind != "stable" else 1.0
        d.rounded_rectangle([x, y, x + tw, y + th], radius=10, fill=blend(WHITE, fill, k),
                            outline=blend(LINE, ring, k), width=3 if kind != "stable" else 2)
        d.text((x + 12, y + 8), str(b + 1), font=font(16), fill=blend(MUTED, ink, k))
        d.text((x + 12, y + 36), stay["id"], font=font(22, "Medium", True), fill=blend(INK, ink, k))

    lx, ly = gx, gy + 7 * (th + gap) + 6
    for kind, label in (("stable", "Patient, no gap"), ("gap", "Gap found"), ("with_physician", "Query with physician"),
                        ("resolved", "Resolved"), ("open", "Answered, still open")):
        fill, ring, _ = STATE_STYLE[kind]
        d.rounded_rectangle([lx, ly + 4, lx + 22, ly + 26], radius=5, fill=fill, outline=ring, width=2)
        d.text((lx + 32, ly + 3), label, font=font(20), fill=MUTED)
        lx += 44 + d.textlength(label, font=font(20))

    fx, fy, fw = 1300, 350, W - 80 - 1300
    d.rounded_rectangle([fx, fy, fx + fw, 1040], radius=16, fill=WHITE, outline=LINE, width=2)
    d.text((fx + 28, fy + 24), "LIVE FEED", font=font(18, "SemiBold"), fill=MUTED)
    y = fy + 66
    for e in view["feed"]:
        d.text((fx + 28, y), f"{clock(e['t'])} · {e['encounter_id']}", font=font(17, mono=True), fill=MUTED)
        y += 28
        for line in wrap(d, describe(e), font(22), fw - 56)[:3]:
            d.text((fx + 28, y), line, font=font(22), fill=INK)
            y += 30
        y += 18
    if not view["feed"]:
        d.text((fx + 28, y), "Admissions starting…", font=font(22), fill=MUTED)

    if outro > 0:
        a = ease(outro)
        top = round(H - (H - 335) * a)  # a dark panel rises over the (by now empty) ward
        d.rectangle([0, top, W, H], fill=(15, 23, 42))
        if a > 0.55:
            k = ease((a - 0.55) / 0.45)
            gaps, resolved, corrected = view["counts"][1], view["counts"][3], view["counts"][4]
            lines = [(f"{gaps} gaps caught while patients were still in bed", font(64, "Bold"), WHITE),
                     (f"{resolved} resolved  ·  {corrected} billing categories corrected",
                      font(38, "Medium"), (148, 163, 184)),
                     ("Live demo: wardsight.vercel.app", font(44, "SemiBold"), (94, 234, 212))]
            y = top + 150
            for text, f, colour in lines:
                d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f,
                       fill=blend((15, 23, 42), colour, k))
                y += 130
    return img


def main() -> None:
    rep = Replay(json.loads((ROOT / "web" / "public" / "replay.json").read_text()))
    mp4 = OUT / "ward-replay.mp4"
    writer = VideoWriter(mp4)
    total = int(SECONDS * FPS)
    for i in range(total):
        t = i / FPS
        hour = rep.data["hours"] * window(t, PLAY_FROM, PLAY_TO)
        writer.write(draw_frame(rep, hour, window(t, PLAY_TO + 0.2, SECONDS - 0.4)))
    writer.close()
    to_gif(mp4, OUT / "ward-replay.gif")
    print(f"wrote {mp4} ({total} frames) and ward-replay.gif")


if __name__ == "__main__":
    main()
