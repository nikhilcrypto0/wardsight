"""Video thumbnail (1280x720): AI-made ward background (Higgsfield, Z Image) + the real replay numbers.

The headline numbers come from web/public/replay.json, so the thumbnail matches the demo.

    cd scripts/media && uv run --project ../.. python thumbnail.py   # -> data/media/thumbnail.jpg
"""

from __future__ import annotations

import json
from pathlib import Path

from common import OUT, ROOT, font
from PIL import Image, ImageDraw

TW, TH = 1280, 720
BG = Path(__file__).resolve().parent / "assets" / "ward-night.jpg"


def headline_numbers() -> tuple[int, int]:
    events = json.loads((ROOT / "web" / "public" / "replay.json").read_text())["events"]
    gaps = sum(e["type"] == "flag" for e in events)
    resolved = sum(e["type"] == "answered" and e["resolved"] for e in events)
    return gaps, resolved


def main() -> None:
    gaps, resolved = headline_numbers()
    img = Image.open(BG).convert("RGB").resize((TW, TH), Image.LANCZOS)
    shade = Image.new("L", (TW, 1))
    for x in range(TW):  # dark on the left for the text, clear on the right for the beds
        shade.putpixel((x, 0), int(235 * max(0.0, 1 - x / (TW * 0.62)) ** 1.3))
    img = Image.composite(Image.new("RGB", (TW, TH), (8, 15, 30)), img, shade.resize((TW, TH)))
    d = ImageDraw.Draw(img)

    d.text((64, 70), "WARDSIGHT", font=font(34, "Bold"), fill=(94, 234, 212))
    d.text((60, 120), f"{gaps} gaps", font=font(150, "Bold"), fill=(255, 255, 255))
    d.text((64, 300), "caught while patients", font=font(56, "SemiBold"), fill=(226, 232, 240))
    d.text((64, 366), "are still in bed", font=font(56, "SemiBold"), fill=(226, 232, 240))
    pill = f"{resolved} resolved by a human-approved query"
    d.rounded_rectangle([64, 470, 64 + 40 + d.textlength(pill, font=font(26, "Medium")), 530], radius=12,
                        fill=(15, 118, 110))
    d.text((84, 482), pill, font=font(26, "Medium"), fill=(255, 255, 255))
    d.text((64, 640), "Synthetic data. Demo, not for clinical use.", font=font(22), fill=(148, 163, 184))

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "thumbnail.jpg"
    img.save(out, quality=92)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
