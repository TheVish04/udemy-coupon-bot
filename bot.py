import os
import logging
import random
import requests
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
from bs4 import BeautifulSoup

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse
import json

# ─── CONFIG ────────────────────────────────────────────────
TOKEN             = '7918306173:AAFFIedi9d4R8XDA0AlsOin8BCfJRJeNGWE'
CHAT_ID           = '@udemyfreecourses2080'
INTERVAL          = 1  # minutes between posts
SHEET_KEY         = '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70'
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
PORT              = 10000  # health-check endpoint port
# ────────────────────────────────────────────────────────────

# Fallback coupons if sheet is empty or invalid
STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
    ('it-security-101-protecting-and-securing-computer-networks', 'B938BDB811ABEDBBDD79'),
]

# ─── LOGGING & SCHEDULER SETUP ─────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
logger    = logging.getLogger(__name__)
scheduler = BlockingScheduler(timezone="UTC")
# ────────────────────────────────────────────────────────────

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

# ─── UDEMY SCRAPER ─────────────────────────────────────────
def fetch_course_details(slug):
    """
    Scrape Udemy course page for:
      - title
      - thumbnail (og:image)
      - description (og:description)
      - rating (data-purpose="rating-number")
      - students (data-purpose="enrollment")
    """
    url = f"https://www.udemy.com/course/{slug}/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp    = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup    = BeautifulSoup(resp.text, 'html.parser')

        # Open Graph metadata
        title       = soup.find('meta', property='og:title')['content']
        thumbnail   = soup.find('meta', property='og:image')['content']
        description = soup.find('meta', property='og:description')['content']

        # course rating
        rating_tag = soup.select_one('span[data-purpose="rating-number"]')
        rating     = float(rating_tag.text.strip()) if rating_tag and rating_tag.text.strip() else 0.0

        # student enrollment
        enroll_tag = soup.select_one('div[data-purpose="enrollment"]')
        students   = int(''.join(filter(str.isdigit, enroll_tag.text.strip()))) if enroll_tag else 0

        return title, thumbnail, description, rating, students
    except Exception as e:
        logger.warning(f"Scraping Udemy failed for {slug}—using fallback", exc_info=True)
        return (
            slug.replace('-', ' ').title(),
            None,
            'Check out this course for exciting content!',
            0.0,
            0
        )

# ─── TELEGRAM SENDER ───────────────────────────────────────
def send_coupon():
    # pick a random (slug, coupon) tuple
    slug, coupon = random.choice(fetch_coupons())
    redirect_url = f"{BASE_REDIRECT_URL}?udemy_url=" + urllib.parse.quote(
        f"https://www.udemy.com/course/{slug}/?couponCode={coupon}", safe=''
    )

    # try scraping real course data
    try:
        title, img, desc, rating, students = fetch_course_details(slug)
    except Exception:
        logger.warning("Scraping Udemy failed—using slug fallback", exc_info=True)
        title, img, desc, rating, students = (
            slug.replace('-', ' ').title(),
            None,
            '',
            0.0,
            0
        )

    # Format the description to a maximum of 200 characters with ellipsis
    short_desc = (desc[:197] + '...') if len(desc) > 200 else desc

    # Build HTML caption with structured format
    caption = (
        f"📚✏️ <b>{title}</b>\n"
        f"🏅 <b>CERTIFIED</b>\n"
        f"⏰ ASAP ({students} Enrolls Left)\n"
        f"⭐ {rating:.1f}/5    👩‍🎓 {students:,} students\n"
        f"🎓 IT & Software > IT Certifications\n"
        f"🌐 English (US)\n\n"
        f"💡 Learn everything you need to know as a {title.split(' - ')[0].lower().replace('full course', '').strip()} beginner.\n"
        f"Become a {title.split(' - ')[0].lower().replace('full course', '').strip()} expert!\n\n"
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
        api_endpoint   = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    else:
        payload['text']      = caption
        api_endpoint         = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload.pop('caption')

    # send to Telegram
    try:
        resp = requests.post(api_endpoint, data=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get('ok'):
            logger.info(f"Sent course card: {slug}")
        else:
            logger.error(f"Telegram API error: {result}")
    except Exception as e:
        logger.error("Failed to send to Telegram", exc_info=True)

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
        minutes=INTERVAL,
        next_run_time=datetime.now() + timedelta(minutes=INTERVAL)
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")