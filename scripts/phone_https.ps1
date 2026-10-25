<#
  Phone motion sensors (AR, VR, look-around) need a secure context: https, or http://localhost.
  A phone on the same Wi-Fi opens http://<laptop-ip>:8000, which browsers treat as insecure, so the sensors stay off.

  This script gives the app a temporary public https address with a Cloudflare quick tunnel (no account, no install beyond cloudflared).
  The address is random, public while the tunnel runs, and gone when you close it. Do not leave it running with real data.

    powershell -File scripts/phone_https.ps1          # prints the https URL and the QR hint
    powershell -File scripts/phone_https.ps1 -Port 8000

  Other ways, if you cannot use a tunnel:
    Android Chrome only: chrome://flags/#unsafely-treat-insecure-origin-as-secure, add http://<laptop-ip>:8000, relaunch. iOS has no such switch.
    LAN https: mkcert + a local reverse proxy; the phone must trust the mkcert root CA (iOS: Settings > General > About > Certificate Trust).
#>
param([int]$Port = 8000)

$tool = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $tool) {
  Write-Host "cloudflared is not installed. Install once with:  winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
  Write-Host "Then run this script again." -ForegroundColor Yellow
  exit 1
}
try { Invoke-WebRequest "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 3 | Out-Null }
catch { Write-Host "Nothing answers on port $Port. Start the app first:  uv run --env-file .env uvicorn server.app:app --port $Port" -ForegroundColor Yellow; exit 1 }

Write-Host "Starting the tunnel. Open the https://....trycloudflare.com address below on the phone (or scan it as a QR code)." -ForegroundColor Green
& cloudflared tunnel --url "http://127.0.0.1:$Port"
