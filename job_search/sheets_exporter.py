# =============================================================================
# sheets_exporter.py — Export/sync job results to Google Sheets via OAuth 2.0
# =============================================================================
#
# First run: opens a browser for OAuth consent → saves token.json locally.
# Subsequent runs: silently reuses the saved token (auto-refreshes if expired).
#
# Sheet layout mirrors the Excel export:
#   Row 1  : Title banner
#   Row 2  : Sub-header (run timestamp + count)
#   Row 3  : Column headers (frozen)
#   Row 4+ : Job data, sorted by match_score desc
#
# A second tab "Summary" is also written with grade/source breakdown.
# =============================================================================

import json
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import gspread
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
CREDENTIALS_FILE = _HERE / "credentials.json"
TOKEN_FILE = _HERE / "token.json"

# ─── OAuth Scopes ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",        # full drive access — required to open manually-created sheets
]

# ─── Sheet config ─────────────────────────────────────────────────────────────
SHEET_NAME = "Job Search Results — Automated"

# ─── Target Spreadsheet ID ────────────────────────────────────────────────────
# Extracted from: https://docs.google.com/spreadsheets/d/<ID>/edit
# Always update THIS specific sheet instead of searching by name.
SPREADSHEET_ID = "13vPMUXg8NFvBRUOwlePAJzGFICQhObhDAPt9bjN1Cnk"

# ─── Column headers (must match exporter.py COLUMNS order) ───────────────────
HEADERS = [
    "Match Score", "Grade", "Job Title", "Company",
    "Location", "Salary", "Source", "Posted Date", "Apply Link",
]

# ─── Grade → background color (hex without #) ────────────────────────────────
GRADE_COLORS = {
    "A+": {"red": 0.784, "green": 0.969, "blue": 0.769},   # #C8F7C5
    "A":  {"red": 0.835, "green": 0.961, "blue": 0.890},   # #D5F5E3
    "B":  {"red": 1.000, "green": 0.953, "blue": 0.804},   # #FFF3CD
    "C":  {"red": 1.000, "green": 0.878, "blue": 0.698},   # #FFE0B2
    "D":  {"red": 1.000, "green": 0.804, "blue": 0.824},   # #FFCDD2
}

SOURCE_COLORS = {
    "naukri":    {"red": 0.910, "green": 0.961, "blue": 0.914},
    "linkedin":  {"red": 0.890, "green": 0.949, "blue": 0.992},
    "indeed":    {"red": 1.000, "green": 0.973, "blue": 0.882},
    "glassdoor": {"red": 0.953, "green": 0.898, "blue": 0.961},
    "google":    {"red": 0.988, "green": 0.894, "blue": 0.925},
}


# =============================================================================
# Public API
# =============================================================================

def export_to_sheets(
    jobs: list[dict],
    sheet_name: Optional[str] = None,
) -> str:
    """
    Write job results to Google Sheets.

    Args:
        jobs:       Scored job dicts from job_searcher.run_job_search()
        sheet_name: Optional override for the spreadsheet title

    Returns:
        URL of the Google Spreadsheet
    """
    if not jobs:
        raise ValueError("No jobs to export to Sheets.")

    title = sheet_name or SHEET_NAME

    gc = _get_gspread_client()
    spreadsheet = _get_or_create_spreadsheet(gc, title)

    applied_jobs = [j for j in jobs if j.get("applied_status")]
    not_applied_jobs = [j for j in jobs if not j.get("applied_status")]

    _write_jobs_sheet(spreadsheet, jobs, "Job Results", 0)         # All jobs
    _write_jobs_sheet(spreadsheet, applied_jobs, "Applied Jobs", 1)
    _write_jobs_sheet(spreadsheet, not_applied_jobs, "Not Applied Jobs", 2)
    _write_summary_sheet(spreadsheet, jobs, 3)

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
    logger.info(f"Google Sheet updated: {url}")
    return url


