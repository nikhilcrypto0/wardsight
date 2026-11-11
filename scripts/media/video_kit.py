"""Video kit: intro and outro cards, plus a stitcher for the final demo video.

    uv run python video_kit.py cards                                 # -> data/media/intro.mp4, outro.mp4
    uv run python video_kit.py stitch rec1.mov rec2.mp4 -o demo.mp4  # intro + clips + outro

Stitching scales every clip to 1920x1080 at 30 fps (letterboxed, never stretched), gives the
cards a silent audio track so the narration in the recordings lines up, and joins them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from common import (
    FPS,
    INK,
    MUTED,
    OUT,
    TEAL,
    H,
    VideoWriter,
    W,
    blend,
    canvas,
    ease,
    font,
    synthetic_banner,
    window,
)

DARK = (15, 23, 42)
INTRO_S, OUTRO_S = 4.0, 6.0
TAGLINE = "Plain code decides. AI only drafts wording. A human approves."


def centered(d, y, text, fnt, fill):
    d.text(((W - d.textlength(text, font=fnt)) / 2, y), text, font=fnt, fill=fill)


def intro_frame(t: float):
    img, d = canvas()
    k1, k2, k3 = (ease(window(t, a, a + 0.7)) for a in (0.2, 0.9, 1.6))
    out = 1 - ease(window(t, INTRO_S - 0.4, INTRO_S))
    bg = img.getpixel((0, 100))
    centered(d, 360, "WardSight", font(140, "Bold"), blend(bg, INK, k1 * out))
    d.rectangle([(W - 160 * k2) / 2, 545, (W + 160 * k2) / 2, 551], fill=blend(bg, TEAL, out))
    centered(d, 590, "Clinical documentation integrity while patients are still in bed",
             font(40, "Medium"), blend(bg, MUTED, k2 * out))
    centered(d, 670, TAGLINE, font(32), blend(bg, TEAL, k3 * out))
    synthetic_banner(d)
    return img


def outro_frame(t: float):
    img, d = canvas(DARK)
    k1, k2, k3 = (ease(window(t, a, a + 0.7)) for a in (0.2, 1.0, 1.8))
    centered(d, 300, "WardSight", font(110, "Bold"), blend(DARK, (255, 255, 255), k1))
    centered(d, 460, TAGLINE, font(40, "Medium"), blend(DARK, (203, 213, 225), k2))
    centered(d, 600, "Live demo   wardsight.vercel.app", font(46, "SemiBold"), blend(DARK, (94, 234, 212), k3))
    centered(d, 680, "Source   github.com/nikhilcrypto0/wardsight", font(40), blend(DARK, (148, 163, 184), k3))
    centered(d, 860, "Synthetic patients only. Demo, not for clinical use.", font(26), blend(DARK, (100, 116, 139), k3))
    return img


def render(name: str, seconds: float, draw) -> Path:
    path = OUT / name
    writer = VideoWriter(path)
    for i in range(int(seconds * FPS)):
        writer.write(draw(i / FPS))
    writer.close()
    return path


def has_audio(path: Path) -> bool:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                            "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return bool(json.loads(probe.stdout).get("streams"))


def stitch(clips: list[Path], out: Path) -> None:
    for c in clips:
        if not c.exists():
            raise SystemExit(f"missing clip: {c}")
    parts = [OUT / "intro.mp4", *clips, OUT / "outro.mp4"]
    if not parts[0].exists() or not parts[-1].exists():
        raise SystemExit("run `video_kit.py cards` first")
    args, filters = [], []
    for i, p in enumerate(parts):
        args += ["-i", str(p)]
        filters.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=white,fps={FPS},format=yuv420p,setsar=1[v{i}]")
    n = len(parts)
    for i, p in enumerate(parts):
        if has_audio(p):
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:  # silent track as long as the clip, so audio and video stay in step
            args += ["-f", "lavfi", "-t", str(probe_seconds(p)), "-i", "anullsrc=r=48000:cl=stereo"]
            filters.append(f"[{n}:a]anull[a{i}]")
            n += 1
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(parts)))
    filters.append(f"{joined}concat=n={len(parts)}:v=1:a=1[v][a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, "-filter_complex", ";".join(filters),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], check=True)


def probe_seconds(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cards")
    st = sub.add_parser("stitch")
    st.add_argument("clips", nargs="+", type=Path)
    st.add_argument("-o", "--out", type=Path, default=OUT / "wardsight-demo.mp4")
    a = ap.parse_args()
    if a.cmd == "cards":
        print(render("intro.mp4", INTRO_S, intro_frame), render("outro.mp4", OUTRO_S, outro_frame))
    else:
        stitch(a.clips, a.out)
        print(f"wrote {a.out} ({probe_seconds(a.out):.1f} s)")


if __name__ == "__main__":
    main()
