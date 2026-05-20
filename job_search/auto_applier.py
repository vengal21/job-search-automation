import logging
import os
import time
from typing import Callable

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import NAUKRI_EMAIL, NAUKRI_PASSWORD
from models import SessionLocal, UserAnswer

from linkedin_applier import auto_apply_linkedin
from indeed_applier import auto_apply_indeed
from glassdoor_applier import auto_apply_glassdoor
from llm_helper import get_answer_from_llm

logger = logging.getLogger(__name__)

def auto_apply_all(jobs: list[dict], profile: dict, ask_user_callback: Callable[[str], str], emit_callback: Callable[[str, int], None], check_cancel: Callable[[], bool] = None) -> None:
    """
    Orchestrate auto-apply for all supported platforms (Naukri, LinkedIn, Indeed, Glassdoor).
    """
    emit_callback("Starting automated application process...", 88)
    
    options = webdriver.ChromeOptions()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    service = Service(log_output=os.devnull)
    driver = None
    
    try:
        driver = webdriver.Chrome(options=options, service=service)
        
        # 1. Naukri
        auto_apply_naukri(jobs, profile, ask_user_callback, emit_callback, check_cancel, driver)
        if check_cancel and check_cancel(): return
        
        # 2. LinkedIn
        auto_apply_linkedin(jobs, profile, ask_user_callback, emit_callback, check_cancel, driver)
        if check_cancel and check_cancel(): return
        
        # 3. Indeed
        auto_apply_indeed(jobs, profile, ask_user_callback, emit_callback, check_cancel, driver)
        if check_cancel and check_cancel(): return
        
        # 4. Glassdoor
        auto_apply_glassdoor(jobs, profile, ask_user_callback, emit_callback, check_cancel, driver)
        
    except Exception as e:
        logger.error(f"Global auto-apply orchestrator crashed: {e}")
    finally:
        if driver:
            driver.quit()
        emit_callback("Finished all auto-apply processes.", 98)

def auto_apply_naukri(jobs: list[dict], profile: dict, ask_user_callback: Callable[[str], str], emit_callback: Callable[[str, int], None], check_cancel: Callable[[], bool], driver: webdriver.Chrome) -> None:
    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        emit_callback("Naukri credentials not found. Skipping.", 89)
        return

    naukri_jobs = [j for j in jobs if j.get("source", "").lower() == "naukri" and j.get("job_url")]
    if not naukri_jobs:
        return

    emit_callback(f"Starting Naukri apply for {len(naukri_jobs)} jobs...", 89)

    try:
        driver.get("https://login.naukri.com/")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "usernameField"))).send_keys(NAUKRI_EMAIL)
            driver.find_element(By.ID, "passwordField").send_keys(NAUKRI_PASSWORD)
            driver.find_element(By.XPATH, "//button[contains(text(), 'Login')]").click()
            time.sleep(5)
            if "login" in driver.current_url:
                emit_callback("Naukri login failed (possible captcha).", 90)
                return
        except Exception:
            return

        db = SessionLocal() if SessionLocal else None
        
        for index, job in enumerate(naukri_jobs):
            if check_cancel and check_cancel(): break
            emit_callback(f"Applying to Naukri: {job.get('title')}...", 90)
            
            try:
                driver.get(job["job_url"])
                time.sleep(3)
                
                # Ensure the apply button exists and is internal (not redirecting externally immediately)
                # For Naukri, apply buttons on site are usually internal.
                apply_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Apply') or contains(text(), 'Apply on Company Website')]")
                
                if not apply_btns:
                    continue
                    
                btn_text = apply_btns[0].text.strip().lower()
                if "company website" in btn_text:
                    logger.info(f"External apply for {job['title']}. Skipping.")
                    job["applied_status"] = False
                    continue
                
                apply_btns[0].click()
                time.sleep(3)
                
                question_elements = driver.find_elements(By.CSS_SELECTOR, ".botItem .questionText")
                if question_elements:
                    for q_el in question_elements:
                        question_text = q_el.text.strip()
                        if not question_text: continue
                        
                        answer = ""
                        if db:
                            saved = db.query(UserAnswer).filter(UserAnswer.question_text == question_text).first()
                            if saved: answer = saved.answer_text
                        
                        if not answer:
                            # Use LLM here
                            answer = get_answer_from_llm(question_text, profile)
                        
                        if not answer:
                            answer = ask_user_callback(question_text)
                            if answer and db:
                                db.add(UserAnswer(question_text=question_text, answer_text=answer))
                                db.commit()
                        time.sleep(1)
                
                job["applied_status"] = True
            except Exception:
                job["applied_status"] = False
                
        if db:
            db.close()
    except Exception as e:
        logger.error(f"Naukri process error: {e}")
