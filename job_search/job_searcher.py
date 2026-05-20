# =============================================================================
# job_searcher.py — Core job search engine
# Searches LinkedIn, Indeed, Glassdoor, Google Jobs, and Naukri
# =============================================================================

import logging
import time
import re
from datetime import datetime, timedelta, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

import pandas as pd

from config import (
    EXPERIENCE_MATCH_PHRASES,
    EXPERIENCE_REJECT_PHRASES,
    JOB_BOARDS_JOBSPY,
    HOURS_OLD,
    MAX_RESULTS_PER_QUERY,
    REQUEST_DELAY_SECONDS,
    GLASSDOOR_DELAY_SECONDS,
    SCORE_WEIGHTS,
    MAX_SCORE,
)
from naukri_scraper import scrape_naukri
from glassdoor_scraper import scrape_glassdoor

logger = logging.getLogger(__name__)

# ─── JobSpy import (graceful fallback) ───────────────────────────────────────
try:
    from jobspy import scrape_jobs as jobspy_scrape
    JOBSPY_AVAILABLE = True
except ImportError:
    JOBSPY_AVAILABLE = False
    logger.warning("python-jobspy not installed. Install via: pip install python-jobspy")


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_job_search(
    search_config: dict,
    profile: dict,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    check_cancel: Optional[Callable[[], bool]] = None,
) -> list[dict]:
    """
    Run a complete job search across all configured job boards.

    Args:
        search_config: Dict with keys:
            - location_mode: one of 'chennai', 'remote_india', 'remote_global', 'outside_india'
            - custom_city: city string if location_mode == 'outside_india'
            - job_titles: list of job titles to search for
            - include_naukri: bool
        profile: Dict from resume_parser.parse_resume() or get_default_profile()
        progress_callback: Optional fn(message, percent) for SSE progress updates

    Returns:
        List of scored and filtered job dicts, sorted by match_score desc
    """
    def emit(msg: str, pct: int):
        logger.info(f"[{pct}%] {msg}")
        if progress_callback:
            progress_callback(msg, pct)

    location_text = search_config.get("location_text", "").strip()
    search_titles = search_config.get("job_titles", [])
    
    # ── Board toggles ────────────────────────────────────────────────────────
    include_linkedin = search_config.get("include_linkedin", True)
    include_indeed = search_config.get("include_indeed", True)
    include_glassdoor = search_config.get("include_glassdoor", True)
    include_naukri = search_config.get("include_naukri", True)
    include_naukrigulf = search_config.get("include_naukrigulf", True)
    include_wellfound = search_config.get("include_wellfound", True)

    if not location_text:
        raise ValueError("location_text is required in search_config. Cannot start job search without a location.")
    if not search_titles:
        raise ValueError("job_titles is required in search_config. Cannot start job search without job titles.")

    search_tasks = []
    is_remote = "remote" in location_text.lower() or "worldwide" in location_text.lower()
    lower_loc = location_text.lower()
    if "us" in lower_loc or "usa" in lower_loc or "united states" in lower_loc:
        country_indeed = "US"
    elif "uk" in lower_loc or "united kingdom" in lower_loc or "london" in lower_loc:
        country_indeed = "UK"
    elif "singapore" in lower_loc:
        country_indeed = "Singapore"
    elif "canada" in lower_loc:
        country_indeed = "Canada"
    elif "australia" in lower_loc:
        country_indeed = "Australia"
    else:
        country_indeed = "India"

    search_tasks.append({
        "mode_key": "custom",
        "label": location_text,
        "locations": [location_text],
        "glassdoor_locations": [_glassdoor_location_label(location_text)],
        "is_remote": is_remote,
        "country_indeed": country_indeed
    })

    mode_labels = [t["label"] for t in search_tasks]
    emit(f"Starting search for {len(search_titles)} titles in {', '.join(mode_labels)}...", 5)

    all_jobs = []
    
    # Build list of active JobSpy sites
    jobspy_sites = []
    if include_linkedin:
        jobspy_sites.append("linkedin")
    if include_indeed:
        jobspy_sites.append("indeed")
    if include_wellfound:
        jobspy_sites.append("wellfound")
    # Always query google jobs if we are searching jobspy sites or as general fallback
    if jobspy_sites:
        jobspy_sites.append("google")

    jobspy_steps = (sum(len(t["locations"]) for t in search_tasks) * len(search_titles)) if (jobspy_sites and JOBSPY_AVAILABLE) else 0
    glassdoor_steps = (sum(len(t["glassdoor_locations"]) for t in search_tasks) * len(search_titles)) if include_glassdoor else 0
    naukri_steps = len(search_tasks) if include_naukri else 0
    naukrigulf_steps = len(search_tasks) if include_naukrigulf else 0
    total_steps = jobspy_steps + glassdoor_steps + naukri_steps + naukrigulf_steps
    step = 0

    for task in search_tasks:
        if check_cancel and check_cancel(): break
        locations = task["locations"]
        is_remote = task["is_remote"]
        country_indeed = task["country_indeed"]
        glassdoor_locations = task["glassdoor_locations"]

        # ─── JobSpy Search ───────────────────────────────────────────────────────
        if JOBSPY_AVAILABLE and jobspy_sites:
            for location in locations:
                if check_cancel and check_cancel(): break
                for title in search_titles:
                    if check_cancel and check_cancel(): break
                    step += 1
                    pct = int(5 + (step / max(total_steps, 1)) * 60)
                    emit(f"Searching '{title}' on {', '.join(jobspy_sites)} ({location})...", pct)

                    jobs = _search_jobspy(
                        search_term=title,
                        location=location,
                        is_remote=is_remote,
                        country_indeed=country_indeed,
                        sites=jobspy_sites,
                    )
                    all_jobs.extend(jobs)
                    time.sleep(REQUEST_DELAY_SECONDS)

        # ─── Glassdoor ───────────────────────────────────────────────────────────
        if include_glassdoor:
            gd_country = country_indeed or "India"
            for gd_location in glassdoor_locations:
                if check_cancel and check_cancel(): break
                for title in search_titles:
                    if check_cancel and check_cancel(): break
                    step += 1
                    pct = int(5 + (step / max(total_steps, 1)) * 60)
                    emit(f"Searching '{title}' on Glassdoor ({gd_location})...", pct)

                    gd_jobs = _search_glassdoor(
                        search_term=title,
                        location=gd_location,
                        is_remote=is_remote,
                        country=gd_country,
                    )
                    all_jobs.extend(gd_jobs)
                    time.sleep(GLASSDOOR_DELAY_SECONDS)

        # ─── Naukri Scrape (Selenium) ─────────────────────────────────────────────
        if include_naukri and not (check_cancel and check_cancel()):
            step += 1
            naukri_location = locations[0] if locations else "Chennai"
            emit(f"Scraping Naukri.com for {naukri_location}...", 70)
            try:
                naukri_jobs = scrape_naukri(
                    search_terms=search_titles[:6],  # Limit to top 6 titles for speed
                    location=naukri_location,
                    is_remote=is_remote,
                    experience=search_config.get("experience", 1),
                    max_results=MAX_RESULTS_PER_QUERY,
                    headless=True,
                )
                all_jobs.extend(naukri_jobs)
                emit(f"Naukri: Found {len(naukri_jobs)} jobs", 80)
            except Exception as e:
                emit(f"Naukri scrape failed: {str(e)[:80]}", 80)
                logger.error(f"Naukri scrape error: {e}")

        # ─── Naukri Gulf Scrape (Selenium) ────────────────────────────────────────
        if include_naukrigulf and not (check_cancel and check_cancel()):
            step += 1
            naukrigulf_location = locations[0] if locations else "Dubai"
            emit(f"Scraping Naukrigulf.com for {naukrigulf_location}...", 80)
            try:
                from naukrigulf_scraper import scrape_naukrigulf
                naukrigulf_jobs = scrape_naukrigulf(
                    search_terms=search_titles[:6],
                    location=naukrigulf_location,
                    max_results=MAX_RESULTS_PER_QUERY,
                    headless=True,
                )
                all_jobs.extend(naukrigulf_jobs)
                emit(f"Naukri Gulf: Found {len(naukrigulf_jobs)} jobs", 85)
            except Exception as e:
                emit(f"Naukri Gulf scrape failed: {str(e)[:80]}", 85)
                logger.error(f"Naukri Gulf scrape error: {e}")

    emit(f"Processing {len(all_jobs)} raw results...", 85)

    # ─── Dedup + Filter + Score ───────────────────────────────────────────────
    filtered = _filter_jobs(all_jobs)
    emit(f"After 24hr filter: {len(filtered)} jobs remain", 90)

    scored = _score_jobs(filtered, profile)
    scored.sort(key=lambda j: j["match_score"], reverse=True)

    emit(f"Done! Found {len(scored)} matching jobs.", 100)
    return scored


