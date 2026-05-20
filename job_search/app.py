# =============================================================================
# app.py — Flask web server for Job Search Automation
# =============================================================================

import json
import logging
import os
import queue
import threading
import uuid
from pathlib import Path

from flask import (
    Flask, Response, jsonify, render_template,
    request, stream_with_context, session
)
from flask_cors import CORS

_pending_questions = {}


# ─── Logging — write to rotating file, NOT stdout ────────────────────────────
from logging.handlers import RotatingFileHandler

LOG_FILE = Path(__file__).parent / "logs" / "jobsearch.log"
LOG_FILE.parent.mkdir(exist_ok=True)

_file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,   # 5 MB per file
    backupCount=5,               # keep last 5 rotated files
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))

logging.root.setLevel(logging.INFO)
logging.root.handlers = []          # remove any default stdout handlers
logging.root.addHandler(_file_handler)

logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("Job Search server starting up")
logger.info(f"Log file: {LOG_FILE}")
logger.info("=" * 60)

app = Flask(__name__)
app.secret_key = "job_search_secret_key_123"
CORS(app)

# ─── Initialize MySQL Database ───────────────────────────────────────────────
from models import (
    init_db, save_jobs_to_db, get_or_create_user,
    create_search_session, get_user_history, get_jobs_for_session,
    update_job_applied_status
)
init_db()


# ─── Upload dir ───────────────────────────────────────────────────────────────
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ─── In-memory job store: job_id → {status, jobs, sheets_url, queue} ─────────
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# =============================================================================
# Routes
# =============================================================================

@app.route("/")
def index():
    """Serve the main frontend page."""
    token_exists = (Path(__file__).parent / "token.json").exists()
    return render_template("index.html", google_authed=token_exists)


@app.route("/auth/google")
def auth_google():
    """
    Trigger Google OAuth in the local browser (local desktop use only).
    Runs OAuth in a worker thread so other Flask routes stay responsive.
    """
    result: dict = {"ok": False, "message": "Authentication timed out."}
    error: list[Exception] = []

    def _run_oauth():
        try:
            from sheets_exporter import _get_gspread_client
            _get_gspread_client()
            result["ok"] = True
            result["message"] = "Google account connected successfully!"
        except Exception as exc:
            error.append(exc)

    worker = threading.Thread(target=_run_oauth, daemon=True)
    worker.start()
    worker.join(timeout=180)

    if worker.is_alive():
        return jsonify({
            "ok": False,
            "message": "Google sign-in is still open in your browser. Complete it, then refresh.",
        }), 504

    if error:
        logger.error("Google auth failed: %s", error[0])
        return jsonify({"ok": False, "message": str(error[0])}), 500

    return jsonify(result)


@app.route("/auth/status")
def auth_status():
    """Check whether a valid Google token exists."""
    token_path = Path(__file__).parent / "token.json"
    return jsonify({"authed": token_path.exists()})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Username required"}), 400
    user = get_or_create_user(username)
    if user:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        
        return jsonify({
            "id": user["id"],
            "username": user["username"],
            "resume": None
        })
    return jsonify({"error": "Database error"}), 500

@app.route("/api/session")
def get_session():
    if "user_id" in session:
        user_id = session["user_id"]
        return jsonify({
            "id": user_id,
            "username": session["username"],
            "resume": None
        })
    return jsonify(None)

@app.route("/api/history")
def history():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_user_history(user_id))

