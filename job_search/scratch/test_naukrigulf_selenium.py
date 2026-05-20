from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--window-size=1920,1080")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

service = Service(log_output=os.devnull)
driver = webdriver.Chrome(options=options, service=service)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

try:
    print("Navigating to Naukrigulf...")
    driver.get("https://www.naukrigulf.com/business-analyst-jobs-in-dubai")
    time.sleep(5)
    print("Page Title:", driver.title)
    print("Page Source length:", len(driver.page_source))
    # Look for job card element
    for selector in ["div.job-tuple", "article", ".job-info", "a.job-title"]:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements:
            print(f"Found {len(elements)} elements with selector '{selector}'")
            print("First item text:", elements[0].text[:200])
except Exception as e:
    print("Error:", e)
finally:
    driver.quit()
