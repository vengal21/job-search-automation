import logging
import time
from typing import Callable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD
from models import SessionLocal, UserAnswer
from llm_helper import get_answer_from_llm

logger = logging.getLogger(__name__)

def auto_apply_linkedin(
    jobs: list[dict],
    profile: dict,
    ask_user_callback: Callable[[str], str],
    emit_callback: Callable[[str, int], None],
    check_cancel: Callable[[], bool] = None,
    driver: webdriver.Chrome = None
) -> None:
    if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
        emit_callback("LinkedIn credentials missing. Skipping LinkedIn auto-apply.", 90)
        return

    linkedin_jobs = [j for j in jobs if j.get("source", "").lower() == "linkedin" and j.get("job_url")]
    if not linkedin_jobs:
        return

    emit_callback(f"Checking {len(linkedin_jobs)} LinkedIn jobs for Easy Apply...", 90)

    try:
        # 1. Login
        driver.get("https://www.linkedin.com/login")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username"))).send_keys(LINKEDIN_EMAIL)
        driver.find_element(By.ID, "password").send_keys(LINKEDIN_PASSWORD)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        time.sleep(3)
        if "login" in driver.current_url:
            emit_callback("LinkedIn login failed or requires CAPTCHA.", 92)
            return
        
        emit_callback("Successfully logged into LinkedIn.", 92)
        
        db = SessionLocal() if SessionLocal else None
        
        for index, job in enumerate(linkedin_jobs):
            if check_cancel and check_cancel(): break
            pct = 92 + int((index / len(linkedin_jobs)) * 6)
            emit_callback(f"Checking LinkedIn: {job.get('title')}...", pct)
            
            try:
                driver.get(job["job_url"])
                time.sleep(3)
                
                # Check for Easy Apply
                easy_apply_btns = driver.find_elements(By.XPATH, "//button[contains(@class, 'jobs-apply-button') and contains(., 'Easy Apply')]")
                
                if not easy_apply_btns:
                    logger.info(f"No Easy Apply for {job['title']}")
                    continue
                
                emit_callback(f"Easy Apply found for: {job['title']}! Applying...", pct)
                easy_apply_btns[0].click()
                time.sleep(2)
                
                # Handle modals
                _handle_linkedin_modals(driver, profile, ask_user_callback, db, check_cancel)
                
                job["applied_status"] = True
                
            except Exception as e:
                logger.warning(f"Failed LinkedIn apply for {job.get('title')}: {e}")
                job["applied_status"] = False

        if db:
            db.close()

    except Exception as e:
        logger.error(f"LinkedIn auto-apply crashed: {e}")

def _handle_linkedin_modals(driver, profile, ask_user_callback, db, check_cancel):
    # This is a robust conceptual loop for LinkedIn's multi-step modal
    max_steps = 10
    step = 0
    while step < max_steps:
        if check_cancel and check_cancel(): break
        time.sleep(2)
        
        # Check if submit button is visible
        submit_btns = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Submit application')]")
        if submit_btns:
            submit_btns[0].click()
            time.sleep(2)
            return # Done
            
        # Or next button
        next_btns = driver.find_elements(By.XPATH, "//button[contains(@aria-label, 'Continue to next step')]")
        
        # Find questions on this page and answer them
        _answer_visible_questions(driver, profile, ask_user_callback, db)
        
        if next_btns:
            next_btns[0].click()
            step += 1
        else:
            break

def _answer_visible_questions(driver, profile, ask_user_callback, db):
    # Proof of concept for interacting with form fields
    form_groups = driver.find_elements(By.CSS_SELECTOR, ".jobs-easy-apply-form-section__grouping")
    for group in form_groups:
        try:
            label = group.find_element(By.TAG_NAME, "label").text.strip()
            inputs = group.find_elements(By.TAG_NAME, "input")
            if not inputs:
                continue
                
            input_el = inputs[0]
            if input_el.get_attribute("value"):
                continue # Already filled (e.g. by default profile)
                
            # Ask DB or LLM or User
            answer = ""
            if db:
                saved = db.query(UserAnswer).filter(UserAnswer.question_text == label).first()
                if saved:
                    answer = saved.answer_text
            
            if not answer:
                answer = get_answer_from_llm(label, profile)
                
            if not answer:
                answer = ask_user_callback(label)
                if answer and db:
                    db.add(UserAnswer(question_text=label, answer_text=answer))
                    db.commit()
            
            if answer:
                input_el.send_keys(answer)
        except Exception:
            pass