@app.route("/api/history/<job_id>", methods=["DELETE", "POST"])
def delete_history_item(job_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    from models import delete_search_session_db
    success = delete_search_session_db(job_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Session not found or failed to delete"}), 404

@app.route("/api/jobs/<job_id>")
def get_past_jobs(job_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    jobs = get_jobs_for_session(job_id)
    
    from models import get_search_session
    session_data = get_search_session(job_id)
    
    profile_summary = None
    if session_data and session_data.get("search_params"):
        try:
            params = json.loads(session_data["search_params"])
            profile_summary = params.get("profile_summary")
        except Exception:
            pass
            
    return jsonify({
        "jobs": jobs,
        "profile_summary": profile_summary
    })

@app.route("/api/jobs/<int:job_result_id>/apply", methods=["POST"])
def apply_job(job_result_id):
    if not session.get("user_id"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    applied = data.get("applied", True)
    success = update_job_applied_status(job_result_id, applied)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Failed to update"}), 500


@app.route("/search", methods=["POST"])
def start_search():
    """
    Accept a search request and kick off the job search in a background thread.

    Form fields (multipart/form-data):
        resume      — optional PDF file upload
        skills      — comma-separated skills (used if no resume)
        role        — job role / title (used if no resume)
        location    — one of: chennai, remote_india, remote_global, outside_india
        custom_city — city name if location == outside_india
        naukri      — "true" / "false"

    Returns:
        JSON { job_id: "..." } — use this to connect to /stream/<job_id>
    """
    job_id = str(uuid.uuid4())
    progress_q: queue.Queue = queue.Queue()

    # ── Parse form inputs ─────────────────────────────────────────────────────
    location_text = request.form.get("location", "").strip()
    
    # ── Board toggles ────────────────────────────────────────────────────────
    board_toggles = {
        "include_linkedin": request.form.get("linkedin", "true").lower() == "true",
        "include_indeed": request.form.get("indeed", "true").lower() == "true",
        "include_glassdoor": request.form.get("glassdoor", "true").lower() == "true",
        "include_naukri": request.form.get("naukri", "true").lower() == "true",
        "include_naukrigulf": request.form.get("naukrigulf", "true").lower() == "true",
        "include_wellfound": request.form.get("wellfound", "true").lower() == "true",
    }

    if not location_text:
        return jsonify({"error": "Location is required."}), 400

    user_id = session.get("user_id") or 1

    # ── Resume vs manual entry ────────────────────────────────────────────────
    resume_file = request.files.get("resume")
    resume_path = None

    manual_skills = request.form.get("skills", "").strip()
    manual_role   = request.form.get("role", "").strip()

    if not resume_file and not manual_role:
        return jsonify({"error": "Job Role / Title is required when no resume is uploaded."}), 400
    if not resume_file and not manual_skills:
        return jsonify({"error": "Skills are required when no resume is uploaded."}), 400

    if resume_file and resume_file.filename.endswith(".pdf"):
        resume_path = UPLOAD_DIR / f"{job_id}_{resume_file.filename}"
        resume_file.save(str(resume_path))

    experience_str = request.form.get("experience", "1").strip()
    try:
        experience = int(experience_str)
    except ValueError:
        experience = 1

    # ── Register job ─────────────────────────────────────────────────────────
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "jobs": [],
            "sheets_url": None,
            "excel_path": None,
            "queue": progress_q,
            "error": None,
            "cancel": False,
        }

    # ── Launch background thread ──────────────────────────────────────────────
    t = threading.Thread(
        target=_run_search_thread,
        args=(job_id, user_id, resume_path, manual_skills, manual_role,
              location_text, board_toggles, experience, progress_q),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/stop/<job_id>", methods=["POST"])
def stop_search(job_id: str):
    """Signal the background thread to cancel the job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job["cancel"] = True
    return jsonify({"status": "ok"})


@app.route("/stream/<job_id>")
def stream_progress(job_id: str):
    """
    Server-Sent Events endpoint.
    Client connects here to receive live progress messages.

    Events:
        progress  — { message, percent }
        done      — { jobs: [...], sheets_url, excel_path }
        error     — { message }
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job_id"}), 404

    def generate():
        q = job["queue"]
        while True:
            try:
                event = q.get(timeout=120)
            except queue.Empty:
                yield "event: error\ndata: {\"message\": \"Timeout waiting for search results\"}\n\n"
                break

            if event.get("type") == "done":
                data = json.dumps({"jobs": event.get("jobs", []), "sheets_url": event.get("sheets_url"), "excel_path": event.get("excel_path")})
                yield f"event: done\ndata: {data}\n\n"
                break
            elif event.get("type") == "error":
                data = json.dumps({"message": event.get("message")})
                yield f"event: error\ndata: {data}\n\n"
                break
            elif event.get("type") == "cancel":
                data = json.dumps({"message": event.get("message", "Search cancelled.")})
                yield f"event: cancel\ndata: {data}\n\n"
                break
            elif event.get("type") == "question":
                data = json.dumps({"question_id": event.get("question_id"), "question_text": event.get("question_text"), "message": event.get("message"), "percent": event.get("percent")})
                yield f"event: question\ndata: {data}\n\n"
            else:
                data = json.dumps({"message": event.get("message"), "percent": event.get("percent")})
                yield f"event: progress\ndata: {data}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/results/<job_id>")
def get_results(job_id: str):
    """Return stored results for a completed search."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job_id"}), 404
    return jsonify({
        "status": job["status"],
        "jobs": job["jobs"],
        "sheets_url": job["sheets_url"],
        "excel_path": job["excel_path"],
    })


@app.route("/submit_answer", methods=["POST"])
def submit_answer():
    q_id = request.form.get("question_id")
    answer = request.form.get("answer", "")
    if q_id in _pending_questions:
        _pending_questions[q_id]["answer"] = answer
        _pending_questions[q_id]["event"].set()
        return jsonify({"status": "ok"})
    return jsonify({"error": "Question not found or expired"}), 400

# =============================================================================
# Background search worker
# =============================================================================

def _run_search_thread(
    job_id: str,
    user_id: int,
    resume_path,
    manual_skills: str,
    manual_role: str,
    location_text: str,
    board_toggles: dict,
    experience: int,
    progress_q: queue.Queue,
):
    def emit(msg: str, pct: int):
        progress_q.put({"type": "progress", "message": msg, "percent": pct})

    def ask_user(question_text: str) -> str:
        evt = threading.Event()
        q_id = str(uuid.uuid4())
        _pending_questions[q_id] = {"question": question_text, "event": evt, "answer": None}
        progress_q.put({"type": "question", "question_id": q_id, "question_text": question_text, "message": f"Action needed: {question_text}", "percent": 95})
        
        # Block until frontend posts an answer (timeout 5 mins)
        evt.wait(timeout=300)
        
        answer = _pending_questions[q_id].get("answer", "")
        if q_id in _pending_questions:
            del _pending_questions[q_id]
        return answer

    try:
        from resume_parser import parse_resume_with_llm
        from job_searcher import run_job_search
        from exporter import export_to_excel

        def check_cancel() -> bool:
            with _jobs_lock:
                return _jobs.get(job_id, {}).get("cancel", False)

        # ── Build profile ──────────────────────────────────────────────────────
        if resume_path and Path(resume_path).exists():
            emit("Analysing resume with AI…", 3)
            profile = parse_resume_with_llm(str(resume_path))

            # Override suggested titles if user provided a manual role
            if manual_role:
                roles = [r.strip() for r in manual_role.split(",") if r.strip()]
                profile["suggested_titles"] = roles

            # Override skills/search_keywords if user provided manual skills
            if manual_skills:
                skills = [s.strip() for s in manual_skills.split(",") if s.strip()]
                profile["skills"] = skills
                profile["search_keywords"] = skills

            # Use experience from resume if detected, else fall back to form value
            if profile.get("experience_years", 1.5) <= 1.5 and experience > 1:
                profile["experience_years"] = experience

            # If LLM used, emit rich analysis summary
            if profile.get("llm_analysed"):
                past = profile.get("past_roles", [])
                skills_preview = ", ".join(profile.get("skills", [])[:6])
                titles_preview = ", ".join(profile.get("suggested_titles", [])[:3])
                emit(
                    f"🤖 AI Analysis: prev roles — {', '.join(past) if past else 'N/A'} • "
                    f"Skills: {skills_preview} • Searching: {titles_preview}…",
                    5
                )
            else:
                emit(
                    f"Resume parsed (rule-based) — {len(profile.get('skills', []))} skills, "
                    f"searching: {', '.join(profile.get('suggested_titles', [])[:3])}…",
                    5
                )

            # If LLM couldn't determine target role, ask the user
            if profile.get("needs_role_input"):
                user_role = ask_user(
                    "What role are you looking for? (e.g. Data Analyst, Financial Analyst, HR Analyst)"
                )
                if user_role and user_role.strip():
                    role_input = user_role.strip()
                    existing = [t for t in profile["suggested_titles"] if t.lower() != role_input.lower()]
                    profile["suggested_titles"] = [role_input] + existing
                    emit(f"Searching for: {role_input}…", 7)

        elif manual_skills or manual_role:
            emit("Building profile from manual input…", 3)
            skills = [s.strip() for s in manual_skills.split(",") if s.strip()]
            roles = [r.strip() for r in manual_role.split(",") if r.strip()]
            profile = {
                "raw_text": "",
                "skills": skills,
                "search_keywords": skills,
                "suggested_titles": roles,
                "experience_years": experience,
                "past_roles": [],
                "projects": [],
                "llm_analysed": False,
                "summary": "",
                "needs_role_input": False,
            }
            emit(
                f"Manual profile — roles: {manual_role}, "
                f"skills: {manual_skills}, exp: {experience} yrs",
                5
            )
        else:
            raise ValueError("No resume uploaded and no role/skills provided. Cannot run search.")

        profile_summary = {
            "llm_analysed":     profile.get("llm_analysed", False),
            "summary":          profile.get("summary", ""),
            "past_roles":       profile.get("past_roles", []),
            "skills":           profile.get("skills", [])[:12],
            "suggested_titles": profile.get("suggested_titles", [])[:6],
        }

        # ── Search config ──────────────────────────────────────────────────────
        job_titles = profile.get("suggested_titles", [])
        if not job_titles:
            raise ValueError(
                "Could not determine job titles to search. "
                "Please enter a job role/title manually, or upload a resume with a clearer profile."
            )

        search_config = {
            "location_text": location_text,
            "job_titles": job_titles,
            "include_linkedin": board_toggles.get("include_linkedin", True),
            "include_indeed": board_toggles.get("include_indeed", True),
            "include_glassdoor": board_toggles.get("include_glassdoor", True),
            "include_naukri": board_toggles.get("include_naukri", True),
            "include_naukrigulf": board_toggles.get("include_naukrigulf", True),
            "include_wellfound": board_toggles.get("include_wellfound", True),
            "experience": profile.get("experience_years", experience),
            "profile_summary": profile_summary,
        }

        # ── Save Search Session ───────────────────────────────────────────────
        create_search_session(user_id, job_id, json.dumps(search_config))

        # ── Run search ────────────────────────────────────────────────────────
        jobs = run_job_search(search_config, profile, progress_callback=emit, check_cancel=check_cancel)
        
        if check_cancel():
            with _jobs_lock:
                _jobs[job_id]["status"] = "cancelled"
            progress_q.put({"type": "cancel", "message": "Search stopped by user."})
            return

        # ── Auto Apply (All Platforms) ───────────────────────────
        from auto_applier import auto_apply_all
        auto_apply_all(jobs, profile, ask_user, emit, check_cancel)

        # ── Export ─────────────────────────────────────────────────────────────
        emit("Exporting results…", 95)
        result = export_to_excel(jobs, sync_to_sheets=True)

        # ── Save to MySQL ─────────────────────────────────────────────────────
        emit("Saving to MySQL database…", 98)
        save_jobs_to_db(job_id, jobs)

        # ── Serialize jobs for JSON ────────────────────────────────────────────
        serializable = []
        for j in jobs:
            serializable.append({
                "id":          j.get("id"),
                "title":       j.get("title", ""),
                "company":     j.get("company", ""),
                "location":    j.get("location", ""),
                "salary":      j.get("salary_string", "") or "N/A",
                "source":      j.get("source", "").title(),
                "score":       j.get("match_score", 0),
                "grade":       j.get("match_grade", "D"),
                "date_posted": str(j.get("date_posted", "")) or "Today",
                "job_url":     j.get("job_url", ""),
                "description": (j.get("description", "") or "")[:4000],
                "applied_status": j.get("applied_status", False)
            })

        profile_summary = {
            "llm_analysed":     profile.get("llm_analysed", False),
            "summary":          profile.get("summary", ""),
            "past_roles":       profile.get("past_roles", []),
            "skills":           profile.get("skills", [])[:12],
            "suggested_titles": profile.get("suggested_titles", [])[:6],
        }

        with _jobs_lock:
            _jobs[job_id]["jobs"]           = serializable
            _jobs[job_id]["sheets_url"]     = result.get("sheets_url")
            _jobs[job_id]["excel_path"]     = result.get("excel_path")
            _jobs[job_id]["status"]         = "done"
            _jobs[job_id]["profile_summary"]= profile_summary

        emit("All done!", 100)
        progress_q.put({
            "type":           "done",
            "jobs":           serializable,
            "sheets_url":     result.get("sheets_url"),
            "excel_path":     result.get("excel_path"),
            "profile_summary": profile_summary,
        })

    except Exception as exc:
        logger.exception(f"Search thread [{job_id}] failed: {exc}")
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"]  = str(exc)
        progress_q.put({"type": "error", "message": str(exc)})

    finally:
        # Clean up uploaded resume file
        if resume_path and Path(str(resume_path)).exists():
            try:
                Path(str(resume_path)).unlink()
            except Exception:
                pass


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    # use_reloader=False prevents the WinError 10038 socket crash on Windows
    # when running under the VS Code debugger. Manually restart to pick up changes.
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True, use_reloader=False)