# ─── Glassdoor helpers ────────────────────────────────────────────────────────

def _glassdoor_location_label(location: str) -> str:
    """Glassdoor location API works best with short city names, not full addresses."""
    if not location:
        return "Chennai"
    if location.lower() in ("india", "worldwide", "remote"):
        return location
    return location.split(",")[0].strip()


def _search_glassdoor(
    search_term: str,
    location: str,
    is_remote: bool,
    country: str,
) -> list[dict]:
    """Scrape Glassdoor via glassdoor_scraper (avoids JobSpy 403 on glassdoor.co.in)."""
    return scrape_glassdoor(
        search_term=search_term,
        location=_glassdoor_location_label(location),
        country=country or "India",
        is_remote=is_remote,
        max_results=MAX_RESULTS_PER_QUERY,
    )


# ─── JobSpy Search ────────────────────────────────────────────────────────────

def _search_jobspy(
    search_term: str,
    location: str,
    is_remote: bool,
    country_indeed: Optional[str],
    sites: list[str],
) -> list[dict]:
    """Run a single jobspy query and normalize results."""
    try:
        df = jobspy_scrape(
            site_name=sites,
            search_term=search_term,
            google_search_term=f"{search_term} jobs {location}",
            location=location,
            results_wanted=MAX_RESULTS_PER_QUERY,
            hours_old=HOURS_OLD,
            country_indeed=country_indeed or "India",
            is_remote=is_remote,
            linkedin_fetch_description=True,
            verbose=0,
        )

        if df is None or df.empty:
            return []

        return _normalize_jobspy_df(df, search_term)

    except Exception as e:
        logger.error(f"jobspy error for '{search_term}' @ '{location}': {e}")
        return []


