from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os
import re

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

service = Service(log_output=os.devnull)
driver = webdriver.Chrome(options=options, service=service)

try:
    driver.get("https://www.naukrigulf.com/business-analyst-jobs-in-dubai")
    import time
    time.sleep(5)
    html = driver.page_source
    print("Page length:", len(html))
    
    # Let's search for some patterns in HTML:
    # Look for class names
    classes = re.findall(r'class="([^"]+)"', html)
    unique_classes = set()
    for c in classes:
        for val in c.split():
            unique_classes.add(val)
    print("Matching job-related classes:")
    for uc in sorted(unique_classes):
        if "job" in uc or "tuple" in uc or "card" in uc or "srp" in uc:
            print("-", uc)
            
    # Also find all <a> tags with job in href or title
    links = driver.find_elements(By.TAG_NAME, "a")
    job_links = []
    for l in links:
        href = l.get_attribute("href") or ""
        text = l.text or ""
        if "/job-listings-" in href or "-jobs" in href:
            job_links.append((text, href))
    print(f"\nFound {len(job_links)} job links:")
    for text, href in job_links[:10]:
        print(f"Text: '{text}' -> Href: '{href}'")
        
except Exception as e:
    print("Error:", e)
finally:
    driver.quit()
