# Hosting Floorwise from your own machine

Floorwise runs on a laptop and is published at `https://goapuccino.us.kg` through a Cloudflare named tunnel. HTTPS gives phones, AR/VR and the PWA a secure context, so the microphone and motion sensors work.

The server needs the kit data (`docs/industrial-agents-hackathon-2026/data`, about 214 MB, not in Git) and the keys in `.env`, so the machine that holds both is the host. The page is up only while the laptop is awake and the two commands below are running.

## One-time setup

```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login                      # opens the browser: pick the zone goapuccino.us.kg
cloudflared tunnel create floorwise           # prints a tunnel id and writes its credentials file
cloudflared tunnel route dns floorwise goapuccino.us.kg   # if it errors, a Worker or old record owns the name: delete it, or add a proxied CNAME @ -> <TUNNEL-ID>.cfargotunnel.com by hand
```

Then create `%USERPROFILE%\.cloudflared\config.yml` (replace `<TUNNEL-ID>` with the id printed above):

```yaml
tunnel: <TUNNEL-ID>
credentials-file: C:\Users\<you>\.cloudflared\<TUNNEL-ID>.json
ingress:
  - hostname: goapuccino.us.kg
    service: http://127.0.0.1:8000
  - service: http_status:404
```

## Every time

```powershell
# terminal 1: the app (build the web once with: cd web; npm run build)
uv run --env-file .env uvicorn server.app:app --host 0.0.0.0 --port 8000
# terminal 2: the tunnel
cloudflared tunnel run floorwise
```

Check `https://goapuccino.us.kg/healthz` returns `{"ok":true}`.

## Notes

- Keep the laptop awake and plugged in (Windows: Settings > Power > Screen and sleep > Never while plugged in). Open the page once before a pitch to warm the route cache.
- Chat needs a working model key. `ANTHROPIC_API_KEY` must be an API key (`sk-ant-api...`); a Claude CLI login token (`sk-ant-usr-...`) does not work on a server. Without one, set `FLOORWISE_PROVIDER=groq` with `GROQ_API_KEY` in `.env` (rate limited, fine for a demo).
- Voice uses `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` from `.env`; if ElevenLabs fails, the browser voice takes over.
- `.env` stays on the laptop. The tunnel only forwards HTTP to port 8000; nothing is uploaded.
- Quick, temporary URL without a domain: `scripts/phone_https.ps1` starts a random `trycloudflare.com` tunnel.
- Anyone with the URL can use the app and spend your model and voice quota. Stop `cloudflared` when you are not presenting.
