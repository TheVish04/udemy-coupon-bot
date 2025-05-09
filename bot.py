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
import html  # Added for HTML escaping

# ─── CONFIG ────────────────────────────────────────────────
TOKEN             = '7918306173:AAFFIedi9d4R8XDA0AlsOin8BCfJRJeNGWE'
CHAT_ID           = '@udemyfreecourses2080'
INTERVAL          = 1  # minutes between posts
SHEET_KEY         = '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70'
BASE_REDIRECT_URL = '[invalid url, do not cite]
PORT              = 10000  # health-check endpoint port
# ────────────────────────────────────────────────────────────

# Fallback coupons if sheet is empty or invalid
STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
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

    # Normalize header keys
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
    url = f"[invalid url, do not cite]
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp    = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup    = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        logger.warning(f"Failed to fetch course page for {slug}: {e}")
        return slug.replace('-', ' ').title(), None, '', 'N/A', 'N/A'

    # Title
    title_tag = soup.find('meta', property='og:title')
    title = title_tag['content'] if title_tag else slug.replace('-', ' ').title()

    # Thumbnail
    img_tag = soup.find('meta', property='og:image')
    img = img_tag['content'] if img_tag else None

    # Description
    desc_tag = soup.find('meta', property='og:description')
    desc = desc_tag['content'] if desc_tag else ''

    # Rating
    rating_tag = soup.select_one('span[data-purpose="rating-number"]')
    rating = rating_tag.text.strip() if rating_tag else 'N/A'

    # Students
    enroll_tag = soup.select_one('div[data-purpose="enrollment"]')
    students = enroll_tag.text.strip() if enroll_tag else 'N/A'

    return title, img, desc, rating, students

# ─── TELEGRAM SENDER ───────────────────────────────────────
def send_coupon():
    # Pick a random (slug, coupon) tuple
    slug, coupon = random.choice(fetch_coupons())
    redirect_url = f"{BASE_REDIRECT_URL}?udemy_url=" + urllib.parse.quote(
        f"[invalid url, do not cite] safe=''
    )

    # Fetch course details
    title, img, desc, rating, students = fetch_course_details(slug)

    # Escape HTML special characters
    title_escaped = html.escape(title)
    desc_escaped = html.escape(desc) if desc else ''

    # Build HTML caption dynamically
    caption_parts = []
    caption_parts.append(f"📚✏️ <b>{title_escaped}</b>")
    if rating != 'N/A':
        caption_parts.append(f"⭐ {rating}/5")
    if students != 'N/A':
        caption_parts.append(f"👩‍🎓 {students}")
    caption_parts.append("⏰ ASAP (limited seats!)")
    if desc_escaped:
        truncated_desc = desc[:200].strip() + "…"
        caption_parts.append(html.escape(truncated_desc))
    caption = "\n".join(caption_parts)

    # Prepare Telegram payload
    payload = {
        'chat_id':    CHAT_ID,
        'parse_mode': 'HTML',
        'reply_markup': json.dumps({
            'inline_keyboard': [[{
                'text': '🎓 Enroll Now',
                'url':  redirect_url
            }]]
        })
    }

    # Choose sendPhoto vs sendMessage
    if img:
        payload['photo'] = img
        payload['caption'] = caption
        api_endpoint   = f"[invalid url, do not cite]
    else:
        payload['text'] = caption
        api_endpoint    = f"[invalid url, do not cite]

    # Send to Telegram
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
    # 1) Start health-check server
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info(f"Health-check listening on port {PORT}")

    # 2) Send first coupon immediately
    logger.info("Startup: sending first coupon")
    send_coupon()

    # 3) Schedule periodic sends
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