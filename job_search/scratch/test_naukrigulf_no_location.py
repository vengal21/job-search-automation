from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os
import time

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

service = Service(log_output=os.devnull)
driver = webdriver.Chrome(options=options, service=service)

try:
    url = "https://www.naukrigulf.com/jobs?searchText=business+analyst"
    print("Navigating to:", url)
    driver.get(url)
    time.sleep(5)
    print("Title:", driver.title)
    cards = driver.find_elements(By.CSS_SELECTOR, "div.srp-tuple")
    print(f"Found {len(cards)} cards on page.")
except Exception as e:
    print("Error:", e)
finally:
    driver.quit()