# =============================================================================
# Authentication
# =============================================================================

def _get_gspread_client() -> gspread.Client:
    """
    Authenticate via OAuth 2.0 and return an authorised gspread client.

    First run: opens a local browser for consent.
    Later runs: reuses/refreshes the saved token.json.
    """
    creds = None

    # ── Load saved token ─────────────────────────────────────────────────────
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        # If the saved token was granted under a narrower scope (e.g. drive.file),
        # discard it so we re-authenticate with the full current SCOPES list.
        if creds and creds.scopes and not all(s in creds.scopes for s in SCOPES):
            logger.warning(
                "Saved token has insufficient scopes %s — discarding and re-authenticating.",
                creds.scopes,
            )
            creds = None
            TOKEN_FILE.unlink(missing_ok=True)

    # ── Refresh or re-authenticate ────────────────────────────────────────────
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google token...")
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                logger.warning(
                    "Google token refresh failed (%s). Re-authentication required.",
                    exc,
                )
                creds = None

        if not creds or not creds.valid:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}. "
                    "Place your OAuth 2.0 client credentials file there."
                )
            logger.info("Starting OAuth flow — a browser window will open...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

            # Save token for next time
            TOKEN_FILE.write_text(creds.to_json())
            logger.info(f"Token saved to {TOKEN_FILE}")

    return gspread.Client(auth=creds)


# =============================================================================
# Spreadsheet helpers
# =============================================================================

def _get_or_create_spreadsheet(gc: gspread.Client, title: str) -> gspread.Spreadsheet:
    """
    Open the target spreadsheet by its hardcoded ID.
    Falls back to searching by name, then creating a new sheet, if the ID lookup fails.
    """
    # ── Primary: open by explicit spreadsheet ID (always hits the right sheet) ─
    try:
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        logger.info(f"Opened spreadsheet by ID: {SPREADSHEET_ID} ('{spreadsheet.title}')")
        return spreadsheet
    except gspread.SpreadsheetNotFound:
        logger.warning(
            f"Spreadsheet ID '{SPREADSHEET_ID}' not found — "
            "check that the sheet exists and is shared with this Google account."
        )
    except Exception as exc:
        logger.warning(f"Could not open spreadsheet by ID ({exc}). Falling back to name lookup.")

    # ── Fallback: search by name, then create if still not found ──────────────
    try:
        spreadsheet = gc.open(title)
        logger.info(f"Fallback: opened spreadsheet by name: '{title}'")
        return spreadsheet
    except gspread.SpreadsheetNotFound:
        logger.info(f"Spreadsheet '{title}' not found — creating a new one...")
        spreadsheet = gc.create(title)
        try:
            spreadsheet.share(None, perm_type="anyone", role="reader")
        except Exception as exc:
            logger.warning(
                "Could not set public read access on spreadsheet (export still works): %s",
                exc,
            )
        logger.info(f"Created new spreadsheet: {spreadsheet.id}")
        return spreadsheet


# =============================================================================
# Job Results sheet
# =============================================================================

def _write_jobs_sheet(spreadsheet: gspread.Spreadsheet, jobs: list[dict], sheet_name: str, index: int):
    """Clear and rewrite the jobs worksheet."""
    ws = _ensure_worksheet(spreadsheet, sheet_name, index=index)
    ws.clear()

    if not jobs:
        # Write just the header so the sheet exists but is clearly empty
        ws.update("A1", [[f"🔍 {sheet_name} — No jobs in this category"]])
        return

    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    total = len(jobs)

    # ── Build all rows first (batch write = faster) ──────────────────────────
    rows = []

    # Row 1: Title banner
    rows.append([f"🔍 {sheet_name} — {now_str}"] + [""] * (len(HEADERS) - 1))
    # Row 2: Sub-header
    rows.append(
        [f"Total: {total} jobs  |  Last 24 hours only  |  Sorted by Match Score"]
        + [""] * (len(HEADERS) - 1)
    )
    # Row 3: Column headers
    rows.append(HEADERS)

    # Rows 4+: Data
    for job in jobs:
        rows.append(_job_to_row(job))

    ws.update("A1", rows, value_input_option="USER_ENTERED")

    # ── Formatting (batch requests) ──────────────────────────────────────────
    requests = []

    sheet_id = ws.id
    num_rows = len(rows)
    num_cols = len(HEADERS)

    # Merge title row across all columns
    requests.append(_merge_cells(sheet_id, 0, 1, 0, num_cols))
    # Merge sub-header row
    requests.append(_merge_cells(sheet_id, 1, 2, 0, num_cols))

    # Title row format: dark navy BG, white bold text, centered
    requests.append(_format_range(
        sheet_id, 0, 1, 0, num_cols,
        bg={"red": 0.102, "green": 0.102, "blue": 0.180},      # #1A1A2E
        fg={"red": 1, "green": 1, "blue": 1},
        bold=True, size=14, h_align="CENTER",
    ))
    # Sub-header: slightly lighter navy
    requests.append(_format_range(
        sheet_id, 1, 2, 0, num_cols,
        bg={"red": 0.086, "green": 0.129, "blue": 0.243},      # #16213E
        fg={"red": 1, "green": 1, "blue": 1},
        bold=False, size=10, h_align="CENTER",
    ))
    # Header row: mid navy, white bold, centered
    requests.append(_format_range(
        sheet_id, 2, 3, 0, num_cols,
        bg={"red": 0.176, "green": 0.208, "blue": 0.380},      # #2D3561
        fg={"red": 1, "green": 1, "blue": 1},
        bold=True, size=10, h_align="CENTER",
    ))

    # Data rows: grade-based background tinting
    for i, job in enumerate(jobs):
        row_idx = i + 3  # 0-indexed; rows 0,1,2 are banner/subheader/header
        grade = job.get("match_grade", "D")
        source = job.get("source", "").lower()
        bg_color = SOURCE_COLORS.get(source, GRADE_COLORS.get(grade, {"red": 1, "green": 1, "blue": 1}))
        requests.append(_format_range(
            sheet_id, row_idx, row_idx + 1, 0, num_cols,
            bg=bg_color,
        ))

    # Freeze rows 1-3 (banner + sub + header)
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 3},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Column widths (approximate pixel widths)
    col_widths = [90, 60, 220, 160, 150, 130, 90, 100, 380]
    for ci, px in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": ci,
                    "endIndex": ci + 1,
                },
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Row height for banner rows
    for ri, px in [(0, 36), (1, 24), (2, 26)]:
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": ri,
                    "endIndex": ri + 1,
                },
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Hyperlinks are now baked into _job_to_row() as =HYPERLINK() formulas,
    # so no extra per-cell API calls needed here.
    requests = [r for r in requests if r]
    if requests:
        spreadsheet.batch_update({"requests": requests})
    logger.info(f"Job Results sheet written: {num_rows} rows")


