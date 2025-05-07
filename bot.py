import os
import logging
import random
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# ─── CONFIG ────────────────────────────────────────────────
TOKEN             = os.getenv('TELEGRAM_BOT_TOKEN', '7918306173:AAFFIedi9d4R8XDA0AlsOin8BCfJRJeNGWE')
CHAT_ID           = os.getenv('TELEGRAM_CHAT_ID', '@udemyfreecourses2080')
INTERVAL          = int(os.getenv('INTERVAL_MINUTES', '10'))
SHEET_KEY         = os.getenv('SHEET_KEY', '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70')  # Use env var name 'SHEET_KEY'
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
# ────────────────────────────────────────────────────────────

# Static fallback coupons (only used if sheet fails)
STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
]

logger = logging.getLogger(__name__)

def get_coupons_from_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('/etc/secrets/credentials.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(os.getenv('SHEET_KEY')).sheet1
        data = sheet.get_all_records()
        logger.info(f"Successfully fetched sheet data: {len(data)} records")
        return data
    except Exception as e:
        logger.error(f"Error fetching Google Sheet: {str(e)}", exc_info=True)
        return None

# ─── SETUP ─────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",
                    level=logging.INFO)
logger = logging.getLogger(__name__)
scheduler = BlockingScheduler(timezone="UTC")
# ────────────────────────────────────────────────────────────

def build_udemy_url(slug, coupon):
    """Build the full Udemy URL with the slug and coupon code."""
    return f"https://www.udemy.com/course/{slug}/?couponCode={coupon}"

def build_redirect_link(slug, coupon):
    """Build the redirect link to the Blogger page with the encoded Udemy URL."""
    udemy_url = build_udemy_url(slug, coupon)
    encoded_udemy_url = urllib.parse.quote(udemy_url, safe='')
    return f"{BASE_REDIRECT_URL}?udemy_url={encoded_udemy_url}"

def fetch_coupons():
    sheet_vals = get_coupons_from_sheet()
    if sheet_vals:
        logger.info(f"Loaded {len(sheet_vals)} coupons from Google Sheets")
        return [build_redirect_link(record['slug'], record['couponCode']) for record in sheet_vals if 'slug' in record and 'couponCode' in record]
    else:
        logger.info("No sheet data—falling back to static list")
        return [build_redirect_link(slug, code) for slug, code in STATIC_COUPONS]

def send_coupon():
    coupons = fetch_coupons()
    url = random.choice(coupons)
    logger.info(f"Sending coupon: {url}")
    api = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': f"🔖 Grab this discount:\n{url}"}
    try:
        resp = requests.post(api, data=payload, timeout=10)
        resp.raise_for_status()
        j = resp.json()
        if j.get('ok'):
            logger.info(f"Successfully sent message id={j['result']['message_id']}")
        else:
            logger.error(f"Telegram API error: {j}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

if __name__ == '__main__':
    logger.info("Startup: sending first coupon immediately")
    send_coupon()

    logger.info(f"Scheduling next coupons every {INTERVAL} minutes")
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