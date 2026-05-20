"""Start API + Vite dev server with one command (cross-platform)."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = REPO_ROOT / "web"
API_HOST = os.environ.get("HOST", "127.0.0.1")
API_PORT = int(os.environ.get("PORT", "8000"))
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WEB_PORT", "5173"))
API_URL = f"http://{API_HOST}:{API_PORT}"
WEB_URL = f"http://{WEB_HOST}:{WEB_PORT}"

def _npm_executable() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _stream(prefix: str, pipe: subprocess.PIPE | None) -> None:
    if pipe is None:
        return
    for raw in iter(pipe.readline, b""):
        line = raw.decode(errors="replace").rstrip()
        if line:
            print(f"[{prefix}] {line}", flush=True)
    pipe.close()


def _wait_for_http(url: str, *, timeout: float = 180.0, label: str = "service") -> bool:
    deadline = time.monotonic() + timeout
    last_log = 0.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            now = time.monotonic()
            if now - last_log >= 5.0:
                print(
                    f"[dev] Waiting for {label} at {url} "
                    "(profile/embeddings may take a minute on first run)…",
                    flush=True,
                )
                last_log = now
            time.sleep(0.5)
    return False


def _popen(cmd: list[str], *, cwd: Path | None = None) -> subprocess.Popen[bytes]:
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(
        cmd,
        cwd=cwd or REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            check=False,
            capture_output=True,
        )
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def _preflight() -> None:
    if not (WEB_DIR / "package.json").is_file():
        raise SystemExit(f"Missing {WEB_DIR / 'package.json'}")
    if not (WEB_DIR / "node_modules").is_dir():
        raise SystemExit(
            "Web dependencies not installed. Run:\n"
            "  cd web && npm install\n"
            "or: make web-install"
        )
    if not (REPO_ROOT / ".env").is_file():
        print("Note: no .env file found; using defaults and environment variables.", flush=True)


def run_dev(*, api_only: bool = False) -> int:
    """Launch uvicorn (and optionally Vite). Returns process exit code."""
    _preflight()

    api_proc = _popen([sys.executable, "-m", "vai_agent.cli.run_api"])
    web_proc: subprocess.Popen[bytes] | None = None

    threading.Thread(target=_stream, args=("api", api_proc.stdout), daemon=True).start()

    if not _wait_for_http(f"{API_URL}/health", timeout=180.0, label="API"):
        print(
            f"[dev] API did not respond on {API_URL}/health within 180s. "
            "Check [api] logs (ODBC, profile, embeddings).",
            flush=True,
        )
        _terminate(api_proc)
        return 1

    if not api_only:
        web_cmd = [_npm_executable(), "run", "dev"]
        web_proc = _popen(web_cmd, cwd=WEB_DIR)
        threading.Thread(target=_stream, args=("web", web_proc.stdout), daemon=True).start()

    def shutdown(*_args: object) -> None:
        """Shutdown."""
        if web_proc is not None:
            _terminate(web_proc)
        _terminate(api_proc)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("", flush=True)
    print("SQL Assistant — development", flush=True)
    print(f"  API: {API_URL}", flush=True)
    if api_only:
        print(f"  UI:  {API_URL}/app  (static; run: cd web && npm run build)", flush=True)
    else:
        print(f"  UI:  {WEB_URL}  (hot reload; /api → {API_URL})", flush=True)
    print("  Press Ctrl+C to stop both.", flush=True)
    print("", flush=True)

    if not api_only and not _wait_for_http(f"{WEB_URL}/"):
        print("[dev] Warning: Vite did not respond in time; check [web] logs.", flush=True)

    try:
        while True:
            if api_proc.poll() is not None:
                if web_proc is not None:
                    _terminate(web_proc)
                return api_proc.returncode or 0
            if web_proc is not None and web_proc.poll() is not None:
                _terminate(api_proc)
                return web_proc.returncode or 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        shutdown()
        return 0


def main(argv: list[str] | None = None) -> None:
    """Main."""
    parser = argparse.ArgumentParser(description="Run SQL Assistant API + web dev server")
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start only uvicorn (serves built UI from web/dist at /app)",
    )
    args = parser.parse_args(argv)
    raise SystemExit(run_dev(api_only=args.api_only))


if __name__ == "__main__":
    main()
