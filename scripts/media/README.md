# Media

Videos and images for the demo, drawn from real WardSight output. Run from this folder;
everything lands in `data/media/` (gitignored).

| Command | Output |
| --- | --- |
| `uv run --project ../.. python replay_clip.py` | `ward-replay.mp4` + `.gif`: the 14-day ward replay in 20 s |
| `uv run --project ../.. python explainer.py` | `explainer.mp4`: case D0011 from chart to corrected DRG in 37 s (needs `wardsight-factory`, `wardsight-notes --template`) |
| `uv run --project ../.. python video_kit.py cards` | `intro.mp4` (4 s) and `outro.mp4` (6 s) |
| `uv run --project ../.. python video_kit.py stitch rec1.mov rec2.mov -o demo.mp4` | intro + your recordings + outro, all 1920x1080 30 fps |
| `uv run --project ../.. python thumbnail.py` | `thumbnail.jpg` (1280x720) |

To record the app without the Next.js dev badge: `cd web && WARDSIGHT_RECORDING=1 npm run dev`.

`assets/ward-night.jpg` is AI-generated (Higgsfield, Z Image) and shows no real place or person.
Fonts: Geist and Geist Mono (SIL Open Font License, `fonts/OFL.txt`).
