# Deploying the public demo

The hosted demo is the **ward replay only**: a static JSON file and the Next.js app in public mode.
No Python API, no database, no AI keys, so a visitor can never change data or run up a bill. The
patient chart, inbox and audit screens show a "runs locally" card instead.

## One-time setup (Vercel)

1. Import `github.com/nikhilcrypto0/wardsight` in Vercel.
2. **Root directory:** `web`
3. **Environment variable:** `NEXT_PUBLIC_WARDSIGHT_MODE=public`
4. **Production branch:** `milestone-1` (or `main` once merged)
5. Deploy. Every push to that branch redeploys.

## Refreshing the replay data

```
uv run wardsight-scan --split dev
uv run wardsight-replay          # rewrites web/public/replay.json
git add web/public/replay.json && git commit -m "chore: refresh replay" && git push
```

## Check before sharing the link

- Home page plays the replay; the menu shows only "Ward replay".
- `/inbox`, `/audit`, `/encounters/D0011` show the "runs locally" card, not an error.
- The synthetic-data banner is visible on every page.
