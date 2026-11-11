"""Animated explainer (~36 s MP4): one real case, D0011, from chart to corrected billing category.

Every value on screen comes from the engine at render time (evidence rule, query drafter,
rules check, simulated physician, DRG grouper), so the video cannot drift from the code.

    cd scripts/media && uv run --project ../.. python explainer.py   # -> data/media/explainer.mp4
"""

from __future__ import annotations

import duckdb
from common import (
    AMBER_FILL,
    AMBER_INK,
    AMBER_RING,
    BG,
    FPS,
    GREEN_FILL,
    GREEN_INK,
    GREEN_RING,
    INK,
    LINE,
    MUTED,
    OUT,
    ROOT,
    TEAL,
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
    window,
    wrap,
)
from PIL import ImageDraw

from wardsight import criteria
from wardsight.engine import evidence
from wardsight.engine.chart import load_charts
from wardsight.engine.gaps import find_flags
from wardsight.queries.draft import make_request, template_stem
from wardsight.queries.lint import lint_query
from wardsight.workflow.physician import rule_based_reply

CASE = "D0011"
DARK = (15, 23, 42)
# (start, end) seconds of each scene; each fades in and out over FADE seconds
SCENES = [(0.0, 4.5), (4.5, 10.5), (10.5, 16.0), (16.0, 21.0), (21.0, 27.5), (27.5, 31.5), (31.5, 37.0)]
FADE = 0.4
RULES_SHOWN = ("No leading wording", "Diagnosis not named in the question", "No billing or payment talk",
               "At least two clinical indicators", "Every number matches the chart")


def case_facts() -> dict:
    con = duckdb.connect(str(ROOT / "data" / "wardsight.duckdb"), read_only=True)
    chart = load_charts(con, encounter_id=CASE)[0]
    flag = next(f for f in find_flags(chart) if f.condition == "sepsis")
    ev = evidence.sepsis(chart)
    req = make_request(CASE, "sepsis", flag.kind, flag.detail, flag.evidence)
    stem = template_stem(req)
    check = lint_query(stem, req.options, req.indicators, "sepsis", flag.kind)
    reply = rule_based_reply(f"{CASE}-sepsis-missing", flag.kind, req.options)
    hp = next(n.text for n in chart.notes if n.note_type == "history_and_physical")
    plan = next(line for line in hp.splitlines() if line.lower().startswith("assessment"))
    return {
        "age": chart.age, "sex": chart.sex, "reason": chart.reason_for_admission, "los": chart.los_days,
        "map": [(t, v) for t, v in chart.series("map") if t <= 48],
        "platelets": chart.series("platelets")[0], "bilirubin": chart.series("bilirubin")[0],
        "indicators": [(i.t_hours, i.text) for i in ev.indicators], "met": ev.met,
        "stem": stem, "options": req.options, "lint_ok": check.ok, "answer": req.options[reply.option_index],
        "comment": reply.comment, "plan": plan,
        "drg_now": (flag.drg_now.drg, flag.drg_now.description),
        "drg_new": (flag.drg_if_resolved.drg, flag.drg_if_resolved.description),
    }


# ---------- drawing helpers ----------

def centered(d: ImageDraw.ImageDraw, y: float, text: str, fnt, fill) -> None:
    d.text(((W - d.textlength(text, font=fnt)) / 2, y), text, font=fnt, fill=fill)


def step_header(d: ImageDraw.ImageDraw, n: int, title: str, sub: str, k: float) -> None:
    d.text((120, 90), f"STEP {n} OF 5", font=font(22, "SemiBold"), fill=blend(BG, TEAL, k))
    d.text((120, 125), title, font=font(60, "Bold"), fill=blend(BG, INK, k))
    d.text((122, 205), sub, font=font(28), fill=blend(BG, MUTED, k))


def card(d: ImageDraw.ImageDraw, box, k: float, fill=WHITE, ring=LINE) -> None:
    d.rounded_rectangle(box, radius=18, fill=blend(BG, fill, k), outline=blend(BG, ring, k), width=2)


def tick(d: ImageDraw.ImageDraw, x: float, y: float, k: float, good: bool = True) -> None:
    ring = GREEN_RING if good else AMBER_RING
    d.ellipse([x, y, x + 34, y + 34], fill=blend(WHITE, ring, k))
    if k > 0.3:
        if good:
            d.line([(x + 9, y + 18), (x + 15, y + 24), (x + 26, y + 11)], fill=WHITE, width=4)
        else:
            d.text((x + 13, y + 1), "!", font=font(26, "Bold"), fill=WHITE)


