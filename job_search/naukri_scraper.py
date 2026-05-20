# =============================================================================
# naukri_scraper.py — Selenium-based Naukri.com job scraper
# =============================================================================

import time
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os

logger = logging.getLogger(__name__)

NAUKRI_BASE = "https://www.naukri.com"

# Naukri URL format:
# https://www.naukri.com/{keyword-slug}-jobs-in-{location-slug}?experience={exp}
# e.g. https://www.naukri.com/business-analyst-jobs-in-chennai?experience=1


def _build_naukri_url(search_term: str, location: str, experience: int = 1) -> str:
    """Build a Naukri search URL."""
    keyword_slug = search_term.lower().strip().replace(" ", "-")
    if location and location.lower() not in ["india", "worldwide", "remote"]:
        location_slug = location.split(",")[0].strip().lower().replace(" ", "-")
        path = f"/{keyword_slug}-jobs-in-{location_slug}"
    else:
        path = f"/{keyword_slug}-jobs"

    url = f"{NAUKRI_BASE}{path}?experience={experience}"
    if location.lower() in ["india", "remote"]:
        url += "&wfhType=2"  # work from home filter
    logger.debug(f"Naukri URL: {url}")
    return url


def _parse_posted_time(time_str: str) -> Optional[datetime]:
    """Parse Naukri's posted time string into a datetime."""
    if not time_str:
        return None
    time_str = time_str.lower().strip()
    now = datetime.now()
    try:
        if "few" in time_str or "just" in time_str or "minute" in time_str:
            return now - timedelta(minutes=30)
        elif "hour" in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1)) if re.search(r'(\d+)', time_str) else 1
            return now - timedelta(hours=hours)
        elif "day" in time_str:
            days = int(re.search(r'(\d+)', time_str).group(1)) if re.search(r'(\d+)', time_str) else 1
            return now - timedelta(days=days)
        elif "today" in time_str:
            return now
        elif "yesterday" in time_str:
            return now - timedelta(days=1)
    except Exception:
        pass
    return None


def _is_within_24_hours(posted_time: Optional[datetime]) -> bool:
    """Return True if the job was posted within the last 24 hours."""
    if posted_time is None:
        return True  # Include if we can't determine (err on side of inclusion)
    return (datetime.now() - posted_time).total_seconds() <= 86400


