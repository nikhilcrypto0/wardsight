# WardSight — Agent Instructions

> Last verified: 2026-11-05

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

## Hard rules

- **Synthetic data only.** Never load real patient data (PHI) into this repo.
- **Engines read only the `ehr` schema.** `truth` (answer key, scenario labels, note specs) is
  for the benchmark and the note writer only. Reading it from detection code invalidates results.
- **Detection rules (milestone 2) must not import `scenarios.py` or `planter.py`.** Sharing a
  published threshold from `criteria.py` is fine; sharing generation logic is not.
- **Every LLM step runs under the token budgets in `wardsight.toml`** and halts on breach.
- **Keys live in this project's `.env`** (gitignored). See `.env.example`.

## Layout

- `src/wardsight/criteria.py` — published clinical thresholds, each with its citation
- `scenarios.py` — hour-by-hour chart generator; `planter.py` — test groups + answer key
- `store.py` — DuckDB (`ehr`, `truth`, `ops` schemas); `fhir_export.py` — FHIR R4 bundles
- `notes/` — LLM note writer with leak check and budget ledger
