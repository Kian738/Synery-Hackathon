# One command: create the Hugging Face Docker Space (if missing), copy secrets from .env into the Space's
# encrypted secrets, upload the app + kit data, and let HF build the Dockerfile.
#   $env:HF_TOKEN = "<write token>"; ./scripts/deploy.ps1 -Space <hf-user>/floorwise
# The token is read from $env:HF_TOKEN. Secret values go straight from .env to the HF API and are never printed;
# .env itself is never uploaded.
param(
  [Parameter(Mandatory = $true)][string]$Space,
  [switch]$SkipSecrets
)
$ErrorActionPreference = 'Stop'
if (-not $env:HF_TOKEN) { throw 'Set $env:HF_TOKEN to a Hugging Face write token first (huggingface.co/settings/tokens).' }
$env:FW_ROOT = Split-Path -Parent $PSScriptRoot
$env:FW_SPACE = $Space
$env:FW_SKIP_SECRETS = if ($SkipSecrets) { '1' } else { '' }

$py = @'
import os
from pathlib import Path
from huggingface_hub import HfApi

root, space, token = Path(os.environ["FW_ROOT"]), os.environ["FW_SPACE"], os.environ["HF_TOKEN"]
api = HfApi(token=token)

api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
print(f"Space ready: {space}")

# Secrets: only these names are copied; values are read from .env and never printed.
WANTED = ["ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "GROQ_API_KEY",
          "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ORS_API_KEY", "FLOORWISE_PROVIDER"]
if not os.environ.get("FW_SKIP_SECRETS"):
    env = {}
    env_file = root / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for name in WANTED:
        value = env.get(name) or os.environ.get(name)
        if not value:
            continue
        if name == "ANTHROPIC_API_KEY" and value.startswith("sk-ant-usr-"):
            print(f"  skipped {name}: it is a Claude CLI login token, not an API key (needs sk-ant-api...)")
            continue
        if name == "FLOORWISE_PROVIDER":
            api.add_space_variable(space, name, value)
        else:
            api.add_space_secret(space, name, value)
        print(f"  set {name}")

card = """---
title: Floorwise
emoji: 🧭
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
Floorwise: talk to your building. Indoor navigation agent.
"""
# Mirror .dockerignore so .env and local state never leave this machine.
ignore = [".env", ".env.*", ".git/**", ".agent-*", ".agent-*/**", ".venv/**", "**/__pycache__/**", "**/*.pyc",
          ".pytest_cache/**", ".playwright-mcp/**", ".cache/**", "runs/**", "agent_output/**", "reports/**",
          "research_notes/**", "submissions/**", "SUBMISSION/**", "web/node_modules/**", "web/dist/**",
          "web/test-results/**", "README.md", "**/*.pdf", "**/*.mp4",
          "docs/industrial-agents-hackathon-2026/.git/**", "docs/industrial-agents-hackathon-2026/starter_agent/**"]
print("Uploading app and data (first time ~250 MB, later only changes)...")
api.upload_folder(repo_id=space, repo_type="space", folder_path=str(root), path_in_repo=".",
                  ignore_patterns=ignore, commit_message="Deploy Floorwise")
api.upload_file(repo_id=space, repo_type="space", path_or_fileobj=card.encode("utf-8"), path_in_repo="README.md",
                commit_message="Space card")
slug = space.replace("/", "-").replace("_", "-").lower()
print(f"Done. Build log: https://huggingface.co/spaces/{space}\nApp (after build, ~5-10 min): https://{slug}.hf.space")
'@

$py | uv run --no-project --with "huggingface_hub>=0.30" python -
if ($LASTEXITCODE) { throw 'deploy failed' }
