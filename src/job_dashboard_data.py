"""Build a privacy-safe dashboard snapshot from locally collected job data."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from .job_result_details import UNKNOWN_COMPANY, UNKNOWN_LOCATION, extract_company, extract_location
except ImportError:
    from job_result_details import UNKNOWN_COMPANY, UNKNOWN_LOCATION, extract_company, extract_location

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data_folder" / "output"
DATA = ROOT / "job_dashboard" / "src" / "data.json"


def canonical_link(link: str) -> str:
    parts = urlsplit((link or "").strip())
    tracking = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid"}
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not key.casefold().startswith("utm_") and key.casefold() not in tracking]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query, doseq=True), ""))


def make_snapshot() -> dict:
    # data.json is the all-time deduplication history; only the latest completed
    # search is eligible for the actionable dashboard list.
    rows = []
    latest_path = OUTPUT / "latest_search.json"
    last_search = None
    if latest_path.is_file():
        try:
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            if isinstance(latest, dict) and isinstance(latest.get("rows"), list):
                rows = latest["rows"]
                last_search = {
                    "searchedAt": str(latest.get("searchedAt", "")),
                    "window": str(latest.get("window", "any")),
                    "count": len(rows),
                    "engine": str(latest.get("engine", "")),
                    "errors": latest.get("errors", []) if isinstance(latest.get("errors"), list) else [],
                }
        except (json.JSONDecodeError, OSError):
            # Keep the prior readable snapshot if the latest-search file is damaged.
            pass
    pref_path = ROOT / "data_folder" / "work_preferences.yaml"
    try:
        import yaml
        prefs = yaml.safe_load(pref_path.read_text(encoding="utf-8")) or {}
    except Exception:
        prefs = {}
    target_roles = [str(x).strip() for x in prefs.get("positions", []) if str(x).strip()]
    role_phrases = list(dict.fromkeys(target_roles + [
        "Business Analyst", "Data Analyst", "BI Analyst", "MIS Analyst",
        "Product Analyst", "Reporting Analyst", "Operations Analyst", "RPA Developer",
        "Power BI Developer", "Project Analyst",
    ]))
    skill_phrases = ["Power BI", "SQL", "MySQL", "Python", "Selenium", "RPA", "ETL", "DAX", "Forecasting", "Business Analysis", "Excel", "dashboard", "reporting"]

    # Keep the newest record for each canonical URL, while retaining the duplicate count.
    grouped = {}
    for row in rows if isinstance(rows, list) else []:
        link = canonical_link(str(row.get("link", "")))
        if not link or not urlsplit(link).scheme in {"http", "https"}:
            continue
        prior = grouped.get(link)
        timestamp = str(row.get("timestamp", ""))
        if prior is None or timestamp >= prior.get("timestamp", ""):
            grouped[link] = {**row, "_duplicateCount": (prior or {}).get("_duplicateCount", 0) + 1}
        else:
            prior["_duplicateCount"] = prior.get("_duplicateCount", 1) + 1

    outcomes = {}
    for name, status in (("success.json", "Applied"), ("review.json", "Ready for review"), ("failed.json", "Failed"), ("skipped.json", "Skipped")):
        path = OUTPUT / name
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            items = []
        for item in items if isinstance(items, list) else []:
            key = canonical_link(str(item.get("link", "")))
            if key:
                outcomes[key] = status

    enriched = []
    for link, row in grouped.items():
        title = str(row.get("title", "")).strip()
        company = str(row.get("company", "")).strip()
        company, company_evidence = extract_company(
            title,
            str(row.get("snippet", "")),
            str(row.get("link", "")),
            "" if not company or company.casefold() in {UNKNOWN_COMPANY.casefold(), "unknown company"} or re.fullmatch(r"[0-9a-f-]{28,}", company, re.I) else company,
        )
        location = str(row.get("location", "")).strip()
        location_evidence = str(row.get("locationEvidence", "")).strip()
        if not location or location.casefold() in {UNKNOWN_LOCATION.casefold(), "unknown location"}:
            location, location_evidence = extract_location(title, str(row.get("snippet", "")))
        lower = title.casefold()
        evidence_text = f"{title} {row.get('snippet', '')}".casefold()
        matched_role = next((r for r in role_phrases if r.casefold() in lower), None)
        snippet_role = next((r for r in role_phrases if r.casefold() in evidence_text), None)
        matched_skill = next((s for s in skill_phrases if s.casefold() in evidence_text), None)
        if matched_role:
            band, reason = "Strong title match", f"Title includes target role: {matched_role}"
        elif snippet_role:
            band, reason = "Possible title match", f"Search-result snippet mentions target role: {snippet_role}"
        elif matched_skill:
            band, reason = "Possible title match", f"Title or search-result snippet mentions profile skill: {matched_skill}"
        else:
            band, reason = "Limited title evidence", "Title alone does not show a clear match"
        status = outcomes.get(link, "New")
        enriched.append({
            "id": link,
            "title": title or "Untitled listing",
            "company": company,
            "companyEvidence": str(row.get("companyEvidence", "")).strip() or company_evidence,
            "location": location or UNKNOWN_LOCATION,
            "locationEvidence": location_evidence,
            "priorityArea": str(row.get("priorityArea", "Not classified")),
            "link": link,
            "source": str(row.get("source", "Search result")),
            "snippet": str(row.get("snippet", "")),
            "companyType": str(row.get("companyType", "Unclassified")),
            "companyPriority": int(row.get("companyPriority", 20 + int(row.get("locationPriority", 99)))),
            "fitBand": band,
            "fitReason": reason,
            "applicationStatus": status,
            "duplicateCount": row.get("_duplicateCount", 1),
            "timestamp": str(row.get("timestamp", "")),
            "firstSeenAt": str(row.get("firstSeenAt", row.get("timestamp", ""))),
            "lastSeenAt": str(row.get("lastSeenAt", row.get("timestamp", ""))),
            "lastSearchWindow": str(row.get("lastSearchWindow", "any")),
            "newFinding": bool(row.get("newFinding", False)),
            "descriptionAvailable": bool(str(row.get("description", "")).strip()),
            "locationPriority": int(row.get("locationPriority", 99)),
            "matchedResumeKeywords": row.get("matchedResumeKeywords", []),
            "searchWindows": row.get("searchWindows", [row.get("searchWindow", "any")]),
        })
    enriched.sort(key=lambda r: (r["companyPriority"], {"Strong title match": 0, "Possible title match": 1, "Limited title evidence": 2}[r["fitBand"]], r["company"].casefold(), r["title"].casefold()))
    summary = Counter(row["fitBand"] for row in enriched)
    for row in enriched:
        summary[f"status:{row['applicationStatus']}"] += 1
    return {
        "id": "personal-job-fit-dashboard",
        "surface": "dashboard",
        "buildStatus": "complete",
        "title": "Job fit and application dashboard",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lastSearch": last_search,
        "status": "reviewed",
        "filters": [],
        "queries": {
            "job_postings": {
                "rows": enriched,
                "source": {
                    "label": "Public search results across job-board domains",
                    "tables": ["data_folder/output/latest_search.json", "data_folder/output/data.json", "data_folder/output/success.json", "data_folder/output/review.json", "data_folder/output/failed.json", "data_folder/output/skipped.json"],
                    **({"executedAt": last_search["searchedAt"]} if last_search and last_search.get("searchedAt") else {}),
                    "filters": ["The dashboard shows the latest successful search result set; older discoveries stay in the local history file.", "Listings with duplicate canonical URLs are represented once."],
                    "metricDefinitions": [
                        {"label": "Job fit", "definition": "First-pass evidence from the listing title and search-provider snippet, matched to the configured role preferences and resume skill terms. This is not a full-description or eligibility assessment."},
                        {"label": "Application status", "definition": "Derived from local tracking files. Applied means the user confirmed they submitted the application; opening a listing does not mark it Applied."},
                        {"label": "Search window", "definition": "The selected range limits the search provider's indexed results; it does not verify when the employer posted the job or whether the posting is still open."},
                        {"label": "First found in this search", "definition": "The listing URL was not in Gogoi's local discovery history before this search. This is not the employer's posting date."}
                    ]
                }
            }
        },
        "fitSummary": dict(summary),
        "disclosure": "Listings are discovered through public indexed search results; snippets may be stale or incomplete. The optional application helper opens original postings in a visible local Chrome window and fills only recognized fields from the saved resume. The user signs in, reviews all entries, answers unknown questions, and submits manually; the helper never clicks the final Submit control."
    }


if __name__ == "__main__":
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(make_snapshot(), indent=2), encoding="utf-8")
    print(f"Wrote dashboard snapshot with {len(make_snapshot()['queries']['job_postings']['rows'])} unique jobs")