# =============================================================================
# Summary sheet
# =============================================================================

def _write_summary_sheet(spreadsheet: gspread.Spreadsheet, jobs: list[dict], index: int):
    """Clear and rewrite the 'Summary' worksheet."""
    ws = _ensure_worksheet(spreadsheet, "Summary", index=index)
    ws.clear()

    grade_counts = Counter(j.get("match_grade", "D") for j in jobs)
    source_counts = Counter(j.get("source", "unknown") for j in jobs)

    rows = [
        ["📊 Search Summary", ""],
        ["", ""],
        ["Metric", "Count"],
        ["Total Jobs Found", len(jobs)],
        ["A+ Grade (score ≥ 80)", grade_counts.get("A+", 0)],
        ["A  Grade (score 65–79)", grade_counts.get("A", 0)],
        ["B  Grade (score 50–64)", grade_counts.get("B", 0)],
        ["C  Grade (score 35–49)", grade_counts.get("C", 0)],
        ["D  Grade (score < 35)", grade_counts.get("D", 0)],
        ["", ""],
        ["Source", "Count"],
    ]
    for source, count in source_counts.most_common():
        rows.append([source.title(), count])

    ws.update("A1", rows, value_input_option="USER_ENTERED")

    sheet_id = ws.id
    requests = [
        _merge_cells(sheet_id, 0, 1, 0, 2),
        _format_range(
            sheet_id, 0, 1, 0, 2,
            bg={"red": 0.102, "green": 0.102, "blue": 0.180},
            fg={"red": 1, "green": 1, "blue": 1},
            bold=True, size=14, h_align="CENTER",
        ),
        _format_range(
            sheet_id, 2, 3, 0, 2,
            bg={"red": 0.176, "green": 0.208, "blue": 0.380},
            fg={"red": 1, "green": 1, "blue": 1},
            bold=True, size=10, h_align="CENTER",
        ),
    ]
    # Bold the "Source / Count" divider row
    src_row_idx = len(rows) - len(source_counts) - 1
    requests.append(_format_range(sheet_id, src_row_idx, src_row_idx + 1, 0, 2, bold=True))

    requests = [r for r in requests if r]
    if requests:
        spreadsheet.batch_update({"requests": requests})
    logger.info("Summary sheet written.")


