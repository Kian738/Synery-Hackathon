"""fw: the one command for this project. Run `uv run fw` to see everything.

  fw doctor                 is everything installed and configured? (keys, data, web build)
  fw start                  build the web app if needed and open it (http://localhost:8000)
  fw dev                    backend + frontend with hot reload (http://localhost:5173)
  fw check                  every offline test and eval gate (free, ~3 min)
  fw submit                 answer the public test set -> submissions/team_floorwise_test.csv
  fw bench B Q OUT          Sunday run: building dir B, questions file Q, answers file OUT (.json/.csv)
  fw chat [B]               talk to a building in the terminal
  fw eval SUITE [args]      one eval suite (routes solver parser e2e e2e_basic robust metamorphic build interaction report)

.env is loaded automatically."""

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from floorwise.paths import DATA, KIT, ROOT

DEFAULT_BUILDING = DATA / "dev" / "proc-factory-dev-003"


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip() and key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip()


def run(command: list[str], cwd: Path = ROOT) -> int:
    print("$", " ".join(command), flush=True)
    return subprocess.call(command, cwd=cwd, shell=os.name == "nt" and command[0] in ("npm", "npx"))


def web_is_stale() -> bool:
    dist = ROOT / "web" / "dist" / "index.html"
    if not dist.exists():
        return True
    built = dist.stat().st_mtime
    return any(p.stat().st_mtime > built for p in (ROOT / "web" / "src").rglob("*") if p.is_file())


def doctor() -> int:
    from floorwise import llm

    ok = True

    def line(good: bool, text: str, fix: str = "") -> None:
        nonlocal ok
        ok &= good
        print(("  ok   " if good else "  FIX  ") + text + (f"\n         -> {fix}" if not good and fix else ""))

    print("floorwise doctor")
    line(sys.version_info >= (3, 12), f"python {sys.version.split()[0]}", "install Python 3.12+")
    line((DATA / "manifest.csv").exists(), f"kit data at {DATA}", "clone the kit into docs/industrial-agents-hackathon-2026 or set FLOORWISE_KIT")
    line(shutil.which("npm") is not None, "node/npm for the web app", "install Node.js 20+")
    line((ROOT / "web" / "node_modules").exists(), "web dependencies installed", "cd web && npm install")
    line(not web_is_stale(), "web app built and current", "fw start builds it")
    status = llm.info()
    line(status.available, f"LLM provider: {status.name} (chat {status.models['chat']}, parser {status.models['parser']})",
         "add ANTHROPIC_API_KEY (or GROQ_API_KEY for testing) to .env")
    print("\nWithout an LLM key everything works except chat and the LLM parts of evals.")
    return 0 if ok else 1


def start() -> int:
    if web_is_stale():
        if not (ROOT / "web" / "node_modules").exists():
            run(["npm", "install"], ROOT / "web")
        if run(["npm", "run", "build"], ROOT / "web"):
            return 1
    webbrowser.open("http://localhost:8000")
    return run([sys.executable, "-m", "uvicorn", "server.app:app", "--port", "8000"])


def dev() -> int:
    backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--port", "8000", "--reload"], cwd=ROOT)
    try:
        webbrowser.open("http://localhost:5173")
        return run(["npm", "run", "dev"], ROOT / "web")
    finally:
        backend.terminate()


def check() -> int:
    code = run([sys.executable, "-m", "pytest", "-q"])
    os.environ["FLOORWISE_OFFLINE"] = "1"
    return code or run([sys.executable, "-m", "eval", "gates"])


def submit() -> int:
    out = ROOT / "submissions" / "team_floorwise_test.csv"
    return run([sys.executable, "-m", "floorwise.cli", str(DATA / "test"), str(out)])


def main() -> None:
    load_env()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    command, rest = args[0], args[1:]
    if command == "doctor":
        sys.exit(doctor())
    if command == "start":
        sys.exit(start())
    if command == "dev":
        sys.exit(dev())
    if command == "check":
        sys.exit(check())
    if command == "submit":
        sys.exit(submit())
    if command == "bench":
        sys.exit(run([sys.executable, "-m", "floorwise.cli", *rest]))
    if command == "chat":
        sys.exit(run([sys.executable, "-m", "floorwise.agent.chat", *(rest or [str(DEFAULT_BUILDING)])]))
    if command == "eval":
        sys.exit(run([sys.executable, "-m", "eval", *rest]))
    print(f"unknown command '{command}'\n{__doc__}")
    sys.exit(2)


if __name__ == "__main__":
    main()
