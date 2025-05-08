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
            
            # First check if pagination exists
            pagination_nav = self.driver.find_elements(By.CSS_SELECTOR, 'nav[aria-label="pagination navigation"]')
            if not pagination_nav:
                print("No pagination found, assuming 1 page")
                return 1
                
            # Try to find pagination buttons with aria-label containing "Go to page"
            pagination_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button.MuiPaginationItem-root')
            
            # Extract page numbers from the aria-labels
            page_numbers = []
            for button in pagination_buttons:
                try:
                    aria_label = button.get_attribute('aria-label')
                    if aria_label and 'Go to page' in aria_label:
                        # Extract the number from "Go to page X"
                        page_num = aria_label.split('Go to page')[-1].strip()
                        if page_num.isdigit():
                            page_numbers.append(int(page_num))
                except Exception:
                    continue
            
            # If we still don't have page numbers, try getting text from buttons
            if not page_numbers:
                for button in pagination_buttons:
                    try:
                        text = button.text.strip()
                        if text.isdigit():
                            page_numbers.append(int(text))
                    except Exception:
                        continue
            
            # If we found valid page numbers, return the maximum
            if page_numbers:
                max_page = max(page_numbers)
                print(f"Detected {max_page} pages from pagination")
                return max_page
            else:
                print("Could not extract page numbers, assuming at least 10 pages")
                return 10  # Assume at least 10 pages if we can't determine exactly
            
        except Exception as e:
            print(f"Error getting total pages: {str(e)}")
            # If we can't determine pages, assume at least 10
            print("Assuming 10 pages due to error")
            return 10
    
    def navigate_to_page(self, page_num):
        """Navigate to a specific page of courses using pagination buttons"""
        if page_num == 1:
            # Just load the base URL for page 1
            self.driver.get(self.courses_url)
            return True
            
        # For pages > 1, try to use pagination
        try:
            # First check if we're already on the courses page
            current_url = self.driver.current_url
            if not current_url.startswith(self.courses_url):
                self.driver.get(self.courses_url)
                
            # Wait for pagination to load
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'nav[aria-label="pagination navigation"]')))
            time.sleep(2)  # Wait for JS to fully render
            
            # Try to find the button for the specific page
            page_button = self.driver.find_element(By.XPATH, f'//button[@aria-label="Go to page {page_num}"]')
            page_button.click()
            
            # Wait for page to reload
            time.sleep(3)
            return True
        except Exception as e:
            print(f"Error navigating to page {page_num}: {str(e)}")
            
            # Fallback: Try using URL parameter
            try:
                url = f"{self.courses_url}?page={page_num}"
                self.driver.get(url)
                time.sleep(3)
                return True
            except:
                print(f"Failed to navigate to page {page_num}")
                return False
    
    def get_course_links(self, page_num):
        """Get all course links from a specific page"""
        print(f"Fetching courses from page {page_num}...")
        
        # Navigate to the specified page
        if not self.navigate_to_page(page_num):
            return []
        
        try:
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
            
            # Wait for the page to load
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.MuiButton-root')))
            time.sleep(2)  # Additional wait for JS rendering
            
            # Extract course title
            try:
                title_element = self.driver.find_element(By.CSS_SELECTOR, 'h1.MuiTypography-root')
                title = title_element.text.strip()
            except NoSuchElementException:
                title = "Unknown Title"
            
            # Multiple methods to find the "Get Course" button
            udemy_link = None
            
            # Method 1: Direct "Get Course" text approach
            try:
                get_course_elements = self.driver.find_elements(By.XPATH, '//*[text()="Get Course"]')
                for element in get_course_elements:
                    # Try to find parent or ancestor that is an <a> tag
                    current = element
                    for _ in range(4):  # Check up to 4 levels up
                        try:
                            # Try parent
                            current = current.find_element(By.XPATH, '..')
                            # Check if it's an anchor
                            if current.tag_name == 'a':
                                link = current.get_attribute('href')
                                if link and "udemy.com" in link:
                                    udemy_link = link
                                    break
                        except:
                            break
                    if udemy_link:
                        break
            except Exception as e:
                print(f"Method 1 failed: {str(e)}")
            
            # Method 2: Look for any Udemy links in buttons
            if not udemy_link:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, '.MuiButtonBase-root')
                    for button in buttons:
                        # If the button itself is a link
                        if button.tag_name == 'a':
                            link = button.get_attribute('href')
                            if link and "udemy.com" in link:
                                udemy_link = link
                                break
                        
                        # Or if the button contains a link
                        try:
                            link_element = button.find_element(By.TAG_NAME, 'a')
                            link = link_element.get_attribute('href')
                            if link and "udemy.com" in link:
                                udemy_link = link
                                break
                        except:
                            pass
                except Exception as e:
                    print(f"Method 2 failed: {str(e)}")
            
            # Method 3: Just look for any element with a Udemy link
            if not udemy_link:
                try:
                    links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="udemy.com"]')
                    for link_element in links:
                        link = link_element.get_attribute('href')
                        if link:
                            udemy_link = link
                            break
                except Exception as e:
                    print(f"Method 3 failed: {str(e)}")
            
            if not udemy_link:
                print(f"No Udemy link found for: {course_url}")
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
    
    # Get user input for how many pages to scrape
    try:
        max_pages_input = input("Enter number of pages to scrape (or press Enter for all pages): ")
        max_pages = int(max_pages_input) if max_pages_input.strip() else None
    except ValueError:
        print(f"Invalid input '{max_pages_input}'. Using default.")
        max_pages = None
        
    # Force a minimum of 10 pages if a specific number was requested
    if max_pages is not None and max_pages < 10:
        print(f"Setting minimum of 10 pages to scrape")
        max_pages = 10
    
    # Get user input for output filename
    filename = input("Enter output CSV filename (default: udemy_coupons.csv): ")
    if not filename.strip():
        filename = "udemy_coupons.csv"
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    # Initialize scraper
    scraper = RealDiscountScraper()
    
    # Start scraping
    courses = scraper.scrape_courses(max_pages=max_pages)
    scraper.save_to_csv(courses, filename)
    
    print(f"\nScraper completed. Found {len(courses)} courses.")


if __name__ == "__main__":
    main()