# ---------- scenes (t = seconds into the scene, k = fade-in/out alpha) ----------

def s_intro(d, f, t, k):
    centered(d, 330, "One patient, start to finish", font(76, "Bold"), blend(BG, INK, k))
    centered(d, 440, f"Patient {CASE}  ·  {f['age']} {f['sex']}  ·  admitted for {f['reason']}",
             font(36), blend(BG, MUTED, k))
    k2 = k * ease((t - 1.2) / 0.8)
    centered(d, 560, "How WardSight catches a missing diagnosis while she is still in bed",
             font(34, "Medium"), blend(BG, TEAL, k2))


def s_chart(d, f, t, k):
    step_header(d, 1, "The chart keeps filling in", "Vitals and labs arrive hour by hour", k)
    x0, y0, cw, ch = 120, 300, 1080, 600
    card(d, [x0, y0, x0 + cw, y0 + ch], k)
    d.text((x0 + 32, y0 + 24), "Mean arterial pressure (mmHg), first 48 hours", font=font(24, "Medium"),
           fill=blend(BG, INK, k))
    px0, py0, pw, ph = x0 + 90, y0 + 90, cw - 140, ch - 170
    lo, hi = 55, 90

    def pt(h, v):
        return px0 + pw * h / 48, py0 + ph * (1 - (v - lo) / (hi - lo))

    thr = pt(0, criteria.SOFA_MAP_MMHG)[1]
    d.line([px0, thr, px0 + pw, thr], fill=blend(WHITE, AMBER_RING, k), width=2)
    d.text((px0 + pw - 230, thr - 34), f"SOFA line: below {criteria.SOFA_MAP_MMHG}", font=font(20),
           fill=blend(WHITE, AMBER_INK, k))
    for v in (60, 70, 80, 90):
        d.text((x0 + 30, pt(0, v)[1] - 12), str(v), font=font(20, mono=True), fill=blend(WHITE, MUTED, k))
    for h in (0, 12, 24, 36, 48):
        d.text((pt(h, lo)[0] - 14, py0 + ph + 14), f"h{h}", font=font(20, mono=True), fill=blend(WHITE, MUTED, k))
    shown = 48 * ease(t / 3.5)
    pts = [pt(h, v) for h, v in f["map"] if h <= shown]
    if len(pts) > 1:
        d.line(pts, fill=blend(WHITE, TEAL, k), width=5, joint="curve")
    for (h, v), (x, y) in zip(f["map"], pts):
        low = v < criteria.SOFA_MAP_MMHG
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=blend(WHITE, AMBER_RING if low else TEAL, k))
        if low and h == 0:
            d.text((x + 14, y + 6), f"{v:g}", font=font(24, "Medium", True), fill=blend(WHITE, AMBER_INK, k))

    labs = [("Platelets", f"{f['platelets'][1]:g} K/uL", f"hour {f['platelets'][0]:g}",
             "normal 150 or more"),
            ("Bilirubin", f"{f['bilirubin'][1]:g} mg/dL", f"hour {f['bilirubin'][0]:g}",
             f"normal below {criteria.SOFA_BILIRUBIN_MG_DL:g}")]
    for i, (name, val, when, ref) in enumerate(labs):
        kk = k * ease((t - 1.5 - i * 0.7) / 0.6)
        y = y0 + i * 310
        card(d, [1260, y, W - 120, y + 290], kk, AMBER_FILL, AMBER_RING)
        d.text((1300, y + 30), name.upper(), font=font(22, "SemiBold"), fill=blend(BG, AMBER_INK, kk))
        d.text((1300, y + 80), val, font=font(64, "Medium", True), fill=blend(BG, INK, kk))
        d.text((1300, y + 180), f"{when}  ·  {ref}", font=font(24), fill=blend(BG, MUTED, kk))


