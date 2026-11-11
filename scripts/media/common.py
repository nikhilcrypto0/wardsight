"""Shared helpers for WardSight media: fonts, palette, easing, and an ffmpeg frame writer.

Frames are drawn with Pillow and piped straight into ffmpeg as raw RGB, so no
temporary image files are written. Everything is drawn from real WardSight data.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = Path(__file__).resolve().parent / "fonts"
OUT = ROOT / "data" / "media"

W, H, FPS = 1920, 1080, 30

# The web app's palette (Tailwind slate/teal/amber/violet/emerald)
BG = (246, 247, 249)
INK = (20, 24, 31)
MUTED = (100, 116, 139)
LINE = (226, 232, 240)
WHITE = (255, 255, 255)
TEAL = (15, 118, 110)
AMBER_FILL, AMBER_RING, AMBER_INK = (254, 243, 199), (245, 158, 11), (146, 64, 14)
VIOLET_FILL, VIOLET_RING, VIOLET_INK = (237, 233, 254), (139, 92, 246), (91, 33, 182)
GREEN_FILL, GREEN_RING, GREEN_INK = (209, 250, 229), (16, 185, 129), (6, 95, 70)
ORANGE_FILL, ORANGE_RING, ORANGE_INK = (255, 237, 213), (251, 146, 60), (154, 52, 18)
EMPTY_FILL = (236, 240, 244)
ROSE = (190, 18, 60)
BANNER = (254, 243, 199)


@lru_cache(maxsize=64)
def font(size: int, weight: str = "Regular", mono: bool = False) -> ImageFont.FreeTypeFont:
    name = f"GeistMono-{weight}.ttf" if mono else f"Geist-{weight}.ttf"
    return ImageFont.truetype(str(FONTS / name), size)


def ease(t: float) -> float:
    """Smooth in-out curve for 0..1."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def window(t: float, start: float, end: float) -> float:
    """0..1 progress of time t through [start, end]."""
    return 0.0 if t <= start else 1.0 if t >= end else (t - start) / (end - start)


def blend(a: tuple[int, ...], b: tuple[int, ...], k: float) -> tuple[int, ...]:
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def canvas(color: tuple[int, int, int] = BG) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), color)
    return img, ImageDraw.Draw(img)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return [*lines, line] if line else lines


def synthetic_banner(draw: ImageDraw.ImageDraw, alpha: float = 1.0) -> None:
    """The same banner the app shows on every page."""
    fill = blend(BG, BANNER, alpha)
    draw.rectangle([0, 0, W, 44], fill=fill)
    msg = "Synthetic data only. No real patients. Demo, not for clinical use."
    f = font(20)
    draw.text(((W - draw.textlength(msg, font=f)) / 2, 11), msg, font=f, fill=blend(fill, AMBER_INK, alpha))


class VideoWriter:
    """Pipe RGB frames into ffmpeg as H.264 (yuv420p plays everywhere, LinkedIn included)."""

    def __init__(self, path: Path, fps: int = FPS, size: tuple[int, int] = (W, H)) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
             "-movflags", "+faststart", str(path)],
            stdin=subprocess.PIPE)
        self.frames = 0

    def write(self, img: Image.Image) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(img.convert("RGB").tobytes())
        self.frames += 1

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {self.path}")


def to_gif(mp4: Path, gif: Path, width: int = 960, fps: int = 12) -> None:
    """High-quality GIF via a two-pass palette."""
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    f"{vf},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a",
                    str(gif)], check=True)


def save_still(img: Image.Image, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    img.save(path)
    return path