def scrape_naukri(
    search_terms: list[str],
    location: str,
    is_remote: bool = False,
    experience: int = 1,
    max_results: int = 50,
    headless: bool = True,
) -> list[dict]:
    """
    Scrape Naukri.com job listings using Selenium.

    Args:
        search_terms: List of job title search terms
        location: City/region to search in
        is_remote: Whether to filter for remote jobs
        experience: Years of experience filter (Naukri uses integer)
        max_results: Maximum number of results to return
        headless: Run Chrome in headless mode (no window)

    Returns:
        List of job dicts with standardized fields
    """
    driver = _create_driver(headless=headless)
    all_jobs = []

    try:
        for term in search_terms:
            if len(all_jobs) >= max_results:
                break
            jobs = _search_term_naukri(driver, term, location, is_remote, experience, max_results)
            all_jobs.extend(jobs)
            time.sleep(2)   # Polite delay between searches
    finally:
        driver.quit()

    # Deduplicate by job URL
    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("job_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    logger.info(f"Naukri: Found {len(unique_jobs)} unique jobs across {len(search_terms)} search terms")
    return unique_jobs[:max_results]


def _create_driver(headless: bool = True) -> webdriver.Chrome:
    """Create and configure a Chrome WebDriver instance."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=3")          # suppress Chrome internal logs
    options.add_argument("--silent")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=en-US")

    # Redirect chromedriver's own stdout/stderr to devnull to suppress
    # "DevTools listening on ws://..." and other internal messages
    service = Service(log_output=os.devnull)

    driver = webdriver.Chrome(options=options, service=service)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def _search_term_naukri(
    driver: webdriver.Chrome,
    search_term: str,
    location: str,
    is_remote: bool,
    experience: int,
    max_results: int,
) -> list[dict]:
    """Scrape Naukri for a single search term."""
    jobs = []
    url = _build_naukri_url(search_term, location if not is_remote else "india", experience)

    try:
        driver.get(url)
        time.sleep(3)

        # Wait for job cards to load — try current selectors first, then fallbacks
        card_selector = None
        for selector in [
            "div.srp-jobtuple-wrapper",
            "div[class*='srp-jobtuple']",
            ".job-tuple-wrapper",
        ]:
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                card_selector = selector
                break
            except TimeoutException:
                continue

        if not card_selector:
            logger.warning(f"Naukri: No job cards found for '{search_term}' in '{location}'")
            return []

        # Collect job cards using the confirmed working selector
        job_cards = driver.find_elements(By.CSS_SELECTOR, card_selector)
        logger.info(f"Naukri: Found {len(job_cards)} cards for '{search_term}'")

        for card in job_cards[:max_results]:
            job = _parse_job_card(card, search_term)
            if job:
                # Filter: only last 24 hours
                if _is_within_24_hours(job.get("_posted_datetime")):
                    jobs.append(job)

    except Exception as e:
        logger.error(f"Naukri scrape error for '{search_term}': {e}")

    return jobs


def _parse_job_card(card, search_term: str) -> Optional[dict]:
    """Extract job data from a single Naukri job card element."""
    def safe_text(*selectors: str) -> str:
        """Try each selector in order, return first non-empty match."""
        for sel in selectors:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                t = el.text.strip()
                if t:
                    return t
            except NoSuchElementException:
                continue
        return ""

    def safe_attr(*selectors_and_attr) -> str:
        """selectors_and_attr = (*selectors, attr_name). Try each selector."""
        *selectors, attr = selectors_and_attr
        for sel in selectors:
            try:
                val = card.find_element(By.CSS_SELECTOR, sel).get_attribute(attr) or ""
                if val:
                    return val
            except NoSuchElementException:
                continue
        return ""

    try:
        # ── Title & URL ─────────────────────────────────────────────────────
        title = safe_text(
            "a.title", "a[class*='title']", ".jobTitle", ".title",
        )
        job_url = safe_attr(
            "a.title", "a[class*='title']", ".jobTitle",
            "href",
        )

        # ── Company ─────────────────────────────────────────────────────────
        company = safe_text(
            ".comp-name", "a.comp-name", ".subTitle",
            "[class*='comp-name']", ".company-name",
        )

        # ── Location ────────────────────────────────────────────────────────
        location = safe_text(
            "span.loc-item", "[class*='loc-item']",
            ".locWdth", "span.location", ".location span",
        )

        # ── Experience ──────────────────────────────────────────────────────
        experience = safe_text(
            ".exp-wrap span", "[class*='exp']", ".experience span", ".expwdth",
        )

        # ── Salary ──────────────────────────────────────────────────────────
        salary = safe_text(
            ".sal-wrap span", ".sal-mnth", "[class*='sal']",
            ".salary span", ".salwdth",
        )

        # ── Posted time ─────────────────────────────────────────────────────
        posted_str = safe_text(
            "span.job-post-day", "[class*='job-post-day']",
            ".job-post-age", ".postAge", ".date",
            ".jobTupleHeader .type", ".fresh-relevance-list span",
        )
        posted_dt = _parse_posted_time(posted_str)

        if not title or not job_url:
            return None

        return {
            "title": title,
            "company": company,
            "location": location,
            "min_amount": None,
            "max_amount": None,
            "salary_string": salary,
            "job_url": job_url,
            "description": "",
            "date_posted": posted_dt.date() if posted_dt else None,
            "source": "naukri",
            "search_term": search_term,
            "_posted_datetime": posted_dt,
            "is_remote": "remote" in location.lower() or "work from home" in location.lower(),
        }

    except Exception as e:
        logger.debug(f"Failed to parse Naukri card: {e}")
        return None
