import sys
sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os
import json

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

service = Service(log_output=os.devnull)
driver = webdriver.Chrome(options=options, service=service)

try:
    print("Loading page...")
    driver.get("https://www.naukrigulf.com/business-analyst-jobs-in-dubai")
    import time
    time.sleep(5)
    
    # Try finding job cards using "srp-tuple" or "tuple-wrap" or similar
    cards = driver.find_elements(By.CSS_SELECTOR, "div.srp-tuple")
    if not cards:
        cards = driver.find_elements(By.CSS_SELECTOR, "[class*='srp-tuple']")
    
    print(f"Found {len(cards)} job cards.")
    
    jobs = []
    for card in cards[:10]:
        try:
            # Let's extract: Title, Company, Link, Location, Exp, Salary, Posted Date
            title_el = card.find_element(By.CSS_SELECTOR, "a.job-title")
            title = title_el.text.strip()
            url = title_el.get_attribute("href")
            
            # Company
            try:
                org_el = card.find_element(By.CSS_SELECTOR, "p.org-name")
                company = org_el.text.strip()
            except:
                try:
                    org_el = card.find_element(By.CSS_SELECTOR, "[class*='org-name']")
                    company = org_el.text.strip()
                except:
                    company = ""
            
            # Location
            try:
                loc_el = card.find_element(By.CSS_SELECTOR, "p.exp-loc")
                loc = loc_el.text.strip()
            except:
                loc = ""
                
            # Date
            try:
                date_el = card.find_element(By.CSS_SELECTOR, "p.job-post-date")
                date_str = date_el.text.strip()
            except:
                date_str = ""
                
            jobs.append({
                "title": title,
                "url": url,
                "company": company,
                "location": loc,
                "date": date_str
            })
        except Exception as card_err:
            print("Card error:", card_err)
            
    print(json.dumps(jobs, indent=2))
        
except Exception as e:
    print("Error:", e)
finally:
    driver.quit()
