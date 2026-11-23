# Engine on AI-written notes: development ward

Run 2026-11-23 with `gpt-5.4-mini`. Held-out ward untouched; final exam not run.

| Notes | Result |
| --- | --- |
| Template notes (clean wording, the easy case) | 75/75 planted gaps caught, 0 false alarms on 125 charts that should stay quiet |
| AI-written notes | 75/75 planted gaps caught, 0 false alarms on 125 charts that should stay quiet |

Charts with AI notes: 200 of 200.

| Test group | Charts | Correct |
| --- | --- | --- |
| confounder (CKD) | 15 | 15 |
| correctly documented | 40 | 40 |
| missing diagnosis | 50 | 50 |
| near-miss | 30 | 30 |
| routine admission | 40 | 40 |
| unsupported diagnosis | 25 | 25 |

## Every mistake, in plain English

None.

## Cost

211 model calls (11 drafts rejected by the leak check and retried),
335,042 tokens in total. Budget caps from wardsight.toml applied to every call.
