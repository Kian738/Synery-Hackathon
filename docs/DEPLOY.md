# Deploying Floorwise for free (pitch demo)

One Docker container serves the API and the built web app. HTTPS on the public URL gives phones, VR and the PWA a secure context, so the microphone, gyroscope and "install to home screen" work.

## Ranking (free tiers, no credit card)

| # | Platform | Fit | Caveats |
|---|---|---|---|
| 1 | **Hugging Face Spaces (Docker, CPU Basic)** | Free, no card. 2 vCPU, 16 GB RAM, long-running process, streaming/SSE works, HTTPS `*.hf.space`. Upload ~250 MB of kit data with `hf upload` (large files go through Xet/LFS automatically). | Sleeps after 48 h without traffic; first wake rebuilds/starts in ~1 to 3 min. Public Space = public code (Private also works for free but then visitors need a HF login, so keep it public for the pitch). Disk is ephemeral (walk cache rebuilds after restart). |
| 2 | Render free web service (`render.yaml`) | Free, no card, Docker. | 512 MB RAM (tight for numpy/scipy/shapely + data), sleeps after 15 min idle, ~1 min cold start, 750 h/month. Kit data is gitignored, so a Git build lacks it. |
| 3 | Koyeb free | 1 small instance, Docker. | 512 MB RAM, scales to zero after idle; signup may ask for a card. |
| - | Fly.io, Railway | No longer free without a card (trial credit only). | |
| - | Vercel | Serverless functions: bundle size limit (250 MB unzipped), execution time limits, no long-lived process. Data + scientific Python does not fit. | |
| - | Google Cloud Run | Generous free tier, but billing account (card) required. | |

Sources: huggingface.co/docs/hub/spaces-overview (hardware, sleep), huggingface.co/docs/hub/spaces-sdks-docker (app_port, uid 1000), render.com/docs/free, koyeb.com/pricing, vercel.com/docs/functions/limitations, cloud.google.com/run/pricing. Checked from known 2026 terms; re-check limits on the day.

Sizes: kit data `docs/industrial-agents-hackathon-2026/data` is 214 MB (the kit folder is gitignored, so it is uploaded from your disk, not from Git). Git pack is ~99 MB.

## Recommended: Hugging Face Space (about 5 minutes)

1. Sign up at huggingface.co (no card). Create a **write** token: Settings -> Access Tokens.
2. (Automatic) The script creates the Space (Docker, free CPU, public) and copies these secrets from `.env` into the Space's encrypted secrets, printing names only: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ORS_API_KEY` (and `FLOORWISE_PROVIDER` as a variable). An `ANTHROPIC_API_KEY` that is a Claude CLI token (`sk-ant-usr-`) is skipped because it will not work on a server. Use `-SkipSecrets` to set them by hand instead (Space -> Settings -> Variables and secrets).
3. In PowerShell at the repo root:
   ```powershell
   $env:HF_TOKEN = "<your write token>"
   ./scripts/deploy.ps1 -Space <your-hf-username>/floorwise
   ```
   This uploads the working tree (with kit data) minus `.env`, `.agent-*`, `node_modules`, runs and test output, and writes the Space card (`sdk: docker`, `app_port: 7860`).
4. Watch the build log on the Space page (first build ~5 to 10 min). App: `https://<user>-floorwise.hf.space`. Health: `/healthz` returns `{"ok": true}`.

`.env` is excluded by `.dockerignore` and by the script's exclude list and is gitignored; secrets only live in the Space settings.

## Before the pitch

- Open the URL 10 minutes before, load a building and send one chat message (warms the walk cache and the model client).
- Keep-warm: a free uptime monitor (UptimeRobot, cron-job.org) hitting `https://<user>-floorwise.hf.space/healthz` every 5 to 10 min. Needed on Render (15 min sleep); on HF it prevents the 48 h sleep.
- Rate limits: the Anthropic key's tier limits apply to all viewers; ElevenLabs free tier has a small monthly character quota. If voice fails, the app falls back to browser speech.
- Have the local `uv run fw start --lan` as a backup.

## Runner-up: Render

`render.yaml` is a Blueprint (Docker, free plan, health check `/healthz`, secrets as `sync: false`). Because the kit data is not in Git, either build the image locally and push it to a registry (Render "Deploy an existing image"), or commit the data on a separate deploy branch. Expect cold starts of ~1 min after 15 min idle and possible out-of-memory at 512 MB.

## Local check

No Docker here, so the image was not built locally. Verified instead: uvicorn with `PORT` and `FLOORWISE_WEB_DIST` serves `/` (200), `/healthz` (`{"ok":true}`) and `/api/buildings` (200).
