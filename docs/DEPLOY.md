# Deploying the public demo

Live at **https://wardsight.vercel.app** (Vercel project `wardsight`, account nikhilcrypto0).

The hosted demo is the **full app with no server**: every screen (worklist, chart, live rules check,
physician inbox, utilization review, leadership, audit log, replay) runs in the visitor's browser from
static files in `web/public/demo/`. No Python API, no database, no AI keys, so a visitor can never change
shared data or run up a bill; each visitor's clicks live only in their own browser (reset from the audit
log), and `/api` is not forwarded anywhere.

`uv run wardsight-demo` writes those files by running the real workflow on a copy of the database: for
every query and every answer option it approves, answers and rescans inside a transaction, records the
result and rolls back. `web/app/lib/demo.ts` replays the recorded outcomes. `npm test` (in `web/`) proves
the browser matches the engine: the rules check on 2,250 cases, and the ward totals after every query is
worked.

## How it is set up

- Project linked from `web/` with the Vercel CLI (`web/.vercel/` is gitignored).
- Production environment variable: `NEXT_PUBLIC_WARDSIGHT_MODE=public`.
- Deploys are made from the CLI; the project is not connected to GitHub, so a push does not redeploy.

## Redeploy

```
cd web && vercel deploy --prod
```

## Refreshing the demo data (after any engine or data change)

```
uv run wardsight-scan --split dev
uv run wardsight-replay          # rewrites web/public/replay.json
uv run wardsight-demo            # rewrites web/public/demo/ and web/tests/ fixtures
cd web && npm test               # browser must still match the engine
git add web/public web/tests && git commit -m "chore: refresh demo data" && git push
cd web && vercel deploy --prod
```

## Check after every deploy

- Home page shows the "you are the CDI reviewer" intro and the worklist (75 gaps).
- `/encounters/D0011`: approve the query, then in `/inbox` let the simulated physician reply; the chart
  shows billing category 872 and the audit log has three new rows. Reset from `/audit`.
- `/api/summary` returns 404.
- The synthetic-data banner is visible on every page.
