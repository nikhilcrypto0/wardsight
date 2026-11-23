# Engine on AI-written notes: development ward

Run 2026-11-23 with `gpt-5.4-mini`. Held-out ward untouched; final exam not run.

| Notes | Result |
| --- | --- |
| Template notes (clean wording, the easy case) | 95/95 planted gaps caught, 0 false alarms on 139 charts that should stay quiet |
| AI-written notes | 95/95 planted gaps caught, 0 false alarms on 139 charts that should stay quiet |

Charts with AI notes: 234 of 234.

| Test group | Charts | Correct |
| --- | --- | --- |
| stated, then resolved | 8 | 8 |
| conflicting notes | 10 | 10 |
| confounder (CKD) | 15 | 15 |
| correctly documented | 40 | 40 |
| missing diagnosis | 50 | 50 |
| near-miss | 30 | 30 |
| routine admission | 40 | 40 |
| not fully specified | 10 | 10 |
| vague, not specific | 6 | 6 |
| unsupported diagnosis | 25 | 25 |

## Every mistake, in plain English

None.

## Cost

258 model calls (18 drafts rejected by the leak check and retried),
416,602 tokens in total. Budget caps from wardsight.toml applied to every call.