def _normalize_jobspy_df(df: pd.DataFrame, search_term: str) -> list[dict]:
    """Convert a jobspy DataFrame to a list of normalized job dicts."""
    jobs = []
    for _, row in df.iterrows():
        try:
            # Parse date_posted — handle str, datetime, pandas Timestamp, NaT, float
            posted = row.get("date_posted")
            try:
                import pandas as pd
                if pd.isna(posted):
                    posted = None
            except Exception:
                pass
            if posted is not None:
                if isinstance(posted, str):
                    try:
                        posted = datetime.strptime(posted, "%Y-%m-%d").date()
                    except ValueError:
                        p_lower = posted.lower()
                        if "hour" in p_lower or "minute" in p_lower or "second" in p_lower or "now" in p_lower or "today" in p_lower:
                            posted = datetime.now().date()
                        elif "day" in p_lower:
                            import re
                            match = re.search(r'(\d+)', p_lower)
                            if match:
                                days = int(match.group(1))
                                posted = (datetime.now() - timedelta(days=days)).date()
                            else:
                                posted = datetime.now().date()
                        else:
                            posted = None
                elif hasattr(posted, "to_pydatetime"):
                    # pandas Timestamp
                    try:
                        posted = posted.to_pydatetime().date()
                    except Exception:
                        posted = None
                elif isinstance(posted, datetime):
                    posted = posted.date()
                elif isinstance(posted, date):
                    pass  # already a date
                elif isinstance(posted, float):
                    posted = None

            # Build job_url from available columns
            job_url = str(row.get("job_url") or row.get("url") or "")

            job = {
                "title": str(row.get("title") or ""),
                "company": str(row.get("company") or ""),
                "location": str(row.get("location") or ""),
                "description": str(row.get("description") or ""),
                "job_url": job_url,
                "date_posted": posted,
                "source": str(row.get("site") or "jobspy"),
                "search_term": search_term,
                "is_remote": bool(row.get("is_remote") or False),
                "min_amount": row.get("min_amount"),
                "max_amount": row.get("max_amount"),
                "salary_string": _format_salary(row),
                "_posted_datetime": _date_to_datetime(posted),
            }
            jobs.append(job)
        except Exception as e:
            logger.debug(f"Row normalization error: {e}")
    return jobs


