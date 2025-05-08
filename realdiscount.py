from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import csv
import time
import random
from urllib.parse import urlparse, parse_qs
import os

class RealDiscountScraper:
    def __init__(self):
        self.base_url = "https://www.real.discount"
        self.courses_url = f"{self.base_url}/courses"
        
        # Setup Selenium
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Initialize the WebDriver
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        self.wait = WebDriverWait(self.driver, 15)  # 15 second timeout
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
    
    def get_total_pages(self):
        """Get the total number of pages of courses"""
        try:
            self.driver.get(self.courses_url)
            # Wait for page to load (main container)
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".MuiGrid-container")))
            time.sleep(3)  # Additional wait for JS to render fully
            
            # Find pagination elements
            pagination_elements = self.driver.find_elements(By.CSS_SELECTOR, '.MuiPagination-ul li')
            if not pagination_elements:
                return 1
            
            # Extract page numbers
            page_numbers = []
            for page in pagination_elements:
                try:
                    text = page.text.strip()
                    if text.isdigit():
                        page_numbers.append(int(text))
                except ValueError:
                    continue
            
            return max(page_numbers) if page_numbers else 1
            
        except Exception as e:
            print(f"Error getting total pages: {str(e)}")
            # If we can't determine pages, assume at least 1
            return 1
    
    def get_course_links(self, page_num):
        """Get all course links from a specific page"""
        url = f"{self.courses_url}?page={page_num}"
        print(f"Fetching courses from page {page_num}...")
        
        try:
            self.driver.get(url)
            # Wait for courses to load (MuiLink elements)
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".MuiLink-root")))
            time.sleep(3)  # Additional wait for JS to render fully
            
            # Find all course cards with links
            course_links = []
            link_elements = self.driver.find_elements(By.CSS_SELECTOR, '.MuiLink-root[href^="/offer/"]')
            
            for link in link_elements:
                try:
                    href = link.get_attribute('href')
                    if href and '/offer/' in href:
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            href = f"{self.base_url}{href}"
                        course_links.append(href)
                except Exception:
                    continue
            
            return course_links
            
        except TimeoutException:
            print(f"Timeout waiting for courses on page {page_num}")
            return []
        except Exception as e:
            print(f"Error fetching courses from page {page_num}: {str(e)}")
            return []
    
    def extract_coupon_details(self, course_url):
        """Extract the Udemy course slug and coupon code from a course page"""
        try:
            print(f"Processing: {course_url}")
            self.driver.get(course_url)
            
            # Wait for the page to load (specifically the Get Course button)
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.MuiButton-root')))
            time.sleep(2)  # Additional wait for JS rendering
            
            # Extract course title
            try:
                title_element = self.driver.find_element(By.CSS_SELECTOR, 'h1.MuiTypography-root')
                title = title_element.text.strip()
            except NoSuchElementException:
                title = "Unknown Title"
            
            # Extract the Get Course button link
            try:
                # First try with the "Get Course" text, which is more specific
                get_course_btns = self.driver.find_elements(By.XPATH, '//a[contains(text(), "Get Course")]')
                
                # If not found, try all buttons that might link to Udemy
                if not get_course_btns:
                    get_course_btns = self.driver.find_elements(By.CSS_SELECTOR, 'a.MuiButton-root[href*="udemy.com"]')
                
                if not get_course_btns:
                    # Try any link to Udemy as a last resort
                    get_course_btns = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="udemy.com"]')
                
                if not get_course_btns:
                    print(f"No link to Udemy found for: {course_url}")
                    return None
                
                # Get the first matching button with a valid Udemy link
                udemy_link = None
                for btn in get_course_btns:
                    link = btn.get_attribute('href')
                    if link and "udemy.com" in link:
                        udemy_link = link
                        break
                
                if not udemy_link:
                    print(f"No valid link found in buttons for: {course_url}")
                    return None
                
            except NoSuchElementException:
                print(f"No Get Course button found for: {course_url}")
                return None
            
            # Parse the URL to extract slug and coupon code
            parsed_url = urlparse(udemy_link)
            path_parts = parsed_url.path.strip('/').split('/')
            
            # Get the slug (course identifier from the URL path)
            # Typically the format is /course/course-slug/
            if 'course' in path_parts:
                course_index = path_parts.index('course')
                if len(path_parts) > course_index + 1:
                    slug = path_parts[course_index + 1]
                else:
                    slug = "unknown"
            else:
                # If we can't find "course" in the path, use the last segment
                slug = path_parts[-1] if path_parts else "unknown"
            
            # Get coupon code from query parameters
            query_params = parse_qs(parsed_url.query)
            coupon_code = query_params.get('couponCode', [''])[0]
            
            return {
                'title': title,
                'url': course_url,
                'slug': slug,
                'coupon_code': coupon_code,
                'udemy_link': udemy_link
            }
        except TimeoutException:
            print(f"Timeout loading course page: {course_url}")
            return None
        except Exception as e:
            print(f"Error processing {course_url}: {str(e)}")
            return None
    
    def scrape_courses(self, max_pages=None, delay_min=1, delay_max=3):
        """Scrape courses from Real.Discount"""
        try:
            total_pages = self.get_total_pages()
            print(f"Found {total_pages} pages of courses")
            
            if max_pages and max_pages < total_pages:
                total_pages = max_pages
                print(f"Limiting to first {max_pages} pages")
            
            all_courses = []
            
            for page in range(1, total_pages + 1):
                course_links = self.get_course_links(page)
                print(f"Found {len(course_links)} courses on page {page}")
                
                for link in course_links:
                    # Add a random delay between requests to avoid rate limiting
                    time.sleep(random.uniform(delay_min, delay_max))
                    course_data = self.extract_coupon_details(link)
                    if course_data:
                        all_courses.append(course_data)
                
                print(f"Completed page {page}/{total_pages}")
                # Add a delay between pages
                if page < total_pages:
                    time.sleep(random.uniform(2, 5))
            
            return all_courses
            
        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            return []
        finally:
            self.close()
    
    def save_to_csv(self, courses, filename="udemy_coupons.csv"):
        """Save course data to a CSV file"""
        if not courses:
            print("No courses to save.")
            return
        
        fieldnames = ['title', 'slug', 'coupon_code', 'url', 'udemy_link']
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for course in courses:
                writer.writerow(course)
        
        print(f"Saved {len(courses)} courses to {filename}")
        print(f"File saved at: {os.path.abspath(filename)}")


def main():
    print("Starting Real.Discount Udemy Coupon Scraper...")
    scraper = RealDiscountScraper()
    
    # Get user input for how many pages to scrape
    try:
        max_pages = input("Enter number of pages to scrape (or press Enter for all pages): ")
        max_pages = int(max_pages) if max_pages.strip() else None
    except ValueError:
        max_pages = None
    
    # Get user input for output filename
    filename = input("Enter output CSV filename (default: udemy_coupons.csv): ")
    if not filename.strip():
        filename = "udemy_coupons.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    # Start scraping
    courses = scraper.scrape_courses(max_pages=max_pages)
    scraper.save_to_csv(courses, filename)
    
    print(f"\nScraper completed. Found {len(courses)} courses.")


if __name__ == "__main__":
    main()