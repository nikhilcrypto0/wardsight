# Engine on AI-written notes: development ward

Run 2026-11-23 with `gpt-5.4-mini` in VARIETY mode: each planned diagnosis written as physicians write it (abbreviations, hedging such as 'r/o' or 'likely', typos, other negation forms; all meaning-preserving under the ICD-10-CM coding rules, see notes/variety.py), plus copy-forward and terse style. Held-out ward untouched;
final exam not run.

| Notes | Result |
| --- | --- |
| Template notes (clean wording, the easy case) | 95/95 planted gaps caught, 0 false alarms on 139 charts that should stay quiet |
| AI-written notes | 95/95 planted gaps caught, 0 false alarms on 139 charts that should stay quiet |

Charts with AI notes: 233 of 234. Still on template notes: D0221 (every AI draft was rejected by the note check, or the run stopped at a budget cap).

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

295 model calls: 235 drafts accepted, 60 rejected by the note
check (which compares the planned wording with the note text only, never the engine) and retried.
505,327 tokens in total. Budget caps from wardsight.toml applied to every call.