def s_rule(d, f, t, k):
    step_header(d, 2, "Plain code checks Sepsis-3", "A written rule, not an AI guess. It keeps the exact values.", k)
    infection = [txt for _, txt in f["indicators"][:2]]
    organ = [txt for _, txt in f["indicators"][2:]]
    rows = [("Suspected infection", " + ".join(infection) + " (both needed)"),
            ("Organ dysfunction", f"SOFA rise of {len(organ)} points (2 needed)")]
    for i, (title, detail) in enumerate(rows):
        kk = k * ease((t - 0.4 - i * 1.0) / 0.6)
        y = 320 + i * 170
        card(d, [120, y, 1180, y + 140], kk)
        tick(d, 160, y + 50, kk)
        d.text((225, y + 28), title, font=font(36, "SemiBold"), fill=blend(BG, INK, kk))
        d.text((225, y + 80), detail, font=font(26), fill=blend(BG, MUTED, kk))
    for i, txt in enumerate(organ):
        kk = k * ease((t - 1.6 - i * 0.35) / 0.4)
        d.rounded_rectangle([1240, 320 + i * 110, W - 120, 410 + i * 110], radius=14,
                            fill=blend(BG, AMBER_FILL, kk), outline=blend(BG, AMBER_RING, kk), width=2)
        d.text((1275, 345 + i * 110), f"+1   {txt}", font=font(28, "Medium", True), fill=blend(BG, AMBER_INK, kk))
    kk = k * ease((t - 3.2) / 0.6)
    card(d, [120, 700, W - 120, 840], kk, GREEN_FILL, GREEN_RING)
    centered(d, 742, "Criteria met: the evidence supports sepsis" if f["met"] else "Criteria not met",
             font(46, "Bold"), blend(BG, GREEN_INK, kk))


def s_gap(d, f, t, k):
    step_header(d, 3, "But the notes never say it", "The note reader looks for the diagnosis, synonyms and negation included",
                k)
    card(d, [120, 300, 1180, 820], k)
    d.text((160, 330), "HISTORY AND PHYSICAL, DAY 0", font=font(22, "SemiBold"), fill=blend(BG, MUTED, k))
    for i, line in enumerate(wrap(d, f["plan"], font(40, "Medium"), 960)):
        d.text((160, 400 + i * 56), line, font=font(40, "Medium"), fill=blend(BG, INK, k))
    kk = k * ease((t - 1.0) / 0.6)
    d.line([160, 470, 160 + 960 * kk, 470], fill=blend(WHITE, AMBER_RING, kk), width=4)
    d.text((160, 520), "Searched for: sepsis, septic, septicemia…", font=font(28), fill=blend(WHITE, MUTED, kk))
    d.text((160, 570), "Found: nothing", font=font(28, "SemiBold"), fill=blend(WHITE, AMBER_INK, kk))
    kk = k * ease((t - 2.0) / 0.6)
    card(d, [1240, 300, W - 120, 820], kk, AMBER_FILL, AMBER_RING)
    d.text((1280, 340), "GAP RAISED", font=font(24, "SemiBold"), fill=blend(BG, AMBER_INK, kk))
    for i, line in enumerate(wrap(d, "Evidence met, never documented", font(46, "Bold"), 560)):
        d.text((1280, 400 + i * 60), line, font=font(46, "Bold"), fill=blend(BG, INK, kk))
    d.text((1280, 560), f"Raised at hour {max(h for h, _ in f['indicators']):g},", font=font(30), fill=blend(BG, MUTED, kk))
    d.text((1280, 600), f"day 1 of a {f['los']}-day stay", font=font(30), fill=blend(BG, MUTED, kk))


def s_query(d, f, t, k):
    step_header(d, 4, "A compliant question to the physician",
                "Code picks the indicators and the answers. AI or a template writes only the sentence.", k)
    card(d, [120, 300, 1100, 960], k)
    d.text((160, 330), "DRAFT QUERY", font=font(22, "SemiBold"), fill=blend(BG, MUTED, k))
    words = f["stem"].split()
    shown = " ".join(words[: int(len(words) * ease(t / 2.6))])
    y = 380
    for line in wrap(d, shown, font(30), 900):
        d.text((160, y), line, font=font(30), fill=blend(BG, INK, k))
        y += 44
    kk = k * ease((t - 2.6) / 0.5)
    for i, opt in enumerate(f["options"]):
        oy = 700 + i * 60
        d.ellipse([162, oy + 6, 186, oy + 30], outline=blend(WHITE, MUTED, kk), width=2)
        d.text((204, oy), opt, font=font(30), fill=blend(WHITE, INK, kk))
    card(d, [1150, 300, W - 120, 960], k)
    d.text((1190, 330), "RULES CHECK (ACDIS/AHIMA 2022)", font=font(22, "SemiBold"), fill=blend(BG, MUTED, k))
    for i, rule in enumerate(RULES_SHOWN):
        kr = k * ease((t - 3.0 - i * 0.3) / 0.3)
        tick(d, 1190, 395 + i * 80, kr, f["lint_ok"])
        d.text((1245, 397 + i * 80), rule, font=font(27), fill=blend(WHITE, INK, kr))
    kb = k * ease((t - 5.0) / 0.4)
    d.rounded_rectangle([1190, 840, W - 160, 920], radius=14, fill=blend(WHITE, TEAL, kb))
    msg = "Approved by a human reviewer" if t > 5.6 else "Approve and send"
    d.text((1190 + (W - 160 - 1190 - d.textlength(msg, font=font(30, "SemiBold"))) / 2, 860), msg,
           font=font(30, "SemiBold"), fill=blend(WHITE, WHITE, kb))


