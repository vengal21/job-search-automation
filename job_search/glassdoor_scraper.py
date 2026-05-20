# =============================================================================
# glassdoor_scraper.py — Glassdoor job scraper (India-friendly)
# Uses plain requests with minimal headers; JobSpy's tls_client gets 403 on .co.in
# =============================================================================

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import HOURS_OLD, GLASSDOOR_MAX_RETRIES, GLASSDOOR_DELAY_SECONDS

logger = logging.getLogger(__name__)

try:
    from jobspy.glassdoor.constant import query_template, fallback_token
    from jobspy.model import Country
    _JOBSPY_GLASSDOOR_OK = True
    _JOBSPY_IMPORT_ERROR = None
except ImportError as _import_err:
    query_template = None
    fallback_token = ""
    Country = None
    _JOBSPY_GLASSDOOR_OK = False
    _JOBSPY_IMPORT_ERROR = _import_err

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _base_url(country: str) -> str:
    if Country is None:
        return "https://www.glassdoor.co.in"
    return Country.from_string(country).get_glassdoor_url().rstrip("/")


def _resolve_location(session: requests.Session, base: str, location: str, is_remote: bool) -> tuple[Optional[int], Optional[str]]:
    if is_remote or not location:
        return 11047, "STATE"

    r = session.get(
        f"{base}/findPopularLocationAjax.htm",
        params={"maxLocationsToReturn": 10, "term": location},
        timeout=15,
    )
    if r.status_code != 200:
        logger.error(f"Glassdoor location lookup {r.status_code} for '{location}'")
        return None, None

    items = r.json()
    if not items:
        logger.error(f"Glassdoor: no location match for '{location}'")
        return None, None

    item = items[0]
    loc_type = item["locationType"]
    if loc_type == "C":
        loc_type = "CITY"
    elif loc_type == "S":
        loc_type = "STATE"
    elif loc_type == "N":
        loc_type = "COUNTRY"
    return int(item["locationId"]), loc_type


def _get_csrf_token(session: requests.Session, base: str) -> str:
    try:
        r = session.get(f"{base}/Job/computer-science-jobs.htm", timeout=15)
        matches = re.findall(r'"token":\s*"([^"]+)"', r.text)
        if matches:
            return matches[0]
    except Exception as e:
        logger.debug(f"Glassdoor CSRF fetch failed: {e}")
    return fallback_token


def _parse_job(job_data: dict, base: str, search_term: str) -> Optional[dict]:
    try:
        job = job_data["jobview"]
        job_id = job["job"]["listingId"]
        title = job["job"]["jobTitleText"]
        company = job["header"]["employerNameFromSearch"]
        location_name = job["header"].get("locationName", "")
        age_in_days = job["header"].get("ageInDays")
        date_posted = None
        if age_in_days is not None:
            date_posted = (datetime.now() - timedelta(days=age_in_days)).date()

        return {
            "title": title,
            "company": company,
            "location": location_name,
            "description": "",
            "job_url": f"{base}/job-listing/j?jl={job_id}",
            "date_posted": date_posted,
            "source": "glassdoor",
            "search_term": search_term,
            "is_remote": job["header"].get("locationType") == "S",
            "min_amount": None,
            "max_amount": None,
            "salary_string": "",
            "_posted_datetime": (
                datetime(date_posted.year, date_posted.month, date_posted.day)
                if date_posted else None
            ),
        }
    except Exception as e:
        logger.debug(f"Glassdoor job parse error: {e}")
        return None


def scrape_glassdoor(
    search_term: str,
    location: str,
    country: str = "India",
    is_remote: bool = False,
    max_results: int = 30,
) -> list[dict]:
    """
    Scrape Glassdoor for jobs. Returns normalized job dicts for job_searcher.
    """
    if not _JOBSPY_GLASSDOOR_OK or not query_template:
        msg = (
            "Glassdoor unavailable: install python-jobspy "
            "(pip install python-jobspy) or upgrade it if already installed."
        )
        if not _JOBSPY_GLASSDOOR_OK:
            logger.error("%s Import error: %s", msg, _JOBSPY_IMPORT_ERROR)
        else:
            logger.error(msg)
        return []

    country = country or "India"
    city = location.split(",")[0].strip() if location and not is_remote else location
    base = _base_url(country)

    for attempt in range(1, GLASSDOOR_MAX_RETRIES + 1):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-IN,en;q=0.9",
            })

            location_id, location_type = _resolve_location(session, base, city, is_remote)
            if location_type is None:
                if attempt < GLASSDOOR_MAX_RETRIES:
                    time.sleep(GLASSDOOR_DELAY_SECONDS * attempt)
                continue

            token = _get_csrf_token(session, base)
            fromage = max(HOURS_OLD // 24, 1)
            filter_params = [{"filterKey": "fromAge", "values": str(fromage)}]

            jobs: list[dict] = []
            cursor = None
            pages = min(3, (max_results // 30) + 1)

            for page in range(1, pages + 1):
                payload = [{
                    "operationName": "JobSearchResultsQuery",
                    "variables": {
                        "excludeJobListingIds": [],
                        "filterParams": filter_params,
                        "keyword": search_term,
                        "numJobsToShow": 30,
                        "locationType": location_type,
                        "locationId": location_id,
                        "parameterUrlInput": f"IL.0,12_I{location_type}{location_id}",
                        "pageNumber": page,
                        "pageCursor": cursor,
                        "fromage": fromage,
                        "sort": "date",
                    },
                    "query": query_template,
                }]
                headers = {
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Origin": base,
                    "Referer": f"{base}/",
                    "gd-csrf-token": token,
                    "apollographql-client-name": "job-search-next",
                    "apollographql-client-version": "4.65.5",
                }
                r = session.post(f"{base}/graph", json=payload, headers=headers, timeout=20)
                if r.status_code != 200:
                    logger.error(f"Glassdoor graph API {r.status_code} (page {page})")
                    break

                res = r.json()[0]
                listings = (
                    res.get("data", {})
                    .get("jobListings", {})
                    .get("jobListings")
                )
                if not listings:
                    if res.get("errors"):
                        logger.error(f"Glassdoor API errors: {res['errors']}")
                    break
                for item in listings:
                    job = _parse_job(item, base, search_term)
                    if job:
                        jobs.append(job)

                if len(jobs) >= max_results or not listings:
                    break

                cursors = res["data"]["jobListings"].get("paginationCursors") or []
                cursor = next(
                    (c["cursor"] for c in cursors if c.get("pageNumber") == page + 1),
                    None,
                )
                if not cursor:
                    break

            jobs = jobs[:max_results]
            logger.info(f"Glassdoor: {len(jobs)} jobs for '{search_term}' @ '{city}'")
            return jobs

        except Exception as e:
            logger.warning(
                f"Glassdoor attempt {attempt}/{GLASSDOOR_MAX_RETRIES} "
                f"for '{search_term}' @ '{city}': {e}"
            )
            if attempt < GLASSDOOR_MAX_RETRIES:
                time.sleep(GLASSDOOR_DELAY_SECONDS * attempt)

    return []
