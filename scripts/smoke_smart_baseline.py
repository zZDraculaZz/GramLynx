"""Local smoke checks for recommended smart baseline profile.

Checks startup, /health and a few safe /clean requests without printing payload text.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request

HOST = "127.0.0.1"
PORT = 8010
HEALTH_URL = f"http://{HOST}:{PORT}/health"
CLEAN_URL = f"http://{HOST}:{PORT}/clean"

SAMPLE_REQUESTS: tuple[dict[str, str], ...] = (
    {"text": "севодня будет встреча", "mode": "smart"},
    {"text": "порусски пишу", "mode": "smart"},
    {"text": "текст без изменений", "mode": "smart"},
)


def _http_json(url: str, payload: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    if payload is None:
        req = request.Request(url, method="GET")
    else:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

    with request.urlopen(req, timeout=5) as resp:  # nosec B310 - local smoke script
        body = resp.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return int(resp.status), parsed


def _wait_for_health(deadline_s: float = 25.0) -> None:
    started = time.monotonic()
    while time.monotonic() - started < deadline_s:
        try:
            status, _ = _http_json(HEALTH_URL)
            if status == 200:
                return
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.4)
            continue
    raise RuntimeError("smoke failed: service did not become healthy in time")


def run_smoke() -> None:
    env = os.environ.copy()
    env.setdefault("GRAMLYNX_CONFIG_YAML", str(Path("config.smart_baseline_staging.yml").resolve()))

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    try:
        _wait_for_health()

        status, _ = _http_json(HEALTH_URL)
        if status != 200:
            raise RuntimeError("smoke failed: /health status is not 200")

        checked = 0
        for payload in SAMPLE_REQUESTS:
            status, body = _http_json(CLEAN_URL, payload)
            if status != 200:
                raise RuntimeError("smoke failed: /clean status is not 200")
            clean_text = body.get("clean_text")
            if not isinstance(clean_text, str):
                raise RuntimeError("smoke failed: /clean response missing clean_text")
            checked += 1

        print(f"smoke ok: health=200, clean_requests={checked}, profile=symspell-v7")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.returncode not in (0, -15):
            err = (proc.stderr.read() or "").strip()
            if err:
                raise RuntimeError("smoke failed: server exited unexpectedly")


if __name__ == "__main__":
    run_smoke()