def _format_salary(row) -> str:
    """Format salary from jobspy row."""
    min_a = row.get("min_amount")
    max_a = row.get("max_amount")
    currency = row.get("currency", "INR")
    if min_a and max_a:
        return f"{currency} {int(min_a):,} – {int(max_a):,}"
    elif min_a:
        return f"{currency} {int(min_a):,}+"
    return ""


def _date_to_datetime(d) -> Optional[datetime]:
    """Convert a date/Timestamp/string to datetime at midnight. Returns None for NaT/float/None."""
    if d is None:
        return None
    # Pandas NaT or any float (NaT repr) — treat as unknown
    try:
        import math
        if isinstance(d, float):
            return None
    except Exception:
        pass
    # Pandas Timestamp
    try:
        import pandas as pd
        if isinstance(d, pd.Timestamp):
            if pd.isna(d):
                return None
            return d.to_pydatetime().replace(tzinfo=None)
    except Exception:
        pass
    # Plain date (not datetime)
    if isinstance(d, date) and not isinstance(d, datetime):
        return datetime(d.year, d.month, d.day)
    # Already a datetime
    if isinstance(d, datetime):
        return d.replace(tzinfo=None)
    return None


# ─── Filtering ────────────────────────────────────────────────────────────────

def _filter_jobs(jobs: list[dict]) -> list[dict]:
    """
    Filter jobs to:
    1. Only those posted in the last 24 hours
    2. Remove duplicates by URL
    """
    cutoff = datetime.now() - timedelta(hours=HOURS_OLD)
    seen_urls = set()
    filtered = []

    for job in jobs:
        # Dedup by URL
        url = job.get("job_url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # 24-hour filter
        posted_dt = job.get("_posted_datetime")
        if posted_dt:
            if isinstance(posted_dt, datetime) and posted_dt < cutoff:
                continue
        # If no date info, include by default (some boards don't return dates)

        filtered.append(job)

    return filtered


# ─── Scoring ──────────────────────────────────────────────────────────────────

def _score_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    """Score each job based on keyword match with the user's profile."""
    search_keywords = profile.get("search_keywords", [])
    scored = []

    for job in jobs:
        score = _calculate_score(job, profile)
        job["match_score"] = min(score, MAX_SCORE)
        job["match_grade"] = _score_to_grade(job["match_score"])
        scored.append(job)

    return scored


def _calculate_score(job: dict, profile: dict) -> int:
    """Calculate a 0–100 match score for a job against the user's profile."""
    score = 0
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    combined_text = f"{title} {description}"

    # ── Title match ─────────────────────────────────────────
    profile_titles = [t.lower() for t in profile.get("suggested_titles", [])]
    if any(t in title for t in profile_titles):
        score += SCORE_WEIGHTS["title_exact_match"]
    elif any(
        word in title
        for t in profile_titles
        for word in t.split()
        if len(word) > 3
    ):
        score += SCORE_WEIGHTS["title_partial_match"]

    # ── Keyword match (each keyword counted once) ──────────────────
    matched: set[str] = set()
    profile_skills = profile.get("skills", [])
    for kw in profile_skills:
        key = kw.lower()
        if key not in matched and key in combined_text:
            matched.add(key)
            score += SCORE_WEIGHTS["high_keyword_match"]

    # ── Experience level match ────────────────────────────────
    if any(phrase in combined_text for phrase in EXPERIENCE_MATCH_PHRASES):
        score += SCORE_WEIGHTS["experience_match"]
    # Penalize senior roles
    if any(phrase in combined_text for phrase in EXPERIENCE_REJECT_PHRASES):
        score -= 20

    # ── Recency bonus (posted < 6 hrs ago) ────────────────────
    posted_dt = job.get("_posted_datetime")
    if posted_dt and isinstance(posted_dt, datetime):
        try:
            hours_ago = (datetime.now() - posted_dt).total_seconds() / 3600
            if hours_ago <= 6:
                score += SCORE_WEIGHTS["recency_bonus"]
        except (TypeError, ValueError):
            pass

    return max(score, 0)


def _score_to_grade(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 80:
        return "A+"
    elif score >= 65:
        return "A"
    elif score >= 50:
        return "B"
    elif score >= 35:
        return "C"
    else:
        return "D"