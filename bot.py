import os
import logging
import random
import requests
import threading
import time
import json
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
from bs4 import BeautifulSoup

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# ─── CONFIG ────────────────────────────────────────────────
TOKEN             = '7918306173:AAFFIedi9d4R8XDA0AlsOin8BCfJRJeNGWE'
CHAT_ID           = '@udemyfreecourses2080'
INTERVAL          = random.randint(60, 120)  # seconds between posts
SHEET_KEY         = '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70'
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
PORT              = 10000  # health-check endpoint port
# ────────────────────────────────────────────────────────────

# List of user agents to rotate through
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
]

# Fallback coupons if sheet is empty or invalid
STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3')
    # ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
    # ('it-security-101-protecting-and-securing-computer-networks', 'B938BDB811ABEDBBDD79'),
]

# ─── LOGGING & SCHEDULER SETUP ─────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
logger    = logging.getLogger(__name__)
scheduler = BlockingScheduler(timezone="UTC")
# ────────────────────────────────────────────────────────────

# Track the current position in the coupon list
current_coupon_index = 0

# ─── FLASK HEALTH CHECK ────────────────────────────────────
app = Flask(__name__)

@app.route("/healthz")
def healthz():
    return "OK", 200

def run_health_server():
    app.run(host="0.0.0.0", port=PORT)

# ─── GOOGLE SHEETS FETCH ───────────────────────────────────
def get_coupons_from_sheet():
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    try:
        creds  = ServiceAccountCredentials.from_json_keyfile_name(
            '/etc/secrets/credentials.json', scope
        )
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(SHEET_KEY).sheet1
        rows   = sheet.get_all_records()
        logger.info(f"Fetched {len(rows)} rows from Google Sheets")
        return rows
    except Exception as e:
        logger.error("Error fetching Google Sheet", exc_info=True)
        return None

def fetch_coupons():
    rows = get_coupons_from_sheet()
    if not rows:
        logger.info("No sheet data—using static fallback")
        return STATIC_COUPONS

    # normalize header keys
    valid = []
    for row in rows:
        low = {k.strip().lower(): v for k, v in row.items()}
        slug = low.get('slug')
        code = low.get('couponcode') or low.get('coupon_code')
        if slug and code:
            valid.append((slug, code))

    if not valid:
        logger.warning("No valid slug/couponcode in sheet—using static fallback")
        return STATIC_COUPONS

    logger.info(f"Using {len(valid)} coupons from sheet")
    return valid

def get_next_coupon():
    """Get the next coupon in sequence"""
    global current_coupon_index
    
    all_coupons = fetch_coupons()
    
    if not all_coupons:
        logger.warning("No coupons found, using static fallback")
        return STATIC_COUPONS[0]
    
    # Get the coupon at the current index
    coupon = all_coupons[current_coupon_index]
    
    # Update the index for the next call, wrapping around to 0 if we reach the end
    current_coupon_index = (current_coupon_index + 1) % len(all_coupons)
    
    logger.info(f"Selected coupon at index {current_coupon_index-1} of {len(all_coupons)} total")
    return coupon

# ─── UDEMY SCRAPER ─────────────────────────────────────────
def fetch_course_details(slug):
    """
    Scrape Udemy course page for:
      - title
      - thumbnail (og:image)
      - description (og:description)
    And generate random rating and students instead of fetching them.
    """
    url = f"https://www.udemy.com/course/{slug}/"
    
    # Use a random user agent and add more browser-like headers
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    # Add a delay to avoid being rate-limited (random between 1-3 seconds)
    time.sleep(random.uniform(1, 3))
    
    try:
        # Try to get the course page
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Extract Open Graph metadata
        og_data = {}
        for meta in soup.find_all('meta', property=lambda x: x and x.startswith('og:')):
            og_data[meta['property']] = meta.get('content', '')
        
        # Get title, thumbnail, and description
        title = og_data.get('og:title')
        thumbnail = og_data.get('og:image')
        description = og_data.get('og:description')
        
        # If any of the key data is missing, raise an exception
        if not title or not thumbnail or not description:
            raise ValueError("Missing required metadata from course page")
            
        logger.info(f"Successfully scraped course: {slug}")
        
    except Exception as e:
        logger.warning(f"Scraping Udemy failed for {slug}—using fallback: {str(e)}")
        title = slug.replace('-', ' ').title()
        thumbnail = None
        description = 'Check out this course for exciting content!'

    # Generate random rating and students
    rating = round(random.uniform(4.0, 5.0), 1)  # Higher ratings look better
    students = random.randint(5000, 100000)      # More students look better

    return title, thumbnail, description, rating, students

