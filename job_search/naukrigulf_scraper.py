# =============================================================================
# naukrigulf_scraper.py — Selenium-based Naukrigulf.com job scraper
# =============================================================================

import time
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)

NAUKRIGULF_BASE = "https://www.naukrigulf.com"

def _build_naukrigulf_url(search_term: str, location: str) -> str:
    """Build a Naukrigulf search URL."""
    import urllib.parse
    encoded_term = urllib.parse.quote_plus(search_term.strip())
    
    if location and location.lower() not in ["india", "worldwide", "remote", "abroad", "any", "gulf"]:
        # Slugify location: e.g. "Dubai" -> "dubai", "Saudi Arabia" -> "saudi-arabia"
        location_slug = location.split(",")[0].strip().lower().replace(" ", "-")
        url = f"{NAUKRIGULF_BASE}/jobs-in-{location_slug}?searchText={encoded_term}"
    else:
        url = f"{NAUKRIGULF_BASE}/jobs?searchText={encoded_term}"
        
    logger.debug(f"Naukri Gulf URL: {url}")
    return url

def _parse_posted_time(time_str: str) -> Optional[datetime]:
    """Parse Naukrigulf's posted time string into a datetime."""
    if not time_str:
        return None
    time_str = time_str.lower().strip()
    now = datetime.now()
    try:
        if "few" in time_str or "just" in time_str or "minute" in time_str or "now" in time_str:
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
        else:
            # Check for direct date like "11 May" or "11 May 2026"
            # Format: "%d %b" or "%d %b %Y"
            match = re.search(r'(\d+)\s+([a-zA-Z]{3})', time_str)
            if match:
                day = int(match.group(1))
                month_str = match.group(2)
                months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
                if month_str in months:
                    month = months.index(month_str) + 1
                    year = now.year
                    # If month is in future (e.g. Dec and current is Jan), assume previous year
                    if month > now.month:
                        year -= 1
                    return datetime(year=year, month=month, day=day)
    except Exception as e:
        logger.debug(f"Naukrigulf date parse error: {e}")
    return None

def _is_within_24_hours(posted_time: Optional[datetime]) -> bool:
    """Return True if the job was posted within the last 24 hours."""
    if posted_time is None:
        return True  # Include if we can't determine
    return (datetime.now() - posted_time).total_seconds() <= 86400

def _create_driver(headless: bool = True) -> webdriver.Chrome:
    """Create and configure a Chrome WebDriver instance."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=3")
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

    service = Service(log_output=os.devnull)
    driver = webdriver.Chrome(options=options, service=service)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def scrape_naukrigulf(
    search_terms: list[str],
    location: str,
    max_results: int = 50,
    headless: bool = True,
) -> list[dict]:
    """Scrape Naukrigulf.com job listings using Selenium."""
    driver = _create_driver(headless=headless)
    all_jobs = []

    try:
        for term in search_terms:
            if len(all_jobs) >= max_results:
                break
            jobs = _search_term_naukrigulf(driver, term, location, max_results)
            all_jobs.extend(jobs)
            time.sleep(2)
    finally:
        driver.quit()

    seen_urls = set()
    unique_jobs = []
    for job in all_jobs:
        url = job.get("job_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)

    logger.info(f"Naukrigulf: Found {len(unique_jobs)} unique jobs across {len(search_terms)} search terms")
    return unique_jobs[:max_results]

def _search_term_naukrigulf(
    driver: webdriver.Chrome,
    search_term: str,
    location: str,
    max_results: int,
) -> list[dict]:
    """Scrape Naukrigulf for a single search term."""
    jobs = []
    url = _build_naukrigulf_url(search_term, location)

    try:
        driver.get(url)
        time.sleep(4)

        # Wait for srp-tuple card to load
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.srp-tuple"))
            )
        except TimeoutException:
            logger.warning(f"Naukrigulf: No job cards loaded for '{search_term}' @ '{location}'")
            return []

        job_cards = driver.find_elements(By.CSS_SELECTOR, "div.srp-tuple")
        logger.info(f"Naukrigulf: Found {len(job_cards)} cards for '{search_term}'")

        for card in job_cards[:max_results]:
            job = _parse_job_card(card, search_term)
            if job:
                if _is_within_24_hours(job.get("_posted_datetime")):
                    jobs.append(job)

    except Exception as e:
        logger.error(f"Naukrigulf scrape error for '{search_term}': {e}")

    return jobs

def _parse_job_card(card, search_term: str) -> Optional[dict]:
    """Extract job data from a single Naukrigulf job card element."""
    def safe_text(*selectors: str) -> str:
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
        title = safe_text("p.designation-title", ".designation-title", "a.info-position")
        job_url = safe_attr("a.info-position", "a[class*='info-position']", "href")
        
        company = safe_text("p.info-org", ".info-org", ".company-name")
        location = safe_text("li.info-loc span:not(.ico)", "li.info-loc", ".info-loc")
        experience = safe_text("li.info-exp span:not(.ico)", "li.info-exp", ".info-exp")
        description = safe_text("p.description", ".description", ".job-desc")
        
        posted_str = safe_text("span.time", ".time", ".date")
        posted_dt = _parse_posted_time(posted_str)

        if not title or not job_url:
            return None

        # Build absolute URL if relative
        if job_url.startswith("/"):
            job_url = f"{NAUKRIGULF_BASE}{job_url}"

        return {
            "title": title,
            "company": company,
            "location": location,
            "min_amount": None,
            "max_amount": None,
            "salary_string": experience, # Use experience as salary string / metadata helper on Naukrigulf
            "job_url": job_url,
            "description": description,
            "date_posted": posted_dt.date() if posted_dt else None,
            "source": "naukrigulf",
            "search_term": search_term,
            "_posted_datetime": posted_dt,
            "is_remote": "remote" in location.lower() or "work from home" in location.lower(),
        }

    except Exception as e:
        logger.debug(f"Failed to parse Naukrigulf card: {e}")
        return None
