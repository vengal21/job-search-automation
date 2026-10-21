"""Visible-browser form assistance that always leaves final submission to the user."""
from __future__ import annotations

import re
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "data_folder" / "plain_text_resume.yaml"
RESUME_PATH = Path(os.environ.get("JOB_BOT_RESUME_PATH", str(ROOT / "data_folder" / "resume.pdf")))
BROWSER_PROFILE = ROOT / "chrome_profile" / "job_bot_manual"
load_dotenv(ROOT / ".env")
GOOGLE_LOGIN_EMAIL = os.environ.get("JOB_BOT_LOGIN_EMAIL", "").strip()


def _read_profile() -> dict:
    data = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("personal_information"), dict):
        raise ValueError("The résumé profile is missing personal_information fields.")
    return data


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()


def _value_for(label: str, control_type: str, profile: dict):
    """Return a known résumé value only; never infer demographic/legal answers."""
    info = profile.get("personal_information", {})
    exp = (profile.get("experience_details") or [{}])[0]
    education = (profile.get("education_details") or [{}])[0]
    text = _norm(label)
    if not text:
        return None

    if re.search(r"\b(email|e mail)\b", text):
        return info.get("email")
    if re.search(r"\b(phone|mobile|telephone)\b", text):
        phone = str(info.get("phone", ""))
        prefix = str(info.get("phone_prefix", ""))
        return f"{prefix} {phone}".strip() if control_type != "tel" else phone
    if re.search(r"\b(first name|given name)\b", text):
        return info.get("name")
    if re.search(r"\b(last name|surname|family name)\b", text):
        return info.get("surname")
    if re.search(r"\b(full name|your name|applicant name)\b", text) or text in {"name", "legal name"}:
        return " ".join(str(info.get(k, "")).strip() for k in ("name", "surname") if info.get(k))
    if re.search(r"\b(linkedin)\b", text):
        return info.get("linkedin")
    if re.search(r"\b(github|git hub)\b", text):
        return info.get("github")
    if re.search(r"\b(postal code|zip code|postcode|pincode)\b", text):
        return info.get("zip_code")
    if re.search(r"\b(citizenship|nationality|country of birth|work authorization|visa|sponsorship)\b", text):
        return None
    if re.search(r"\b(country of residence|current country)\b", text) or text == "country":
        return info.get("country")
    if re.search(r"\b(city|current location|current city)\b", text):
        return info.get("city")
    if re.search(r"\b(address|street address)\b", text):
        return info.get("address")
    if re.search(r"\b(current employer|current company|present employer)\b", text):
        return exp.get("company")
    if re.search(r"\b(current job title|current role|present title)\b", text):
        return exp.get("position")
    if text in {"years of experience", "year of experience", "total experience", "overall experience"}:
        if control_type == "number":
            return "1.83"
        return "1 year 10 months"
    if re.search(r"\b(university|school|college|institution)\b", text):
        return education.get("institution")
    if re.search(r"\b(degree|education level)\b", text):
        return education.get("education_level")
    if re.search(r"\b(field of study|major|study area)\b", text):
        return education.get("field_of_study")
    if re.search(r"\b(graduation year|year of completion)\b", text):
        return education.get("year_of_completion")
    if re.search(r"\b(professional summary|profile summary|summary)\b", text):
        return profile.get("summary")
    if re.search(r"\b(skills|key skills)\b", text):
        skills = profile.get("skills", {})
        flattened = []
        for value in skills.values():
            if isinstance(value, list):
                flattened.extend(map(str, value))
        return ", ".join(dict.fromkeys(flattened))
    return None


