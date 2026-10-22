"""Discover public job-posting search results across configured board domains.

This uses the user's configured web-search API, not board-site scraping or login
automation. Search results are leads; open the original posting to verify details.
"""
from __future__ import annotations

import json
import os
import re
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
BOARD_DOMAINS = {
    "LinkedIn": ("linkedin.com",),
    "Naukri": ("naukri.com",),
    "Indeed": ("indeed.com",),
    "Glassdoor": ("glassdoor.com", "glassdoor.co.in"),
    "Company careers": ("myworkdayjobs.com", "greenhouse.io", "ashbyhq.com", "workable.com", "smartrecruiters.com"),
}
LOCATION_QUERIES = {
    "Chennai onsite/hybrid": '("Chennai" OR "Tamil Nadu") ("hybrid" OR "on-site" OR "onsite" OR "office")',
    "Bengaluru onsite/hybrid": '("Bengaluru" OR "Bangalore") ("hybrid" OR "on-site" OR "onsite" OR "office")',
    "Remote India": '"remote" "India"',
    "Remote worldwide, India eligible": '"remote" ("worldwide" OR "anywhere" OR "global")',
}
DEFAULT_LOCATIONS = tuple(LOCATION_QUERIES.items())
DATE_FILTERS = {
    "any": None,
    "24h": SearchTimeRange.LAST_24_HOURS,
    "3d": SearchTimeRange.LAST_3_DAYS,
    "7d": SearchTimeRange.LAST_WEEK,
}
MAX_PAGES_PER_QUERY = 10
# Leave room for the freshness operator appended by the Brave query builder.
MAX_QUERY_CHARS = 580
MAX_QUERY_WORDS = 73

