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
    print("Navigating to Wellfound...")
    url = "https://wellfound.com/role/l/software-engineer/remote"
    driver.get(url)
    time.sleep(5)
    print("Page Title:", driver.title)
    print("Page Source length:", len(driver.page_source))
    # Let's search for tags or classes in page source
    html = driver.page_source.lower()
    for word in ["job", "role", "salary", "apply"]:
        print(f"Occurrences of '{word}':", html.count(word))
except Exception as e:
    print("Error:", e)
finally:
    driver.quit()
