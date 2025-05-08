import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# 1) Download the HacksNation page
page_url = "https://hacksnation.com/d/37317-udemy-free-courses-for-07-may-2025"
resp = requests.get(page_url, timeout=10)
resp.raise_for_status()

# 2) Parse the HTML and locate all enroll links
soup = BeautifulSoup(resp.text, "html.parser")
# the links are plain <a> tags whose text is "Enroll for Free"
enroll_links = [
    a["href"] for a in soup.find_all("a", string="Enroll for Free")
]

# 3) Extract slug and couponCode from each Udemy URL
results = []
for href in enroll_links:
    # ensure it's a Udemy course URL
    parsed = urlparse(href)
    if parsed.netloc.endswith("udemy.com") and parsed.path.startswith("/course/"):
        # slug is the segment after /course/
        slug = parsed.path.split("/")[2]
        # couponCode is in the query string
        coupon = parse_qs(parsed.query).get("couponCode", [""])[0]
        results.append((slug, coupon))

# 4) Print out what we found
for slug, coupon in results:
    print(f"slug: {slug}    couponCode: {coupon}")
