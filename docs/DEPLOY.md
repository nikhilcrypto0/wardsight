# Deploying the public demo

Live at **https://wardsight.vercel.app** (Vercel project `wardsight`, account nikhilcrypto0).

The hosted demo is the **ward replay only**: a static JSON file and the Next.js app in public mode.
No Python API, no database, no AI keys, so a visitor can never change data or run up a bill. The
patient chart, inbox, utilization review, leadership and audit screens show a "runs locally" card,
and `/api` is not forwarded anywhere.

## How it is set up

- Project linked from `web/` with the Vercel CLI (`web/.vercel/` is gitignored).
- Production environment variable: `NEXT_PUBLIC_WARDSIGHT_MODE=public`.
- Deploys are made from the CLI; the project is not connected to GitHub, so a push does not redeploy.

## Redeploy

```
cd web && vercel deploy --prod
```

## Refreshing the replay data

```
uv run wardsight-scan --split dev
uv run wardsight-replay          # rewrites web/public/replay.json
git add web/public/replay.json && git commit -m "chore: refresh replay" && git push
cd web && vercel deploy --prod
```

## Check after every deploy

- Home page plays the replay; the menu shows only "Ward replay".
- `/inbox`, `/ur`, `/encounters/D0011` show the "runs locally" card, not an error.
- `/api/summary` returns 404.
- The synthetic-data banner is visible on every page.
