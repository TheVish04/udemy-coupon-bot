import os
import sys
import csv
import time
import random
from urllib.parse import urlparse, parse_qs

# 1) Suppress TensorFlow-Lite delegate messages (if any)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"  # only errors

# 2) Gather user input up front
pages_input = input("Enter number of pages to scrape (default 5): ").strip()
try:
    MAX_PAGES = int(pages_input) if pages_input else 10
except ValueError:
    print(f"Invalid number '{pages_input}', defaulting to 5 pages.")
    MAX_PAGES = 5

# 3) Now import everything else and start Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

class DiscUdemyScraper:
    BASE = "https://www.discudemy.com"
    LISTING = "/all/{}"

    def __init__(self, headless=True, timeout=15):
        # Suppress ChromeDriver logging by sending it to null
        service = Service(ChromeDriverManager().install())
        service.log_path = os.devnull

        opts = Options()
        if headless:
            opts.add_argument("--headless")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )

        self.driver = webdriver.Chrome(service=service, options=opts)
        self.wait   = WebDriverWait(self.driver, timeout)

    def close(self):
        if self.driver:
            self.driver.quit()

    def get_detail_urls(self, page_num: int):
        url = f"{self.BASE}{self.LISTING.format(page_num)}"
        try:
            self.driver.get(url)
        except WebDriverException as e:
            print(f"[!] Connection error loading listing page {page_num}: {e}")
            return []

        try:
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.card-header")))
        except TimeoutException:
            print(f"[!] Timeout loading listing page {page_num}")
            return []

        anchors = self.driver.find_elements(By.CSS_SELECTOR, "a.card-header")
        urls = []
        for a in anchors:
            href = a.get_attribute("href")
            if href and href.startswith(self.BASE) and "/go/" not in href:
                urls.append(href)
        print(f"[+] Page {page_num}: {len(urls)} detail URLs")
        return list(set(urls))

    def extract_coupon(self, detail_url: str):
        print(f"[→] {detail_url}")
        try:
            self.driver.get(detail_url)
        except WebDriverException as e:
            print(f"[!] Connection reset on detail page {detail_url}: {e}")
            return None

        try:
            take = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.discBtn")))
        except TimeoutException:
            print(f"[!] No Take Course button at {detail_url}")
            return None

        go_link = take.get_attribute("href") or ""
        if not go_link:
            try:
                take.click()
                time.sleep(2)
                go_link = self.driver.current_url
            except WebDriverException as e:
                print(f"[!] Error clicking Take Course at {detail_url}: {e}")
                return None
        else:
            try:
                self.driver.get(go_link)
            except WebDriverException as e:
                print(f"[!] Connection reset when navigating to coupon at {detail_url}: {e}")
                return None

        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.ui.segment a[href*='udemy.com/course']")
            ))
        except TimeoutException:
            print(f"[!] Timeout on go-page for {detail_url}")
            return None

        try:
            udemy_anchor = self.driver.find_element(
                By.CSS_SELECTOR, "div.ui.segment a[href*='udemy.com/course']"
            )
            udemy_url = udemy_anchor.get_attribute("href")
        except NoSuchElementException:
            print(f"[!] No Udemy link at go-page for {detail_url}")
            return None

        parsed = urlparse(udemy_url)
        parts  = parsed.path.strip("/").split("/")
        slug   = parts[parts.index("course")+1] if "course" in parts else parts[-1]
        code   = parse_qs(parsed.query).get("couponCode", [""])[0]

        return {
            "detail_url":  detail_url,
            "go_link":     go_link,
            "udemy_url":   udemy_url,
            "slug":        slug,
            "coupon_code": code
        }

    def scrape(self, max_pages, delay_range=(1,3)):
        results = []
        for p in range(1, max_pages+1):
            details = self.get_detail_urls(p)
            for d in details:
                time.sleep(random.uniform(*delay_range))
                try:
                    info = self.extract_coupon(d)
                except Exception as e:
                    print(f"[!] Unexpected error on {d}: {e}")
                    continue
                if info:
                    results.append(info)
            time.sleep(random.uniform(2,5))
        return results

    def save_csv(self, data, fname="discudemy_coupons.csv"):
        if not data:
            print("[!] No data to save.")
            return
        keys = ["detail_url","go_link","udemy_url","slug","coupon_code"]
        with open(fname, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        print(f"[✓] Saved {len(data)} entries to {os.path.abspath(fname)}")


if __name__ == "__main__":
    scraper = DiscUdemyScraper(headless=True)
    try:
        print(f"→ Scraping {MAX_PAGES} pages…")
        out = scraper.scrape(max_pages=MAX_PAGES)
        scraper.save_csv(out)
        print("→ Done.")
    finally:
        scraper.close()