def s_answer(d, f, t, k):
    step_header(d, 5, "The physician answers", "Simulated physician in this demo. The answer becomes a note addendum.", k)
    card(d, [120, 300, 1180, 820], k, VIOLET_FILL, VIOLET_RING)
    d.text((160, 330), "PHYSICIAN INBOX", font=font(22, "SemiBold"), fill=blend(BG, VIOLET_INK, k))
    for i, opt in enumerate(f["options"]):
        chosen = opt == f["answer"] and t > 0.9
        oy = 400 + i * 70
        d.ellipse([162, oy + 4, 194, oy + 36], outline=blend(VIOLET_FILL, VIOLET_INK, k), width=3,
                  fill=blend(VIOLET_FILL, VIOLET_INK, k) if chosen else None)
        d.text((214, oy), opt, font=font(32, "SemiBold" if chosen else "Regular"), fill=blend(BG, INK, k))
    kk = k * ease((t - 1.4) / 0.5)
    d.text((160, 720), f"“{f['comment']}”", font=font(28), fill=blend(VIOLET_FILL, VIOLET_INK, kk))
    kk = k * ease((t - 2.0) / 0.6)
    card(d, [1240, 300, W - 120, 820], kk)
    d.text((1280, 340), "THEN, AUTOMATICALLY", font=font(22, "SemiBold"), fill=blend(BG, MUTED, kk))
    for i, step in enumerate(("Addendum added to the chart", "Chart rescanned: gap closed", "Every step in the audit log")):
        ks = kk * ease((t - 2.2 - i * 0.35) / 0.4)
        tick(d, 1280, 410 + i * 90, ks)
        d.text((1335, 412 + i * 90), step, font=font(30), fill=blend(WHITE, INK, ks))


def s_outro(d, f, t, k):
    d.rectangle([0, 44, W, H], fill=blend(BG, DARK, k))
    centered(d, 150, "THE RECORD NOW MATCHES THE CARE", font(26, "SemiBold"), blend(DARK, (148, 163, 184), k))
    (a, da), (b, db) = f["drg_now"], f["drg_new"]
    kk = k * ease((t - 0.3) / 0.6)
    for x, code, desc, colour in ((180, a, da, (148, 163, 184)), (1020, b, db, (94, 234, 212))):
        d.text((x, 230), f"DRG {code}", font=font(96, "Medium", True), fill=blend(DARK, colour, kk))
        for i, line in enumerate(wrap(d, desc, font(30), 720)):
            d.text((x, 360 + i * 40), line, font=font(30), fill=blend(DARK, (203, 213, 225), kk))
    d.text((890, 255), "→", font=font(90, "Bold"), fill=blend(DARK, WHITE, kk))
    k2 = k * ease((t - 1.6) / 0.6)
    centered(d, 590, "Plain code decides. AI only drafts wording. A human approves.", font(48, "Bold"),
             blend(DARK, WHITE, k2))
    k3 = k * ease((t - 2.6) / 0.6)
    centered(d, 700, "Synthetic patients only. Demo, not for clinical use.", font(28), blend(DARK, (148, 163, 184), k3))
    centered(d, 800, "wardsight.vercel.app", font(52, "SemiBold"), blend(DARK, (94, 234, 212), k3))


DRAW = [s_intro, s_chart, s_rule, s_gap, s_query, s_answer, s_outro]


def frame(f: dict, t: float):
    img, d = canvas()
    for (start, end), draw in zip(SCENES, DRAW):
        if start <= t < end:
            k = window(t, start, start + FADE)
            if draw is not s_outro:
                k *= 1 - window(t, end - FADE, end)
            draw(d, f, t - start, ease(k))
    synthetic_banner(d)
    return img


def main() -> None:
    f = case_facts()
    mp4 = OUT / "explainer.mp4"
    writer = VideoWriter(mp4)
    total = int(SCENES[-1][1] * FPS)
    for i in range(total):
        writer.write(frame(f, i / FPS))
    writer.close()
    print(f"wrote {mp4} ({total} frames, {total / FPS:.0f} s)")


if __name__ == "__main__":
    main()
