import os
import csv
import time
import random
import re
import json
import urllib.parse
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm  # Progress bar


class CouponScorpionScraper:
    BASE_URL = "https://couponscorpion.com"
    LISTING_URL = BASE_URL + "/page/{}/"

    def __init__(self, headless=True, timeout=15):
        service = Service(ChromeDriverManager().install())
        service.log_path = os.devnull

        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        
        # Browser configuration for better anti-bot protection bypass
        opts.add_argument("--disable-blink-features=AutomationControlled")  # Hide automation
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--allow-running-insecure-content")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-dev-shm-usage")
        
        # More human-like user agent
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
        
        # Add custom preferences to appear more human-like
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "webrtc.ip_handling_policy": "disable_non_proxied_udp",
            "plugins.always_open_pdf_externally": True
        }
        opts.add_experimental_option("prefs", prefs)
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        
        self.driver = webdriver.Chrome(service=service, options=opts)
        
        # Execute CDP commands to hide automation
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                window.chrome = {
                    runtime: {}
                };
            """
        })
        
        self.wait = WebDriverWait(self.driver, timeout)
        self.short_wait = WebDriverWait(self.driver, 5)

    def close(self):
        if self.driver:
            self.driver.quit()

    def get_detail_links(self, page_num: int) -> list[str]:
        url = self.LISTING_URL.format(page_num)
        self.driver.get(url)

        try:
            # Wait for course items to load
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.info_in_dealgrid figure.mb15 a")
            ))
        except TimeoutException:
            print(f"[!] Timeout loading listing page {page_num}")
            return []

        anchors = self.driver.find_elements(By.CSS_SELECTOR, "div.info_in_dealgrid figure.mb15 a")
        links = []
        for a in anchors:
            href = a.get_attribute("href")
            if href and href.startswith(self.BASE_URL):
                links.append(href)
        return list(set(links))

    def wait_for_cloudflare(self, timeout=30):
        """Wait for Cloudflare protection to complete"""
        try:
            start = time.time()
            while time.time() - start < timeout:
                if "Verifying you are human" in self.driver.page_source or "cloudflare" in self.driver.page_source.lower():
                    print("[*] Detected Cloudflare challenge, waiting...")
                    time.sleep(2)
                else:
                    # Check if we're on a recognizable page
                    if "udemy.com" in self.driver.current_url:
                        print("[+] Successfully passed Cloudflare challenge!")
                        return True
                    elif self.driver.current_url != "about:blank":
                        print("[*] Cloudflare check complete, continuing...")
                        return True
            
            print("[!] Cloudflare challenge timeout")
            return False
        except Exception as e:
            print(f"[!] Error while waiting for Cloudflare: {str(e)}")
            return False
            
    def human_like_delays(self):
        """Add random human-like delays and movements"""
        # Random move of mouse to simulate human behavior
        try:
            if random.random() < 0.5:  # 50% chance to move mouse
                action = ActionChains(self.driver)
                x, y = random.randint(100, 700), random.randint(100, 500)
                action.move_by_offset(x, y).perform()
                
            # Add some realistic pauses
            time.sleep(random.uniform(0.5, 2))
        except:
            pass  # Ignore if it fails, not critical
    
    def directly_extract_redirect_url(self, href_url):
        """Try to extract the Udemy URL directly from the redirect URL"""
        try:
            # Parse the redirect URL to get the 'go' parameter
            parsed = urlparse(href_url)
            params = parse_qs(parsed.query)
            
            if 'go' in params:
                # Try to decode it (it's likely base64 encoded)
                import base64
                encoded_url = params['go'][0]
                # Sometimes it's double-encoded or has other formats
                try:
                    decoded_url = base64.b64decode(encoded_url).decode('utf-8')
                    if "udemy.com" in decoded_url:
                        # Extract the coupon code from this URL
                        coupon_match = re.search(r'couponCode=([^&]+)', decoded_url)
                        if coupon_match:
                            coupon_code = coupon_match.group(1)
                            return {"url": decoded_url, "coupon_code": coupon_code}
                except:
                    pass
            
            return None
        except Exception as e:
            print(f"[!] Error parsing redirect URL: {str(e)}")
            return None
            
    def extract_coupon_from_page_source(self):
        """Extract coupon information from page source if available"""
        try:
            page_source = self.driver.page_source
            
            # Look for Udemy URLs in the page source
            udemy_url_match = re.search(r'https?://www\.udemy\.com/course/[^/"\']+', page_source)
            if udemy_url_match:
                udemy_url = udemy_url_match.group(0)
                
                # Try to find coupon code
                coupon_match = re.search(r'couponCode=([^&"\'\s]+)', page_source)
                coupon_code = coupon_match.group(1) if coupon_match else ""
                
                return {"url": udemy_url, "coupon_code": coupon_code}
        except Exception as e:
            print(f"[!] Error extracting from page source: {str(e)}")
        
        return None
    
    def extract_coupon(self, detail_url: str) -> dict | None:
        """Get the course details and coupon information by visiting the detail page and following redirects."""
        try:
            # Open course detail page
            self.driver.get(detail_url)
            self.human_like_delays()
            
            # Extract course title
            try:
                title_elem = self.wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "h1.rehub_main_font")
                ))
                title = title_elem.text.strip()
            except (TimeoutException, NoSuchElementException):
                try:
                    title_elem = self.driver.find_element(By.TAG_NAME, "h1")
                    title = title_elem.text.strip()
                except:
                    title = "Unknown Title"
            
            print(f"[*] Processing: {title}")
            
            # Try to find the GET COUPON CODE button
            try:
                coupon_btn = self.wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "a.btn_offer_block.re_track_btn")
                ))
                
                # Get the button's href before clicking
                intermediate_url = coupon_btn.get_attribute("href")
                
                # APPROACH 1: Try to extract the final Udemy URL directly from the redirect URL
                direct_extract = self.directly_extract_redirect_url(intermediate_url)
                if direct_extract:
                    udemy_url = direct_extract["url"]
                    coupon_code = direct_extract["coupon_code"]
                    print(f"[+] Extracted directly: {udemy_url} with coupon: {coupon_code}")
                    
                    # Extract slug from the URL
                    parsed = urlparse(udemy_url)
                    path_parts = parsed.path.strip("/").split("/")
                    if "course" in path_parts and len(path_parts) > path_parts.index("course") + 1:
                        slug = path_parts[path_parts.index("course") + 1]
                    else:
                        slug = path_parts[-1] if path_parts else ""
                    
                    return {
                        "title": title,
                        "detail_url": detail_url,
                        "intermediate_url": intermediate_url,
                        "udemy_url": udemy_url,
                        "slug": slug,
                        "coupon_code": coupon_code
                    }
                
                # APPROACH 2: Try clicking the button and follow redirects
                print("[*] Clicking the coupon button...")
                
                # Open in a new tab (may help bypass some protection)
                current_window = self.driver.current_window_handle
                self.driver.execute_script(f"window.open('{intermediate_url}', '_blank');")
                time.sleep(1)
                
                # Switch to the new tab
                windows = self.driver.window_handles
                self.driver.switch_to.window(windows[-1])
                
                # Wait for Cloudflare if present
                cloudflare_done = self.wait_for_cloudflare(timeout=20)
                
                # Check if we're on Udemy
                final_url = self.driver.current_url
                
                # If we ended up on Udemy
                if "udemy.com" in final_url:
                    print(f"[+] Successfully reached Udemy: {final_url}")
                    
                    # Parse Udemy URL to extract slug and coupon
                    parsed = urlparse(final_url)
                    
                    # Extract slug from path
                    path_parts = parsed.path.strip("/").split("/")
                    if "course" in path_parts and len(path_parts) > path_parts.index("course") + 1:
                        slug = path_parts[path_parts.index("course") + 1]
                    else:
                        slug = path_parts[-1] if path_parts else ""
                    
                    # Extract coupon code from query parameters
                    query_params = parse_qs(parsed.query)
                    coupon_code = query_params.get("couponCode", [""])[0]
                    
                    # If no coupon code in query params, try looking for it in the URL
                    if not coupon_code:
                        coupon_match = re.search(r'couponCode=([^&]+)', final_url)
                        if coupon_match:
                            coupon_code = coupon_match.group(1)
                    
                    # Close this tab and switch back
                    self.driver.close()
                    self.driver.switch_to.window(current_window)
                    
                    return {
                        "title": title,
                        "detail_url": detail_url,
                        "intermediate_url": intermediate_url,
                        "udemy_url": final_url,
                        "slug": slug,
                        "coupon_code": coupon_code
                    }
                else:
                    # Try extracting from page source
                    source_extract = self.extract_coupon_from_page_source()
                    if source_extract:
                        udemy_url = source_extract["url"]
                        coupon_code = source_extract["coupon_code"]
                        
                        # Extract slug from the URL
                        parsed = urlparse(udemy_url)
                        path_parts = parsed.path.strip("/").split("/")
                        if "course" in path_parts and len(path_parts) > path_parts.index("course") + 1:
                            slug = path_parts[path_parts.index("course") + 1]
                        else:
                            slug = path_parts[-1] if path_parts else ""
                        
                        # Close this tab and switch back
                        self.driver.close()
                        self.driver.switch_to.window(current_window)
                        
                        return {
                            "title": title,
                            "detail_url": detail_url,
                            "intermediate_url": intermediate_url,
                            "udemy_url": udemy_url,
                            "slug": slug,
                            "coupon_code": coupon_code
                        }
                    
                    # We didn't end up on a Udemy page
                    print(f"[!] Redirect didn't reach Udemy: {final_url}")
                    
                    # Close this tab and switch back
                    self.driver.close()
                    self.driver.switch_to.window(current_window)
                    return None
                
            except TimeoutException:
                print(f"[!] Couldn't find coupon button on {detail_url}")
                return None
            
        except Exception as e:
            print(f"[!] Error processing {detail_url}: {str(e)}")
            return None

    def scrape(self, max_pages=5, delay=(2, 5)) -> list[dict]:
        data = []
        print(f"→ Scraping {max_pages} pages from CouponScorpion.com...\n")
        
        total_links = []
        # First, collect all the links from the listing pages
        for p in tqdm(range(1, max_pages + 1), desc="Collecting links"):
            links = self.get_detail_links(p)
            if not links:
                print(f"[!] No links found on page {p}, skipping")
                continue
                
            print(f"[+] Found {len(links)} courses on page {p}")
            total_links.extend(links)
            
            # Longer delay between pages to appear more human-like
            time.sleep(random.uniform(3, 7))
        
        # Remove duplicates and randomize order
        total_links = list(set(total_links))
        random.shuffle(total_links)
        
        print(f"\n[*] Processing {len(total_links)} unique course links...")
        
        # Process the collected links
        for i, link in enumerate(total_links):
            # More human-like random delay between requests
            delay_time = random.uniform(*delay)
            print(f"[*] Waiting {delay_time:.1f}s before next request ({i+1}/{len(total_links)})")
            time.sleep(delay_time)
            
            info = self.extract_coupon(link)
            if info:
                data.append(info)
                print(f"[+] Found coupon: {info.get('title', 'Unknown')} - {info.get('coupon_code', 'No code')}")
                
                # Save progressively in case the script is interrupted
                if len(data) % 5 == 0:
                    temp_filename = f"couponscorpion_progress_{len(data)}.csv"
                    self.save_csv(data, temp_filename)
                    print(f"[*] Saved progress ({len(data)} coupons) to {temp_filename}")
            
        return data

    def save_csv(self, records: list[dict], filename="couponscorpion_coupons.csv"):
        if not records:
            print("[!] No records to save.")
            return
            
        fields = ["title", "detail_url", "intermediate_url", "udemy_url", "slug", "coupon_code"]
        
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
            
        print(f"[✓] Saved {len(records)} records to {os.path.abspath(filename)}")


if __name__ == "__main__":
    pages = input("Enter number of pages to scrape (default 5): ").strip()
    try:
        max_p = int(pages) if pages else 5
    except ValueError:
        print(f"Invalid input '{pages}', defaulting to 5 pages.")
        max_p = 5

    scraper = CouponScorpionScraper(headless=False)  # Set to False to see the browser in action
    try:
        results = scraper.scrape(max_pages=max_p)
        scraper.save_csv(results)
        print(f"\n→ Done. Extracted {len(results)} coupons.")
    finally:
        scraper.close()