# ─── TELEGRAM SENDER ───────────────────────────────────────
def send_coupon():
    try:
        # Get the next coupon in sequence
        slug, coupon = get_next_coupon()
        
        # Create redirect URL
        redirect_url = f"{BASE_REDIRECT_URL}?udemy_url=" + urllib.parse.quote(
            f"https://www.udemy.com/course/{slug}/?couponCode={coupon}", safe=''
        )

        # Get course details with retry mechanism
        retries = 3
        title, img, desc, rating, students = None, None, None, None, None
        
        while retries > 0:
            try:
                title, img, desc, rating, students = fetch_course_details(slug)
                break
            except Exception as e:
                logger.warning(f"Error fetching course details (attempt {4-retries}/3): {str(e)}")
                retries -= 1
                time.sleep(2)  # Wait 2 seconds before retry
        
        # If all retries failed, use fallback values
        if not title:
            title = slug.replace('-', ' ').title()
            img = None
            desc = 'Check out this course for exciting content!'
            rating = round(random.uniform(4.0, 5.0), 1)
            students = random.randint(5000, 100000)

        # Generate a random number for enrolls left (between 1 and 1000)
        enrolls_left = random.randint(1, 1000)

        # Format the description to a maximum of 200 characters with ellipsis
        short_desc = (desc[:197] + '...') if len(desc) > 200 else desc

        # Build HTML caption with structured format
        rating_text = f"{rating:.1f}/5"
        students_text = f"{students:,}"
        enrolls_left_text = f"{enrolls_left:,}"

        # Clean up title to prevent HTML parsing issues
        title = title.replace("<", "&lt;").replace(">", "&gt;")
        
        # Create a more enticing course topic
        course_topic = title.split(' - ')[0].lower().replace('full course', '').strip()
        if not course_topic:
            course_topic = "this topic"

        caption = (
            f"📚✏️ <b>{title}</b>\n"
            f"🏅 <b>CERTIFIED</b>\n"
            f"⏰ ASAP ({enrolls_left_text} Enrolls Left)\n"
            f"⭐ {rating_text}    👩‍🎓 {students_text} students\n"
            f"🌐 English (US)\n\n"
            f"💡 Learn everything you need to know as a {course_topic} beginner.\n"
            f"Become a {course_topic} expert!\n\n"
            f"🔗 <a href='{redirect_url}'>Enroll Now</a>"
        )

        payload = {
            'chat_id':    CHAT_ID,
            'caption':    caption,
            'parse_mode': 'HTML',
            'reply_markup': json.dumps({
                'inline_keyboard': [[{
                    'text': '🎓 Enroll Now',
                    'url':  redirect_url
                }]]
            })
        }

        # choose sendPhoto vs sendMessage
        if img:
            payload['photo'] = img
            api_endpoint = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        else:
            payload['text'] = caption
            api_endpoint = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            payload.pop('caption')

        # send to Telegram
        resp = requests.post(api_endpoint, data=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get('ok'):
            logger.info(f"Sent course card: {slug}")
        else:
            logger.error(f"Telegram API error: {result}")
            
    except Exception as e:
        logger.error("Failed to send coupon", exc_info=True)

# ─── MAIN ───────────────────────────────────────────────────
if __name__ == '__main__':
    # 1) start health-check server
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info(f"Health-check listening on port {PORT}")

    # 2) send first coupon immediately
    logger.info("Startup: sending first coupon")
    send_coupon()

    # 3) schedule periodic sends
    scheduler.add_job(
        send_coupon,
        'interval',
        seconds=INTERVAL,
        next_run_time=datetime.now() + timedelta(seconds=INTERVAL),
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")