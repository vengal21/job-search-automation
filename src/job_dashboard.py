"""Launch the private localhost job search, match, and application-tracking dashboard."""
from __future__ import annotations

import json
import atexit
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from job_dashboard_data import OUTPUT, ROOT, make_snapshot
from manual_apply_session import SESSION

atexit.register(SESSION.stop)

DIST = ROOT / "job_dashboard" / "dist"
RUNTIME = {"process": None, "message": "", "exitCode": None, "operation": None, "lock": threading.Lock()}
HOST, PORT = "127.0.0.1", int(os.environ.get("JOB_DASHBOARD_PORT", "8765"))
BOT_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


class SelectionConflict(ValueError):
    """The request was valid, but the selected jobs are no longer applicable."""


def _collection_completion_message(exit_code: int | None) -> str:
    if exit_code != 0:
        return "Job search failed. Previous results were kept; check data_folder/output/dashboard_discovery.log."
    try:
        latest = json.loads((OUTPUT / "latest_search.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "Job search finished. The latest search results are shown."
    stats = latest.get("searchStats", {}) if isinstance(latest, dict) else {}
    if not isinstance(stats, dict) or not isinstance(stats.get("queries"), int):
        return "Job search finished. The latest search results are shown."
    window = {"24h": "last 24 hours", "3d": "past 3 days", "7d": "past 7 days"}.get(latest.get("window"), "any indexed date")
    count = len(latest.get("rows", [])) if isinstance(latest.get("rows"), list) else 0
    message = (
        f"Search finished for {window}: {count} unique jobs from {stats.get('pagesFetched', 0)} result pages "
        f"across {stats['queries']} board/location/role searches. Saved role, location, work-mode, date, and blacklist filters were applied."
    )
    excluded = stats.get("excludedByPreferences", 0)
    if isinstance(excluded, int) and excluded:
        message += f" {excluded} search results were excluded by your saved preference filters."
    incomplete = stats.get("incompleteQueries", 0)
    if isinstance(incomplete, int) and incomplete:
        message += f" Results may be incomplete: {incomplete} searches reached the page limit or had a page error; check dashboard_discovery.log."
    else:
        message += " All result pages reported by the provider were checked; live-board listings may still be missing from its index."
    message += " Search indexes lack reliable structured experience/job-type fields, so only explicitly disallowed title labels are filtered; ambiguous listings stay available for review."
    return message


def _resolve_data_app_script() -> Path:
    configured_path = os.environ.get("DATA_APP_SCRIPT")
    if configured_path:
        script = Path(configured_path).expanduser()
        if script.is_file():
            return script
        raise FileNotFoundError(
            f"DATA_APP_SCRIPT points to a missing file: {script}. "
            "Set it to the installed Data plugin's scripts/data-app.mjs file."
        )

    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    plugin_root = codex_home / "plugins" / "cache" / "openai-curated-remote" / "data-analytics"
    candidates = [path for path in plugin_root.glob("*/scripts/data-app.mjs") if path.is_file()]
    if candidates:
        def version_key(path: Path) -> tuple[int, ...]:
            return tuple(int(part) for part in re.findall(r"\d+", path.parents[1].name))

        return max(candidates, key=version_key)

    raise FileNotFoundError(
        f"The Data plugin build script was not found under {plugin_root}. "
        "Install or reconnect the Data plugin in Codex, then run Gogoi again. "
        "If it is installed in a different location, set DATA_APP_SCRIPT to its full scripts/data-app.mjs path."
    )


def status_payload():
    with RUNTIME["lock"]:
        process = RUNTIME["process"]
        if process is not None and process.poll() is not None:
            RUNTIME["exitCode"] = process.returncode
            RUNTIME["process"] = None
            operation = RUNTIME.get("operation")
            RUNTIME["message"] = (_collection_completion_message(process.returncode) if operation == "collect" else "Operation finished.")
            RUNTIME["operation"] = None
        result = {"version": 5, "running": RUNTIME["process"] is not None, "message": RUNTIME["message"], "exitCode": RUNTIME["exitCode"], "operation": RUNTIME["operation"]}
    result["applicationSession"] = SESSION.payload()
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "PersonalJobDashboard/1.0"

    def log_message(self, fmt, *args):
        print("[dashboard] " + (fmt % args))

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def local_request(self):
        origin = self.headers.get("Origin")
        return not origin or urlparse(origin).netloc in {f"{HOST}:{PORT}", f"localhost:{PORT}"}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/data":
            snapshot = make_snapshot()
            self.send_json(200, {
                "rows": snapshot["queries"]["job_postings"]["rows"],
                "lastSearch": snapshot["lastSearch"],
            })
        elif path == "/api/status":
            self.send_json(200, status_payload())
        else:
            self.serve_file(path)

    def do_POST(self):
        if not self.local_request():
            self.send_json(403, {"error": "Requests must come from this local dashboard"})
            return
        path = urlparse(self.path).path
        if path not in {
            "/api/collect", "/api/validate-selection",
            "/api/prepare-application", "/api/fill-application",
            "/api/application-submitted", "/api/application-skip", "/api/application-stop",
        }:
            self.send_json(404, {"error": "Not found"})
            return
        try:
            if path == "/api/collect":
                length = int(self.headers.get("Content-Length", "0"))
                if length > 10_000:
                    raise ValueError("Request is too large")
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("Invalid search request. Refresh and try again.")
                window = payload.get("window", "any")
                if window not in {"any", "24h", "3d", "7d"}:
                    raise ValueError("Choose a valid posting freshness window.")
                with RUNTIME["lock"]:
                    process = RUNTIME["process"]
                    if process is not None and process.poll() is not None:
                        RUNTIME["exitCode"] = process.returncode
                        RUNTIME["process"] = None
                    if RUNTIME["process"] is not None:
                        raise SelectionConflict("Another dashboard operation is already running. Wait for it to finish first.")
                    OUTPUT.mkdir(parents=True, exist_ok=True)
                    args = [str(BOT_PYTHON), "src/job_discovery.py", "--window", window]
                    if not BOT_PYTHON.is_file():
                        raise OSError(f"Project virtual environment not found: {BOT_PYTHON}")
                    with (OUTPUT / "dashboard_discovery.log").open("a", encoding="utf-8") as log_file:
                        process = subprocess.Popen(args, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                    RUNTIME["process"] = process
                    RUNTIME["operation"] = "collect"
                    RUNTIME["message"] = f"Searching public job listings for the selected posting window ({window})."
                    RUNTIME["exitCode"] = None
                self.send_json(202, status_payload())
                return
            if path in {"/api/validate-selection", "/api/prepare-application"}:
                jobs = self.resolve_selected_jobs()
            if path == "/api/validate-selection":
                self.send_json(200, {"valid": True, "count": len(jobs)})
                return
            if path == "/api/prepare-application":
                if RUNTIME["process"] is not None:
                    raise SelectionConflict("Wait for the current job search to finish before preparing applications.")
                result = SESSION.start(jobs)
                self.send_json(200, result)
                return
            if path == "/api/fill-application":
                result = SESSION.fill_current_page()
                self.send_json(200, result)
                return
            if path == "/api/application-submitted":
                result = SESSION.submitted_and_next()
                self.send_json(200, result)
                return
            if path == "/api/application-skip":
                result = SESSION.skip_and_next()
                self.send_json(200, result)
                return
            if path == "/api/application-stop":
                result = SESSION.stop()
                self.send_json(200, result)
                return
        except SelectionConflict as exc:
            print(f"[dashboard] request conflicted: {exc}", flush=True)
            self.send_json(409, {"error": str(exc)})
        except OSError as exc:
            print(f"[dashboard] request failed: {exc}", flush=True)
            log_name = "dashboard_discovery.log" if path == "/api/collect" else "dashboard_apply.log"
            diagnostic_written = False
            try:
                OUTPUT.mkdir(parents=True, exist_ok=True)
                with (OUTPUT / log_name).open("a", encoding="utf-8") as log_file:
                    log_file.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {path} failed:\n")
                    traceback.print_exception(type(exc), exc, exc.__traceback__, file=log_file)
                diagnostic_written = True
            except OSError as log_exc:
                print(f"[dashboard] could not write diagnostic log: {log_exc}", flush=True)
            operation = "job-board search" if path == "/api/collect" else "Chrome application browser" if path == "/api/prepare-application" else "application workflow"
            details = f"Details were written to {log_name}." if diagnostic_written else "Check the dashboard server console for details."
            self.send_json(503, {"error": f"Could not start the {operation}: {exc}. {details}"})
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[dashboard] request rejected: {exc}", flush=True)
            self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            print(f"[dashboard] request failed: {exc}", flush=True)
            self.send_json(500, {"error": f"The browser workflow failed: {str(exc)[:300]}"})

    def resolve_selected_jobs(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValueError("Request is too large")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("Invalid selection request. Refresh the dashboard and select jobs again.")
        ids = payload.get("ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 200:
            raise ValueError("Select at least one and no more than 200 new jobs before starting the bot.")
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("Invalid job selection. Refresh the dashboard and select jobs again.")
        if len(set(ids)) != len(ids):
            raise ValueError("The selection contains duplicate jobs. Refresh the dashboard and select again.")
        available = {row["id"]: row for row in make_snapshot()["queries"]["job_postings"]["rows"]}
        jobs = [available.get(item) for item in ids]
        if any(job is None for job in jobs):
            raise SelectionConflict("A selected job is no longer in the collected list. Refresh and select it again.")
        if any(job["applicationStatus"] != "New" for job in jobs):
            raise SelectionConflict("Only New jobs are selectable. Processed jobs were removed; refresh and select again.")
        return jobs

    def serve_file(self, raw_path):
        request_path = unquote(raw_path).lstrip("/") or "index.html"
        root = DIST.resolve()
        candidate = (root / request_path).resolve()
        if root not in candidate.parents and candidate != root:
            self.send_json(403, {"error": "Invalid path"})
            return
        if not candidate.is_file():
            candidate = root / "index.html"
        if not candidate.is_file():
            self.send_json(503, {"error": "Dashboard build missing. Restart src/job_dashboard.py to build it."})
            return
        content = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def build_dashboard():
    snapshot = ROOT / "job_dashboard" / "src" / "data.json"
    node = Path(os.environ.get("CODEX_NODE", r"C:\Users\W2632\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"))
    if not node.is_file():
        raise FileNotFoundError(f"The configured Node.js executable was not found: {node}. Set CODEX_NODE to its full path.")
    script = _resolve_data_app_script()
    snapshot.write_text(json.dumps(make_snapshot(), indent=2), encoding="utf-8")
    subprocess.run([str(node), str(script), "build", "--project-dir", str(ROOT / "job_dashboard"), "--separate-data"], cwd=ROOT / "job_dashboard", check=True)


if __name__ == "__main__":
    try:
        build_dashboard()
    except FileNotFoundError as exc:
        print(f"[dashboard] startup failed: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
    url = f"http://{HOST}:{PORT}/"
    print(f"Private job dashboard listening at {url}; open this address in Chrome. Press Ctrl+C to stop.", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
