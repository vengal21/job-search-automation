"""Single entry point for opening the complete local Gogoi workflow."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SERVER_SCRIPT = ROOT / "src" / "job_dashboard.py"
HOST = "127.0.0.1"
BASE_PORT = 8765
APP_VERSION = 5
BOT_NAME = "Gogoi"


def dashboard_version(port: int):
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/status", timeout=1) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8")).get("version")
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind((HOST, port))
            return True
        except OSError:
            return False


def wait_for_dashboard(process: subprocess.Popen, port: int, timeout: int = 120) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if dashboard_version(port) == APP_VERSION:
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    if not PYTHON.is_file():
        print(f"Project virtual environment is missing: {PYTHON}")
        return 1

    server_process = None
    port = next((candidate for candidate in range(BASE_PORT, BASE_PORT + 20) if dashboard_version(candidate) == APP_VERSION), None)
    if port is not None:
        print(f"The current job dashboard is already running on port {port}; opening it in your browser.")
    else:
        port = next((candidate for candidate in range(BASE_PORT, BASE_PORT + 20) if port_is_free(candidate)), None)
        if port is None:
            print("No free local dashboard port was found in the range 8765-8784. Stop an old dashboard and try again.")
            return 1
        print(f"Starting {BOT_NAME}...")
        child_env = {**os.environ, "JOB_DASHBOARD_PORT": str(port)}
        server_process = subprocess.Popen(
            [str(PYTHON), "-u", str(SERVER_SCRIPT)],
            cwd=ROOT,
            env=child_env,
        )
        if not wait_for_dashboard(server_process, port):
            if server_process.poll() is None:
                server_process.terminate()
                server_process.wait(timeout=10)
                print("Dashboard startup timed out. Review the server output above.")
            else:
                print(f"Dashboard startup failed (exit code {server_process.returncode}).")
            return 1

    base_url = f"http://{HOST}:{port}/"
    print(f"{BOT_NAME} is ready: {base_url}")
    print("Search listings, prepare selected forms in visible Chrome, then review and submit each application yourself.")
    webbrowser.open(base_url)

    if server_process is not None:
        try:
            return server_process.wait()
        except KeyboardInterrupt:
            print("Stopping the dashboard server...")
            server_process.terminate()
            try:
                return server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_process.kill()
                return server_process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
