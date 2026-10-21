"""Discover public job-posting search results across configured board domains.

This uses the user's configured web-search API, not board-site scraping or login
automation. Search results are leads; open the original posting to verify details.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import DEFAULT_SEARCH_ENGINE
from services.web_search_engine import (  # noqa: E402
    SearchTimeRange,
    UnifiedQuery,
    WebSearchEngineFactory,
)
from job_result_details import extract_company, extract_location  # noqa: E402

OUTPUT = ROOT / "data_folder" / "output"
LATEST_SEARCH = OUTPUT / "latest_search.json"
PREFERENCES = ROOT / "data_folder" / "work_preferences.yaml"
RESUME = ROOT / "data_folder" / "plain_text_resume.yaml"
CLASSIFICATIONS = ROOT / "data_folder" / "company_classifications.yaml"

BOARD_QUERIES = {
    "LinkedIn": "(site:linkedin.com/jobs/view OR site:linkedin.com/jobs/collections)",
    "Naukri": "(site:naukri.com/job-listings OR site:naukri.com/jobs)",
    "Indeed": "(site:in.indeed.com/viewjob OR site:indeed.com/viewjob)",
    "Glassdoor": "(site:glassdoor.co.in/job-listing OR site:glassdoor.com/job-listing)",
    "Company careers": "(site:myworkdayjobs.com OR site:greenhouse.io OR site:ashbyhq.com OR site:apply.workable.com OR site:jobs.smartrecruiters.com)",
}
LOCATION_QUERIES = {
    "Chennai onsite/hybrid": '("Chennai" OR "Tamil Nadu") ("hybrid" OR "on-site" OR "onsite" OR "office")',
    "Bengaluru onsite/hybrid": '("Bengaluru" OR "Bangalore") ("hybrid" OR "on-site" OR "onsite" OR "office")',
    "Remote India": '"remote" "India"',
    "Remote worldwide, India eligible": '"remote" ("worldwide" OR "anywhere" OR "global")',
}
DATE_FILTERS = {
    "any": None,
    "24h": SearchTimeRange.LAST_24_HOURS,
    "3d": SearchTimeRange.LAST_3_DAYS,
    "7d": SearchTimeRange.LAST_WEEK,
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _role_query(preferences: dict[str, Any]) -> str:
    roles = [str(role).strip() for role in preferences.get("positions", []) if str(role).strip()]
    return "(" + " OR ".join(f'"{role}"' for role in roles) + ")" if roles else '"Business Analyst" OR "Data Analyst"'


def _profile_keywords(resume: dict[str, Any]) -> list[str]:
    collected: list[str] = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.casefold() in {"skills", "skills_acquired", "technical_skills"}:
                    visit(nested)
                elif isinstance(nested, (dict, list)):
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)
        elif isinstance(value, str) and value.strip():
            collected.extend(part.strip() for part in value.replace("\n", ",").split(",") if part.strip())
    visit(resume)
    return list(dict.fromkeys(collected))


def _clean_result(result, board: str, location_priority: int, run_at: str, window: str, keywords: list[str]) -> dict[str, Any] | None:
    parsed = urlsplit(str(result.link or "").strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    tracking_names = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid"}
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not key.casefold().startswith("utm_") and key.casefold() not in tracking_names]
    link = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urlencode(query, doseq=True), ""))
    title = str(result.title or "").strip()
    snippet = str(result.snippet or "").strip()
    text = f"{title} {snippet}".casefold()
    matched = [keyword for keyword in keywords if keyword.casefold() in text]
    raw = result.raw_data if isinstance(result.raw_data, dict) else {}
    company, company_evidence = extract_company(title, snippet, link, str(raw.get("company", "") or ""))
    location, location_evidence = extract_location(title, snippet)
    return {
        "title": title or "Untitled job listing",
        "company": company,
        "companyEvidence": company_evidence,
        "location": location,
        "locationEvidence": location_evidence,
        "priorityArea": list(LOCATION_QUERIES)[location_priority],
        "link": link,
        "source": board,
        "snippet": snippet,
        "timestamp": run_at,
        "searchWindows": [window],
        "locationPriority": location_priority,
        "matchedResumeKeywords": matched[:12],
        "companyType": "Unclassified",
        "description": "",
    }


def collect_jobs(window: str = "any", engine_name: str | None = None) -> dict[str, Any]:
    if window not in DATE_FILTERS:
        raise ValueError("Choose a supported posting freshness window: any, 24h, 3d, or 7d.")
    preferences = _load_yaml(PREFERENCES)
    resume = _load_yaml(RESUME)
    classifications = _load_yaml(CLASSIFICATIONS)
    company_types = {}
    for label in ("product", "service"):
        for name in classifications.get(label, []) or []:
            if str(name).strip():
                company_types[" ".join(str(name).strip().casefold().split())] = label.title()
    skills = _profile_keywords(resume)
    roles = preferences.get("positions", [])
    keywords = list(dict.fromkeys([*(str(x) for x in roles), *skills, "Power BI", "SQL", "Excel", "dashboard", "reporting"]))
    location_names = list(LOCATION_QUERIES)
    role_clause = _role_query(preferences)
    selected_engine = WebSearchEngineFactory.get_search_engine(engine_name or DEFAULT_SEARCH_ENGINE)
    run_at = datetime.now(timezone.utc).isoformat()
    results_by_link: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for priority, location in enumerate(location_names):
        for board, board_clause in BOARD_QUERIES.items():
            query_text = f"{role_clause} ({LOCATION_QUERIES[location]}) {board_clause}"
            unified = UnifiedQuery(keywords=[query_text], date_range=DATE_FILTERS[window], gl="in")
            query, params = selected_engine.build_query(unified)
            try:
                response = selected_engine.search(query, params, offset=0, limit=10)
            except Exception as exc:
                errors.append(f"{board} / {location}: {type(exc).__name__}: {exc}")
                continue
            for result in response.results:
                row = _clean_result(result, board, priority, run_at, window, keywords)
                if row is None:
                    continue
                company_key = " ".join(row["company"].casefold().split())
                classification_match = next(((name, category) for name, category in company_types.items() if name in f"{row['title']} {row['snippet']}".casefold()), None)
                if classification_match:
                    row["company"] = classification_match[0]
                    row["companyType"] = classification_match[1]
                else:
                    row["companyType"] = company_types.get(company_key, "Unclassified")
                row["companyPriority"] = (0 if priority == 0 else 1 if priority == 1 else 2 if priority == 2 else 3) if row["companyType"] == "Product" else (4 + priority if row["companyType"] == "Service" else 20 + priority)
                prior = results_by_link.get(row["link"])
                if prior is None or row["locationPriority"] < prior["locationPriority"]:
                    results_by_link[row["link"]] = row

    if errors and not results_by_link:
        raise RuntimeError(f"The job search returned no listings and {len(errors)} of {len(BOARD_QUERIES) * len(LOCATION_QUERIES)} searches failed. The previous results were kept. See dashboard_discovery.log for diagnostics.")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    data_file = OUTPUT / "data.json"
    old_rows = json.loads(data_file.read_text(encoding="utf-8")) if data_file.is_file() else []
    merged: dict[str, dict[str, Any]] = {}
    for old in old_rows if isinstance(old_rows, list) else []:
        link = str(old.get("link", "")).strip()
        if link:
            merged[link] = old
    current_rows = []
    for link, fresh in results_by_link.items():
        prior = merged.get(link)
        if not isinstance(prior, dict):
            prior = None
        prior_windows = prior.get("searchWindows", []) if isinstance(prior, dict) and isinstance(prior.get("searchWindows"), list) else []
        if isinstance(prior, dict) and not prior_windows and prior.get("searchWindow"):
            prior_windows = [prior["searchWindow"]]
        first_seen = (prior or {}).get("firstSeenAt") or (prior or {}).get("timestamp") or run_at
        history_row = {
            **(prior or {}),
            **fresh,
            "firstSeenAt": first_seen,
            "lastSeenAt": run_at,
            "lastSearchWindow": window,
            "searchWindows": sorted(set([*prior_windows, window])),
            "newFinding": prior is None,
        }
        merged[link] = history_row
        # The dashboard displays this search's result set, not every listing ever found.
        current_rows.append({**history_row, "searchWindows": [window]})
    data_file.write_text(json.dumps(list(merged.values()), indent=2), encoding="utf-8")
    latest_search = {
        "searchedAt": run_at,
        "window": window,
        "count": len(current_rows),
        "engine": selected_engine.__class__.__name__,
        "errors": errors,
        "rows": current_rows,
    }
    temp_latest = LATEST_SEARCH.with_suffix(".json.tmp")
    temp_latest.write_text(json.dumps(latest_search, indent=2), encoding="utf-8")
    temp_latest.replace(LATEST_SEARCH)
    ordered = sorted(results_by_link.values(), key=lambda row: (row["locationPriority"], row["source"], row["title"].casefold()))
    return {"count": len(results_by_link), "totalStored": len(merged), "window": window, "searchedAt": run_at, "engine": selected_engine.__class__.__name__, "errors": errors, "rows": ordered}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", choices=DATE_FILTERS, default="any")
    parser.add_argument("--engine", default=None)
    args = parser.parse_args()
    result = collect_jobs(args.window, args.engine)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