# =============================================================================
# Internal helpers
# =============================================================================

def _job_to_row(job: dict) -> list:
    """Convert a job dict to a flat list matching HEADERS order."""
    url = job.get("job_url", "")
    # Emit as HYPERLINK formula so we can batch-write — no extra API calls needed
    apply_cell = f'=HYPERLINK("{url}","Apply →")' if url and url.startswith("http") else (url or "N/A")
    return [
        job.get("match_score", 0),
        job.get("match_grade", "D"),
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("salary_string", "") or "N/A",
        job.get("source", "").title(),
        str(job.get("date_posted", "")) or "Today",
        apply_cell,
    ]


def _ensure_worksheet(
    spreadsheet: gspread.Spreadsheet, title: str, index: int
) -> gspread.Worksheet:
    """Get or create a worksheet with the given title."""
    try:
        ws = spreadsheet.worksheet(title)
        return ws
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=2000, cols=len(HEADERS), index=index)
        return ws


def _merge_cells(sheet_id: int, r1: int, r2: int, c1: int, c2: int) -> dict:
    return {
        "mergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2,
            },
            "mergeType": "MERGE_ALL",
        }
    }


def _format_range(
    sheet_id: int,
    r1: int, r2: int,
    c1: int, c2: int,
    bg: Optional[dict] = None,
    fg: Optional[dict] = None,
    bold: Optional[bool] = None,
    size: Optional[int] = None,
    h_align: Optional[str] = None,
) -> dict:
    """Build a repeatCell request for background / text formatting."""
    cell_format = {}
    if bg is not None:
        cell_format["backgroundColor"] = bg
    text_format = {}
    if fg is not None:
        text_format["foregroundColor"] = fg
    if bold is not None:
        text_format["bold"] = bold
    if size is not None:
        text_format["fontSize"] = size
    if text_format:
        cell_format["textFormat"] = text_format
    if h_align is not None:
        cell_format["horizontalAlignment"] = h_align

    if not cell_format:
        return {}

    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2,
            },
            "cell": {"userEnteredFormat": cell_format},
            "fields": _build_format_fields_mask(cell_format),
        }
    }


def _build_format_fields_mask(cell_format: dict) -> str:
    """Build a valid Google Sheets API field mask (dot-notation for nested fields)."""
    parts: list[str] = []
    for key, value in cell_format.items():
        if key == "textFormat" and isinstance(value, dict):
            for sub_key in value:
                parts.append(f"userEnteredFormat.textFormat.{sub_key}")
        else:
            parts.append(f"userEnteredFormat.{key}")
    return ",".join(parts)