_JOB_TYPE_TERMS = {
    "full_time": ('"full-time"', '"full time"', "fulltime", "permanent"),
    "contract": ("contract", "contractor"),
    "part_time": ('"part-time"', '"part time"'),
    "temporary": ("temporary", "temp role"),
    "internship": ("internship", "intern"),
}
_DISABLED_EXPERIENCE_TITLE_TERMS = {
    "internship": ("intern", "internship"),
    "entry": (),
    "associate": (),
    "mid_senior_level": (),
    "director": ("director", "head of"),
    "executive": ("executive", "vice president", "vp"),
}
_DISABLED_JOB_TYPE_TITLE_TERMS = {
    "part_time": ("part-time", "part time"),
    "temporary": ("temporary", "temp role"),
    "internship": ("intern", "internship"),
    "volunteer": ("volunteer",),
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _role_query(preferences: dict[str, Any]) -> str:
    roles = _roles(preferences)
    return _role_query_for(roles)


def _roles(preferences: dict[str, Any]) -> list[str]:
    roles = [str(role).strip().replace('"', "") for role in preferences.get("positions", []) or [] if str(role).strip()]
    return roles or ["Business Analyst", "Data Analyst"]


def _role_query_for(roles: list[str]) -> str:
    return "(" + " OR ".join(f'"{role}"' for role in roles) + ")" if roles else '"Business Analyst" OR "Data Analyst"'


def _role_query_groups(roles: list[str], other_parts: list[str]) -> list[list[str]]:
    """Split roles only when the provider's query-size limits require it."""
    groups: list[list[str]] = []
    current: list[str] = []
    for role in roles:
        candidate = [*current, role]
        query = " ".join([_role_query_for(candidate), *other_parts])
        if len(query) <= MAX_QUERY_CHARS and len(query.split()) <= MAX_QUERY_WORDS:
            current = candidate
            continue
        if not current:
            raise ValueError(
                "Saved job-search filters are too long to fit the search provider's 600-character or 75-word query limit. "
                "Shorten the role, keyword, or blacklist entries in data_folder/work_preferences.yaml."
            )
        groups.append(current)
        current = [role]
        query = " ".join([_role_query_for(current), *other_parts])
        if len(query) > MAX_QUERY_CHARS or len(query.split()) > MAX_QUERY_WORDS:
            raise ValueError(
                "Saved job-search filters are too long to fit the search provider's 600-character or 75-word query limit. "
                "Shorten the role, keyword, or blacklist entries in data_folder/work_preferences.yaml."
            )
    if current:
        groups.append(current)
    return groups


def _location_queries(preferences: dict[str, Any]) -> list[tuple[str, str]]:
    """Build the search areas from the saved location and work-mode filters."""
    configured = [str(value).strip() for value in preferences.get("locations", []) or [] if str(value).strip()]
    if not configured:
        configured = [name for name, _ in DEFAULT_LOCATIONS]

    remote = bool(preferences.get("remote", True))
    onsite = bool(preferences.get("onsite", True))
    hybrid = bool(preferences.get("hybrid", True))
    work_modes = [term for enabled, term in ((onsite, '"on-site" OR onsite OR office'), (hybrid, "hybrid")) if enabled]
    mode_clause = f'({" OR ".join(work_modes)})' if work_modes else ""
    selected: list[tuple[str, str]] = []
    seen: set[str] = set()

    for value in configured:
        normalized = " ".join(value.casefold().replace("bangalore", "bengaluru").split())
        if "remote" in normalized:
            if not remote:
                continue
            if "world" in normalized or "global" in normalized or "anywhere" in normalized:
                entry = ("Remote worldwide", '"remote" ("worldwide" OR "anywhere" OR "global")')
            else:
                entry = ("Remote India", '"remote" "India"')
        elif "chennai" in normalized or "tamil nadu" in normalized:
            if not mode_clause:
                continue
            entry = ("Chennai onsite/hybrid", f'("Chennai" OR "Tamil Nadu") {mode_clause}')
        elif "bengaluru" in normalized:
            if not mode_clause:
                continue
            entry = ("Bengaluru onsite/hybrid", f'("Bengaluru" OR "Bangalore") {mode_clause}')
        else:
            if not mode_clause:
                continue
            safe_location = value.replace('"', "")
            entry = (f"{value} onsite/hybrid", f'"{safe_location}" {mode_clause}')
        if entry[0] not in seen:
            selected.append(entry)
            seen.add(entry[0])
    return selected


def _preference_terms(preferences: dict[str, Any], section: str, mapping: dict[str, tuple[str, ...]]) -> str:
    enabled = preferences.get(section, {})
    if not isinstance(enabled, dict):
        return ""
    # "Other" means the user accepts job types that have no reliable search phrase.
    if section == "job_types" and enabled.get("other") is True:
        return ""
    terms = [term for key, synonyms in mapping.items() if enabled.get(key) is True for term in synonyms]
    return f'({" OR ".join(dict.fromkeys(terms))})' if terms else ""


def _search_pages(engine, query: str, params: dict[str, Any], max_pages: int) -> tuple[list[Any], int, bool, str | None]:
    """Fetch pages until the provider reports exhaustion or its safe page cap."""
    page_size = int(engine.DEFAULT_SEARCH_LIMIT)
    brave_paging = engine.__class__.__name__ == "BraveSearchEngine"
    results: list[Any] = []
    seen_pages: set[tuple[str, ...]] = set()
    pages = 0
    reached_cap = False
    error = None

    for page_index in range(max_pages):
        offset = page_index if brave_paging else page_index * page_size
        try:
            response = engine.search(query, dict(params), offset=offset, limit=page_size)
        except Exception as exc:
            error = f"page {page_index + 1}: {type(exc).__name__}: {exc}"
            break
        pages += 1
        page_results = response.results or []
        if not page_results:
            break
        signature = tuple(str(item.link or item.title or "") for item in page_results)
        if signature in seen_pages:
            error = "provider repeated a result page before finishing"
            break
        seen_pages.add(signature)
        results.extend(page_results)

        more = response.more_results_available
        if more is False:
            break
        if response.total_results is not None and offset + len(page_results) >= response.total_results:
            break
        if len(page_results) < page_size and more is not True:
            break
        if page_index == max_pages - 1:
            reached_cap = True

    return results, pages, reached_cap, error


def _excluded(row: dict[str, Any], preferences: dict[str, Any]) -> bool:
    def matches(value: Any, text: str) -> bool:
        normalized_text = " ".join(str(text).casefold().split())
        return any(" ".join(str(term).casefold().split()) in normalized_text
                   for term in value if str(term).strip())

    def title_has_any(terms: tuple[str, ...], title: str) -> bool:
        normalized_title = " " + re.sub(r"[\W_]+", " ", title.casefold()).strip() + " "
        return any(
            " " + re.sub(r"[\W_]+", " ", term.casefold()).strip() + " " in normalized_title
            for term in terms
        )

    title = row["title"]
    company_text = f'{row["company"]} {title} {row["snippet"]}'
    location_text = f'{row["location"]} {title} {row["snippet"]}'
    blacklisted = (
        matches(preferences.get("title_blacklist", []) or [], title)
        or matches(preferences.get("company_blacklist", []) or [], company_text)
        or matches(preferences.get("location_blacklist", []) or [], location_text)
    )
    if blacklisted:
        return True

    # Search indexes do not expose structured experience or job-type fields.
    # Exclude only titles that explicitly identify a disabled category so that
    # jobs with missing snippets/details are not silently lost.
    for section, terms_by_filter in (
        ("experience_level", _DISABLED_EXPERIENCE_TITLE_TERMS),
        ("job_types", _DISABLED_JOB_TYPE_TITLE_TERMS),
    ):
        selected = preferences.get(section, {})
        if not isinstance(selected, dict):
            continue
        for filter_name, terms in terms_by_filter.items():
            if selected.get(filter_name) is False and title_has_any(terms, title):
                return True
    return False


def _belongs_to_board(link: str, board: str) -> bool:
    host = (urlsplit(link).hostname or "").casefold().removeprefix("www.")
    return any(host == domain or host.endswith(f".{domain}") for domain in BOARD_DOMAINS[board])


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


def _clean_result(result, board: str, location_priority: int, priority_area: str, run_at: str, window: str, keywords: list[str]) -> dict[str, Any] | None:
    parsed = urlsplit(str(result.link or "").strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    tracking_names = {"fbclid", "gclid", "dclid", "mc_cid", "mc_eid"}
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not key.casefold().startswith("utm_") and key.casefold() not in tracking_names]
    link = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, urlencode(query, doseq=True), ""))
    if not _belongs_to_board(link, board):
        return None
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
        "priorityArea": priority_area,
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
    roles = _roles(preferences)
    keywords = list(dict.fromkeys([*(str(x) for x in roles), *skills, "Power BI", "SQL", "Excel", "dashboard", "reporting"]))
    location_queries = _location_queries(preferences)
    if not location_queries:
        raise ValueError("No enabled job locations or work modes were found in data_folder/work_preferences.yaml.")
    preference_clauses = [_preference_terms(preferences, "job_types", _JOB_TYPE_TERMS)]
    keyword_whitelist = [str(item).strip().replace('"', "") for item in preferences.get("keywords_whitelist", []) or [] if str(item).strip()]
    if keyword_whitelist:
        preference_clauses.append("(" + " OR ".join(f'"{item}"' for item in keyword_whitelist) + ")")
    preference_clauses = [clause for clause in preference_clauses if clause]
    blacklist = list(dict.fromkeys(
        str(term).strip().replace('"', "")
        for key in ("company_blacklist", "title_blacklist", "location_blacklist")
        for term in (preferences.get(key, []) or [])
        if str(term).strip()
    ))
    blacklist_clause = " ".join(f'-"{term}"' for term in blacklist)
    selected_engine = WebSearchEngineFactory.get_search_engine(engine_name or DEFAULT_SEARCH_ENGINE)
    run_at = datetime.now(timezone.utc).isoformat()
    results_by_link: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    try:
        max_pages = min(MAX_PAGES_PER_QUERY, max(1, int(os.environ.get("JOB_SEARCH_MAX_PAGES_PER_QUERY", MAX_PAGES_PER_QUERY))))
    except (TypeError, ValueError):
        max_pages = MAX_PAGES_PER_QUERY
    query_count = pages_fetched = queries_at_page_limit = excluded_count = 0
    incomplete_queries: set[str] = set()

    query_plan: list[tuple[int, str, str, str]] = []
    for priority, (location, location_clause) in enumerate(location_queries):
        for board, board_clause in BOARD_QUERIES.items():
            other_parts = [*preference_clauses, f"({location_clause})", board_clause, blacklist_clause]
            for role_group in _role_query_groups(roles, other_parts):
                query_text = " ".join([_role_query_for(role_group), *other_parts])
                query_plan.append((priority, location, board, query_text))

    query_count = len(query_plan)
    for priority, location, board, query_text in query_plan:
        unified = UnifiedQuery(keywords=[query_text], date_range=DATE_FILTERS[window], gl="in")
        query, params = selected_engine.build_query(unified)
        label = f"{board} / {location}"
        page_results, page_count, reached_cap, page_error = _search_pages(selected_engine, query, params, max_pages)
        pages_fetched += page_count
        if reached_cap:
            queries_at_page_limit += 1
            incomplete_queries.add(label)
        if page_error:
            errors.append(f"{label} {page_error}")
            incomplete_queries.add(label)
        for result in page_results:
            row = _clean_result(result, board, priority, location, run_at, window, keywords)
            if row is None:
                continue
            if _excluded(row, preferences):
                excluded_count += 1
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
        raise RuntimeError(f"The job search returned no listings and {len(errors)} of {query_count} searches failed. The previous results were kept. See dashboard_discovery.log for diagnostics.")

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
        "searchStats": {
            "queries": query_count,
            "pagesFetched": pages_fetched,
            "maxPagesPerQuery": max_pages,
            "queriesAtPageLimit": queries_at_page_limit,
            "incompleteQueries": len(incomplete_queries),
            "excludedByPreferences": excluded_count,
        },
        "rows": current_rows,
    }
    temp_latest = LATEST_SEARCH.with_suffix(".json.tmp")
    temp_latest.write_text(json.dumps(latest_search, indent=2), encoding="utf-8")
    temp_latest.replace(LATEST_SEARCH)
    ordered = sorted(results_by_link.values(), key=lambda row: (row["locationPriority"], row["source"], row["title"].casefold()))
    return {"count": len(results_by_link), "totalStored": len(merged), "window": window, "searchedAt": run_at, "engine": selected_engine.__class__.__name__, "errors": errors, "searchStats": latest_search["searchStats"], "rows": ordered}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", choices=DATE_FILTERS, default="any")
    parser.add_argument("--engine", default=None)
    args = parser.parse_args()
    result = collect_jobs(args.window, args.engine)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
