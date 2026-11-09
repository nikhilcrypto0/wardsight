# WardSight — Agent Instructions

> Last verified: 2026-11-08

AI command center for hospital clinical documentation integrity (CDI), running on a fully
synthetic 40-bed ward. Plain code makes clinical calls, an LLM only drafts wording, a human
approves anything that leaves the system. Plan: https://claude.ai/artifact/XVntUk1Y17AmzHjPfSfuaP

## Commands

- `uv sync` — install
- `uv run pytest -q` — all tests (no network, no API calls)
- `uv run ruff check src tests` — lint
- `uv run wardsight-factory` — build the synthetic ward into `data/` (built-in patients)
- `./scripts/get_synthea.sh` then `uv run wardsight-factory --synthea data/synthea/fhir` — Synthea patients
- `uv run wardsight-notes --limit 3` — LLM-written notes, small paid smoke test (needs `.env`)
- `uv run wardsight-notes --template` — plain template notes for every chart (offline, free)
- `uv run wardsight-scan --split dev` — run the detection engine, flags into `ops.flags`
- `uv run wardsight-bench --split dev` — score flags against the answer key
- `uv run wardsight-bench --split heldout --final` — ONCE, at the very end; a rerun is refused
- `uv run wardsight-queries --split dev [--llm --limit 3]` — draft physician queries into `ops.queries`
- `uv run wardsight-api` — HTTP API on :8000 (dev split only)
- `cd web && npm run dev` — web app on :3000 (proxies /api to :8000); `npm run build` + `npx tsc --noEmit` to check
- `web/` is **Next.js 16** with Cache Components: read `web/AGENTS.md` and `web/node_modules/next/dist/docs/`
  before changing it; client views that read URL params need a `Suspense` boundary

## Hard rules

- **Synthetic data only.** Never load real patient data (PHI) into this repo.
- **Engines read only the `ehr` schema.** `truth` (answer key, scenario labels, note specs) is
  for the benchmark and the note writer only. Reading it from detection code invalidates results.
- **`src/wardsight/engine/` must not import `scenarios`, `planter`, `reload` or the note writer,
  and must not read `truth`.** Sharing a published threshold from `criteria.py` is fine; sharing
  generation logic is not. `tests/test_isolation_and_bench.py` enforces this.
- **Never tune rules against the held-out split.** Develop on `dev` only.
- **Every LLM step runs under the token budgets in `wardsight.toml`** and halts on breach.
- **Keys live in this project's `.env`** (gitignored). See `.env.example`.

## Layout

- `src/wardsight/criteria.py` — published clinical thresholds, each with its citation
- `scenarios.py` — hour-by-hour chart generator; `planter.py` — test groups + answer key
- `store.py` — DuckDB (`ehr`, `truth`, `ops` schemas); `fhir_export.py` — FHIR R4 bundles
- `notes/` — LLM note writer with leak check and budget ledger; `template.py` offline stand-in
- `engine/` — `evidence.py` rules, `documentation.py` note reader, `gaps.py` flags, `drg.py` MS-DRG v44
- `bench.py` — scorer (reads `truth`); held-out scored once
- `queries/` — `options.py` code-chosen answers, `lint.py` compliance gate, `draft.py` template +
  OpenAI drafters with retry, `run.py` review queue. The AI writes only the question stem.
- `workflow/` — `actions.py` review/send/answer/addendum/rescan + `ops.audit`; `physician.py` simulated physician
- `api/app.py` — FastAPI; `web/` — Next.js screens (worklist, chart, inbox, audit)
