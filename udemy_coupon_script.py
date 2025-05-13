import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import argparse
import sys

def scrape_hacksnation(url):
    """
    Scrape Udemy course links from HacksNation website
    """
    print(f"Downloading from {url}...")
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error downloading page: {e}")
        return []

    # Parse the HTML and locate all enroll links
    soup = BeautifulSoup(resp.text, "html.parser")
    # the links are plain <a> tags whose text is "Enroll for Free"
    enroll_links = [
        a["href"] for a in soup.find_all("a", string="Enroll for Free")
    ]

    # Extract slug and couponCode from each Udemy URL
    results = []
    for href in enroll_links:
        # ensure it's a Udemy course URL
        parsed = urlparse(href)
        if parsed.netloc.endswith("udemy.com") and parsed.path.startswith("/course/"):
            # slug is the segment after /course/
            slug = parsed.path.split("/")[2]
            # couponCode is in the query string
            coupon = parse_qs(parsed.query).get("couponCode", [""])[0]
            results.append({"slug": slug, "couponCode": coupon})

    print(f"Found {len(results)} course links")
    return results

def process_text_data(text_data):
    """
    Process multiline string of slug and couponCode pairs
    """
    rows = []
    for line in text_data.strip().split('\n'):
        if 'slug:' in line and 'couponCode:' in line:
            parts = line.split('couponCode:')
            slug_part = parts[0].replace('slug:', '').strip()
            code_part = parts[1].strip()
            rows.append({'slug': slug_part, 'couponCode': code_part})
    
    return rows

def main():
    parser = argparse.ArgumentParser(description='Udemy Coupon Scraper and Processor')
    parser.add_argument('--url', type=str, help='URL to scrape (e.g., https://hacksnation.com/d/37375-udemy-free-courses-for-08-may-2025)')
    parser.add_argument('--file', type=str, help='File containing slug and couponCode pairs')
    parser.add_argument('--output', type=str, default='udemy_coupons.csv', help='Output CSV filename')
    parser.add_argument('--paste', action='store_true', help='Process multiline string from paste.txt file')
    
    args = parser.parse_args()
    
    # Check if at least one input source is specified
    if not (args.url or args.file or args.paste):
        parser.print_help()
        print("\nError: Please specify at least one input source (--url, --file, or --paste)")
        sys.exit(1)
    
    all_courses = []
    
    # Process URL if provided
    if args.url:
        scraped_courses = scrape_hacksnation(args.url)
        all_courses.extend(scraped_courses)
        print(f"Scraped {len(scraped_courses)} courses from the URL")
    
    # Process file if provided
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text_data = f.read()
                file_courses = process_text_data(text_data)
                all_courses.extend(file_courses)
                print(f"Processed {len(file_courses)} courses from the file")
        except Exception as e:
            print(f"Error reading file: {e}")
    
    # Process paste.txt if specified
    if args.paste:
        try:
            with open('paste.txt', 'r', encoding='utf-8') as f:
                text_data = f.read()
                paste_courses = process_text_data(text_data)
                all_courses.extend(paste_courses)
                print(f"Processed {len(paste_courses)} courses from paste.txt")
        except Exception as e:
            print(f"Error reading paste.txt: {e}")
    
    # Create DataFrame from the collected data
    if all_courses:
        df = pd.DataFrame(all_courses)
        
        # Remove duplicates based on slug
        df = df.drop_duplicates(subset=['slug'])
        
        # Save to CSV
        df.to_csv(args.output, index=False)
        print(f"Saved {len(df)} unique courses to {args.output}")
        
        # Print sample of the data
        print("\nSample data:")
        print(df.head().to_string())
    else:
        print("No courses found.")

if __name__ == "__main__":
    main()

# python udemy_coupon_script.py --url "https://hacksnation.com/d/37592-udemy-free-courses-for-13-may-2025" --paste --output special_courses.csv