class ManualApplySession:
    """Controls one visible Chrome session; every site action is inspectable."""

    def __init__(self):
        self._lock = threading.RLock()
        self.driver = None
        self.jobs = []
        self.index = 0
        self._job_window_handle = None
        self.phase = "idle"
        self.message = ""
        self.filled = []
        self.missing = []
        self.profile = None
        self.resume_path = RESUME_PATH if RESUME_PATH.is_file() else None

    def payload(self) -> dict:
        with self._lock:
            current = self.jobs[self.index] if self.jobs and self.index < len(self.jobs) else None
            return {
                "active": self.phase not in {"idle", "complete", "stopped", "error"},
                "phase": self.phase,
                "message": self.message,
                "index": min(self.index + 1, len(self.jobs)) if self.jobs else 0,
                "total": len(self.jobs),
                "title": current.get("title", "") if current else "",
                "company": current.get("company", "") if current else "",
                "source": current.get("source", "") if current else "",
                "filled": list(self.filled),
                "needsYourAnswer": list(self.missing),
                "resumeAvailable": bool(self.resume_path),
            }

    def start(self, jobs: list[dict]) -> dict:
        with self._lock:
            if self.phase not in {"idle", "complete", "stopped", "error"}:
                raise ValueError("An application preparation session is already active.")
            self._close_driver()
            self.profile = _read_profile()
            BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
            options = webdriver.ChromeOptions()
            options.add_argument(f"--user-data-dir={BROWSER_PROFILE}")
            options.add_argument("--start-maximized")
            options.add_experimental_option("prefs", {"credentials_enable_service": False})
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(35)
            self.jobs = list(jobs)
            self.index = 0
            self.filled = []
            self.missing = []
            self._open_current()
            # If the user is already signed in, begin preparing the first form immediately.
            return self.fill_current_page()

    def fill_current_page(self) -> dict:
        with self._lock:
            self._require_driver()
            self._restore_job_window_if_closed()
            self.filled = []
            self.missing = []
            try:
                reopened_after_login = False
                for _ in range(8):
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text[:5000].casefold()
                    if self._posting_unavailable(page_text):
                        self.phase = "needs_user_input"
                        self.message = "This posting looks closed or unavailable. Choose Skip this job to continue; it will not be counted as an application."
                        return self.payload()
                    if self._is_linkedin_feed_landing():
                        if not reopened_after_login:
                            self._reopen_selected_posting()
                            reopened_after_login = True
                            time.sleep(1)
                            continue
                        self.phase = "waiting_for_user"
                        self.message = "LinkedIn returned to the feed instead of this posting. The selected job was reopened once; open its posting from the dashboard while signed in, then choose Continue."
                        return self.payload()
                    if self._login_page(page_text):
                        self.phase = "waiting_for_user"
                        login_action = self._continue_google_login()
                        if login_action == "selected":
                            self.message = f"Selected {GOOGLE_LOGIN_EMAIL} in Google. Finish any password, verification, or consent prompt yourself, then choose Continue. Gogoi never enters credentials or accepts permissions."
                        elif login_action == "opened":
                            self.message = f"Opened Google sign-in. Choose {GOOGLE_LOGIN_EMAIL} if Google offers it. If it asks for a password, verification, or consent, complete that yourself, then choose Continue."
                        elif login_action == "google_waiting":
                            self.message = f"Google sign-in is open, but {GOOGLE_LOGIN_EMAIL} is not available in Gogoi's Chrome profile. Sign in with that account in this Chrome window, then choose Continue."
                        else:
                            self.message = f"Sign in in Gogoi's Chrome window with {GOOGLE_LOGIN_EMAIL}, then choose Continue. This is a separate saved Chrome profile, so sign in once here. Passwords and login fields are never filled."
                        return self.payload()

                    if not self._has_application_context() and self._click_apply_entry():
                        time.sleep(1.5)
                        continue
                    controls = self._form_controls()
                    if not controls:
                        if self._click_apply_entry():
                            time.sleep(2)
                            continue
                        self.phase = "waiting_for_user"
                        self.message = "Open the job’s application form in Chrome, then choose Continue. It may need a manual step."
                        return self.payload()

                    self._fill_controls(controls)
                    self.missing = self._required_fields_left()
                    if self.missing:
                        self.phase = "needs_user_input"
                        self.message = "Some required fields are not in your saved profile. Answer them in Chrome, then choose Continue."
                        return self.payload()

                    if self._has_final_submit():
                        self.phase = "awaiting_review"
                        self.message = "Form filled. Review it in Chrome and submit it yourself. The bot will not click Submit."
                        return self.payload()

                    if self._has_application_context() and self._click_safe_next():
                        time.sleep(1.2)
                        continue

                    self.phase = "needs_user_input"
                    self.message = "Continue through this page manually in Chrome, then choose Continue. The helper will stop before the final Submit."
                    return self.payload()

                self.phase = "needs_user_input"
                self.message = "Continue through the open form manually in Chrome, then choose Continue."
            except WebDriverException as exc:
                self.phase = "error"
                self.message = f"The browser could not prepare this form: {exc.msg[:250]}"
            return self.payload()

    def _is_linkedin_feed_landing(self) -> bool:
        current = urlsplit(self.driver.current_url)
        host = (current.hostname or "").casefold()
        if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
            return False
        if not self.jobs or self.index >= len(self.jobs):
            return False
        target_host = (urlsplit(str(self.jobs[self.index].get("link", ""))).hostname or "").casefold()
        if not (target_host == "linkedin.com" or target_host.endswith(".linkedin.com")):
            return False
        path = (current.path or "/").casefold().rstrip("/") or "/"
        return path == "/" or path.startswith(("/feed", "/mynetwork", "/messaging", "/notifications", "/in/"))

    def _reopen_selected_posting(self):
        if not self.jobs or self.index >= len(self.jobs):
            return
        link = str(self.jobs[self.index].get("link", ""))
        target = urlsplit(link)
        host = (target.hostname or "").casefold()
        if (target.scheme in {"http", "https"}
                and (host == "linkedin.com" or host.endswith(".linkedin.com"))):
            self.driver.get(link)
            self._job_window_handle = self.driver.current_window_handle

    def submitted_and_next(self) -> dict:
        with self._lock:
            self._require_driver()
            if self.phase != "awaiting_review":
                raise ValueError("The application is not at the final review step yet.")
            job = self.jobs[self.index]
            self._write_outcome(job, "Applied", "User confirmed manual submission in the browser.")
            return self._advance("You confirmed submission. Opening the next selected posting.")

    def skip_and_next(self) -> dict:
        with self._lock:
            self._require_driver()
            job = self.jobs[self.index]
            self._write_outcome(job, "Skipped", "User skipped this posting in the browser workflow.")
            return self._advance("Posting skipped. Opening the next selected job.")

    def stop(self) -> dict:
        with self._lock:
            self._close_driver()
            self.phase = "stopped"
            self.message = "Application preparation stopped. No final Submit action was performed by the bot."
            return self.payload()

    def _open_current(self):
        if self.index >= len(self.jobs):
            self._close_driver()
            self.phase = "complete"
            self.message = "Finished the selected application queue. Check the dashboard statuses for your confirmed submissions and skipped jobs."
            return
        job = self.jobs[self.index]
        link = str(job.get("link", ""))
        if urlsplit(link).scheme not in {"http", "https"}:
            raise ValueError("A selected job has an invalid posting URL.")
        self.driver.get(link)
        self._job_window_handle = self.driver.current_window_handle
        self.phase = "waiting_for_user"
        self.message = f"Posting opened in Gogoi's saved Chrome profile. If a Google sign-in offers {GOOGLE_LOGIN_EMAIL}, Gogoi will select that account; complete any password, verification, or consent prompt yourself. The helper will fill known profile details and stop before Submit."
        self.filled = []
        self.missing = []

    def _advance(self, message: str):
        self.index += 1
        self._open_current()
        if self.phase != "complete":
            # Reuse the signed-in browser and prepare the next selected posting automatically.
            self.fill_current_page()
            self.message = f"{message} Next job: {self.message}"
            return self.payload()
        return self.payload()

    def _require_driver(self):
        if self.driver is None or self.phase in {"idle", "complete", "stopped", "error"}:
            raise ValueError("Start a browser application session first.")

    def _restore_job_window_if_closed(self):
        if self.driver is None:
            return
        try:
            handles = self.driver.window_handles
            current = self.driver.current_window_handle
            if current not in handles and self._job_window_handle in handles:
                self.driver.switch_to.window(self._job_window_handle)
        except WebDriverException:
            try:
                handles = self.driver.window_handles
                if self._job_window_handle in handles:
                    self.driver.switch_to.window(self._job_window_handle)
            except WebDriverException:
                pass

    def _close_driver(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None

    def _login_page(self, body_text: str) -> bool:
        if self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'):
            return True
        host = (urlsplit(self.driver.current_url).hostname or "").casefold()
        if host.endswith("google.com") and any(marker in body_text[:1500] for marker in ("verify it’s you", "verify it's you", "2-step verification", "2 step verification", "choose an account", "sign in to continue")):
            return True
        return any(marker in body_text[:1000] for marker in ("sign in to", "log in to", "join now", "sign in to apply"))

    def _continue_google_login(self) -> str | None:
        """Open Google sign-in and select only the explicitly configured account."""
        original_handle = self.driver.current_window_handle
        try:
            # If a Google account chooser is already open, select only the exact email.
            google_handles = []
            for handle in self.driver.window_handles:
                self.driver.switch_to.window(handle)
                host = (urlsplit(self.driver.current_url).hostname or "").casefold()
                if host == "accounts.google.com" or host.endswith(".accounts.google.com"):
                    google_handles.append(handle)
                    if self._select_google_account():
                        return "selected"
            if google_handles:
                self.driver.switch_to.window(google_handles[0])
                return "google_waiting"

            # Click only an explicit Google sign-in action on the current login page.
            self.driver.switch_to.window(original_handle)
            for element in self.driver.find_elements(By.CSS_SELECTOR, "button, [role='button'], a"):
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    text = _norm(element.text or element.get_attribute("aria-label") or "")
                    if text not in {"continue with google", "sign in with google", "log in with google"}:
                        continue
                    before = set(self.driver.window_handles)
                    element.click()
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        handles = set(self.driver.window_handles)
                        new_handles = handles - before
                        if new_handles:
                            self.driver.switch_to.window(next(iter(new_handles)))
                        host = (urlsplit(self.driver.current_url).hostname or "").casefold()
                        if host == "accounts.google.com" or host.endswith(".accounts.google.com"):
                            if self._select_google_account():
                                return "selected"
                            return "google_waiting"
                        time.sleep(0.25)
                    return "opened"
                except WebDriverException:
                    continue
        except WebDriverException:
            pass
        return None

    def _select_google_account(self) -> bool:
        """Click the account row only when its visible identity exactly matches."""
        matches = self.driver.execute_script(r"""
        const target = arguments[0].toLowerCase();
        const visible = el => {
          const r = el.getBoundingClientRect(), s = getComputedStyle(el);
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const nodes = Array.from(document.querySelectorAll(
          '[data-identifier], [data-email], [role="button"], [role="link"], button, a, li'
        )).filter(visible);
        return nodes.filter(el => {
          const identity = [el.getAttribute('data-identifier'), el.getAttribute('data-email'), el.innerText]
            .filter(Boolean).join(' ').toLowerCase();
          const explicit = [el.getAttribute('data-identifier'), el.getAttribute('data-email')]
            .filter(Boolean).map(value => value.trim().toLowerCase());
          const emails = identity.match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/g) || [];
          return explicit.includes(target) || emails.includes(target);
        }).sort((a, b) => a.getBoundingClientRect().width * a.getBoundingClientRect().height
                         - b.getBoundingClientRect().width * b.getBoundingClientRect().height);
        """, GOOGLE_LOGIN_EMAIL)
        if not matches:
            return False
        for element in matches:
            try:
                element.click()
                return True
            except WebDriverException:
                continue
        return False

    @staticmethod
    def _posting_unavailable(body_text: str) -> bool:
        text = _norm(body_text)
        markers = (
            "no longer accepting applications",
            "job posting is no longer available",
            "this job is no longer available",
            "this position has been filled",
            "job is closed",
            "job has expired",
            "job posting has expired",
            "couldn t find anything here",
            "404 error",
        )
        return any(marker in text for marker in markers)

    def _form_controls(self):
        script = r"""
        return Array.from(document.querySelectorAll('input, textarea, select')).filter(el => {
          const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.disabled && !el.readOnly;
        }).map(el => {
          const labels = Array.from(el.labels || []).map(label => label.innerText || '').join(' ');
          const parent = el.closest('label')?.innerText || el.parentElement?.innerText || '';
          const label = labels || el.getAttribute('aria-label') || el.placeholder || el.name || el.id || parent.slice(0,120);
          return {element:el, tag:el.tagName.toLowerCase(), type:(el.type || '').toLowerCase(), name:el.name || '', id:el.id || '', label, required:el.required || el.getAttribute('aria-required') === 'true', value:el.value || ''};
        });
        """
        return self.driver.execute_script(script)

    def _has_application_context(self) -> bool:
        if re.search(r"/(apply|application)(/|\?|$)", urlsplit(self.driver.current_url).path, re.I):
            return True
        if any(dialog.is_displayed() for dialog in self.driver.find_elements(By.CSS_SELECTOR, '[role="dialog"]')):
            return True
        return any(
            info.get("type") == "file"
            or re.search(r"\b(application|resume|curriculum vitae|cover letter|work authorization|email|phone|first name|last name)\b", _norm(str(info.get("label", ""))))
            for info in self._form_controls()
        )

    def _fill_controls(self, controls):
        for info in controls:
            label = str(info.get("label", ""))
            kind = info.get("type") or info.get("tag")
            element = info.get("element")
            if kind in {"password", "hidden", "checkbox", "radio", "submit", "button", "reset"}:
                continue
            if kind == "file":
                if element is not None and self.resume_path and re.search(r"\b(resume|cv|curriculum vitae)\b", _norm(label)):
                    try:
                        element.send_keys(str(self.resume_path))
                        self.filled.append("Résumé file")
                    except Exception:
                        pass
                continue
            value = _value_for(label, kind, self.profile)
            if value is None or str(info.get("value", "")).strip():
                continue
            if element is None:
                continue
            try:
                if info.get("tag") == "select":
                    select = Select(element)
                    wanted = _norm(str(value))
                    matches = [option.text.strip() for option in select.options if wanted and (wanted == _norm(option.text) or wanted in _norm(option.text))]
                    if len(matches) == 1:
                        select.select_by_visible_text(matches[0])
                        self.filled.append(label.strip()[:80] or "Profile field")
                else:
                    element.clear()
                    element.send_keys(str(value))
                    self.filled.append(label.strip()[:80] or "Profile field")
            except Exception:
                continue

    def _required_fields_left(self):
        return self.driver.execute_script(r"""
        return Array.from(document.querySelectorAll('input[required], textarea[required], select[required], [aria-required="true"]')).filter(el => {
          const r=el.getBoundingClientRect(); return r.width>0 && r.height>0 && !el.disabled && !el.value;
        }).map(el => (Array.from(el.labels||[]).map(x=>x.innerText).join(' ') || el.getAttribute('aria-label') || el.placeholder || el.name || el.id || 'Required field').trim()).slice(0,12);
        """)

    def _visible_action_texts(self):
        return self.driver.execute_script(r"""
        return Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], a')).filter(el => {
          const r=el.getBoundingClientRect(); const s=getComputedStyle(el); return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none' && !el.disabled;
        }).map(el => ({text:(el.innerText || el.value || el.getAttribute('aria-label') || '').trim(), tag:el.tagName.toLowerCase()})).filter(x=>x.text);
        """)

    def _has_final_submit(self):
        for action in self._visible_action_texts():
            text = _norm(action["text"])
            if re.search(r"\b(submit|send application|finish application|complete application)\b", text):
                return True
        return False

    def _click_apply_entry(self) -> bool:
        # Click only a clear application-entry action; never click a submit action.
        candidates = self.driver.find_elements(By.CSS_SELECTOR, "button, [role='button'], a")
        for element in candidates:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                if element.tag_name.casefold() == "button" and (element.get_attribute("type") or "").casefold() == "submit":
                    continue
                text = _norm(element.text or element.get_attribute("aria-label") or "")
                if text in {"easy apply", "apply now", "apply for this job", "apply"}:
                    if "submit" in text or "send application" in text:
                        continue
                    before = set(self.driver.window_handles)
                    element.click()
                    time.sleep(1.5)
                    opened = set(self.driver.window_handles) - before
                    if opened:
                        self.driver.switch_to.window(opened.pop())
                        self._job_window_handle = self.driver.current_window_handle
                    return True
            except Exception:
                continue
        return False

    def _click_safe_next(self) -> bool:
        candidates = self.driver.find_elements(By.CSS_SELECTOR, "button, [role='button']")
        for element in candidates:
            try:
                if not element.is_displayed() or not element.is_enabled():
                    continue
                text = _norm(element.text or element.get_attribute("aria-label") or "")
                if text in {"next", "continue", "review", "next step", "continue to review"}:
                    element.click()
                    return True
            except Exception:
                continue
        return False

    def _write_outcome(self, job: dict, status: str, confirmation: str):
        import json
        from datetime import datetime, timezone
        out = ROOT / "data_folder" / "output"
        out.mkdir(parents=True, exist_ok=True)
        paths = {"Applied": out / "success.json", "Ready for review": out / "review.json", "Skipped": out / "skipped.json"}
        managed_paths = [*paths.values(), out / "failed.json"]
        record = {"link": job["link"], "title": job["title"], "company": job["company"], "timestamp": datetime.now(timezone.utc).isoformat(), "status": status, "confirmation": confirmation}
        for path in managed_paths:
            prior = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
            prior = [item for item in prior if item.get("link") != job["link"]]
            path.write_text(json.dumps(prior, indent=2), encoding="utf-8")
        target = paths[status]
        prior = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else []
        prior.append(record)
        target.write_text(json.dumps(prior, indent=2), encoding="utf-8")


SESSION = ManualApplySession()
