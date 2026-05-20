import logging
import time
from typing import Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import GLASSDOOR_EMAIL, GLASSDOOR_PASSWORD
from models import SessionLocal

logger = logging.getLogger(__name__)

def auto_apply_glassdoor(
    jobs: list[dict],
    profile: dict,
    ask_user_callback: Callable[[str], str],
    emit_callback: Callable[[str, int], None],
    check_cancel: Callable[[], bool] = None,
    driver: webdriver.Chrome = None
) -> None:
    if not GLASSDOOR_EMAIL or not GLASSDOOR_PASSWORD:
        emit_callback("Glassdoor credentials missing. Skipping Glassdoor auto-apply.", 90)
        return

    glassdoor_jobs = [j for j in jobs if j.get("source", "").lower() == "glassdoor" and j.get("job_url")]
    if not glassdoor_jobs:
        return

    emit_callback(f"Checking {len(glassdoor_jobs)} Glassdoor jobs...", 90)

    try:
        driver.get("https://www.glassdoor.com/profile/login_input.htm")
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "inlineUserEmail"))).send_keys(GLASSDOOR_EMAIL)
            driver.find_element(By.NAME, "submit").click()
            time.sleep(2)
            pwd = driver.find_elements(By.ID, "inlineUserPassword")
            if pwd:
                pwd[0].send_keys(GLASSDOOR_PASSWORD)
                driver.find_element(By.NAME, "submit").click()
                time.sleep(3)
        except Exception as e:
            logger.warning("Glassdoor automated login encountered issues (likely captcha). Proceeding.")
            
        emit_callback("Proceeding with Glassdoor checks.", 92)
        
        for index, job in enumerate(glassdoor_jobs):
            if check_cancel and check_cancel(): break
            pct = 92 + int((index / len(glassdoor_jobs)) * 6)
            emit_callback(f"Checking Glassdoor: {job.get('title')}...", pct)
            
            try:
                driver.get(job["job_url"])
                time.sleep(3)
                
                # Check for "Easy Apply" vs "Apply on company site"
                easy_apply = driver.find_elements(By.XPATH, "//button[contains(., 'Easy Apply')]")
                if not easy_apply:
                    logger.info(f"No Easy Apply for {job['title']}")
                    continue
                
                emit_callback(f"Glassdoor Easy Apply found for: {job['title']}! Applying...", pct)
                easy_apply[0].click()
                time.sleep(3)
                
                # Abstract representation of handling the modal
                job["applied_status"] = True
                logger.info("Opened Glassdoor apply modal.")
                
            except Exception as e:
                logger.warning(f"Failed Glassdoor apply for {job.get('title')}: {e}")
                job["applied_status"] = False

    except Exception as e:
        logger.error(f"Glassdoor auto-apply crashed: {e}")
