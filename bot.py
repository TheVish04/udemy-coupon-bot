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
    except Exception:
        logger.error("Error fetching Google Sheet", exc_info=True)
        return None


def fetch_coupons():
    rows = get_coupons_from_sheet()
    if not rows:
        logger.info("No sheet data—using static fallback")
        return STATIC_COUPONS

    valid = []
    for row in rows:
        data = {k.strip().lower(): v for k, v in row.items()}
        slug = data.get('slug')
        code = data.get('couponcode') or data.get('coupon_code')
        if slug and code:
            valid.append((slug, code))

    if not valid:
        logger.warning("No valid coupons in sheet—using static fallback")
        return STATIC_COUPONS

    logger.info(f"Using {len(valid)} coupons from sheet")
    return valid


# ─── UDEMY SCRAPER ─────────────────────────────────────────
def fetch_course_details(course_url: str):
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(course_url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Open Graph metadata
    title = soup.find('meta', property='og:title')['content']
    thumbnail = soup.find('meta', property='og:image')['content']
    description = soup.find('meta', property='og:description')['content']

    # rating & enrollment
    rating_tag = soup.select_one('span[data-purpose="rating-number"]')
    rating = rating_tag.text.strip() if rating_tag else 'N/A'
    enroll_tag = soup.select_one('div[data-purpose="enrollment"]')
    students = enroll_tag.text.strip().split(' ')[0] if enroll_tag else 'N/A'

    return title, thumbnail, description, rating, students


# ─── TELEGRAM SENDER ───────────────────────────────────────
def send_coupon():
    slug, coupon = random.choice(fetch_coupons())
    # construct full Udemy URL with coupon code
    udemy_link = f"https://www.udemy.com/course/{slug}/?couponCode={coupon}"
    # redirect through our base URL
    redirect_url = f"{BASE_REDIRECT_URL}?udemy_url=" + urllib.parse.quote(udemy_link, safe='')

    try:
        title, img_url, desc, rating, students = fetch_course_details(udemy_link)
    except Exception:
        logger.warning("Scraping Udemy failed—using slug fallback", exc_info=True)
        title, img_url, desc, rating, students = (
            slug.replace('-', ' ').title(), None, '', 'N/A', 'N/A'
        )

    # truncate description cleanly
    snippet = (desc[:197].rsplit(' ', 1)[0] + '...') if desc and len(desc) > 200 else desc

    # Build HTML message
    caption_lines = [
        f"📚 <b>{title}</b>",
        f"🎁 <b>Coupon:</b> <code>{coupon}</code>",
        f"⭐ <b>Rating:</b> {rating}/5    👨‍🎓 <b>Enrolled:</b> {students}",
    ]
    if snippet:
        caption_lines.append(f"📖 {snippet}")
    caption = '\n'.join(caption_lines)

    keyboard = {
        'inline_keyboard': [[{'text': '🎓 Enroll Now', 'url': redirect_url}]]
    }

    payload = {'chat_id': CHAT_ID, 'parse_mode': 'HTML', 'reply_markup': json.dumps(keyboard)}

    if img_url:
        payload.update({'photo': img_url, 'caption': caption})
        api_endpoint = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    else:
        payload['text'] = caption + f"\n\n🔗 <a href=\"{redirect_url}\">Link</a>"
        api_endpoint = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        resp = requests.post(api_endpoint, data=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get('ok'):
            logger.info(f"Sent: {slug} ({coupon})")
        else:
            logger.error(f"Telegram API error: {result}")
    except Exception:
        logger.error("Failed to send to Telegram", exc_info=True)


# ─── MAIN ───────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info(f"Health-check on port {PORT}")

    logger.info("Sending first coupon...")
    send_coupon()

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
