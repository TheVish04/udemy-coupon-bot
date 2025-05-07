import os
import logging
import random
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ─── CONFIG ────────────────────────────────────────────────
TOKEN             = os.getenv('TELEGRAM_BOT_TOKEN', '7918306173:AAFFIedi9d4R8XDA0AlsOin8BCfJRJeNGWE')
CHAT_ID           = os.getenv('TELEGRAM_CHAT_ID', '@udemyfreecourses2080')
INTERVAL          = int(os.getenv('INTERVAL_MINUTES', '1'))
SHEET_KEY         = os.getenv('SHEET_KEY', '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70')  # Use env var name 'SHEET_KEY'
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
# ────────────────────────────────────────────────────────────

# Static fallback coupons (only used if sheet fails)
STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
]

def get_coupons_from_sheet():
    if not SHEET_KEY:
        logger.info("No SHEET_KEY provided, skipping Google Sheet fetch")
        return []
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY).sheet1
        rows = sheet.get_all_records()
        logger.info(f"Fetched {len(rows)} rows from Google Sheet")
        return [
            (r['slug'], r['couponCode'])
            for r in rows
            if r.get('slug') and r.get('couponCode')
        ]
    except Exception as e:
        logger.error(f"Error fetching Google Sheet: {e}")
        return []

# ─── SETUP ─────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s",
                    level=logging.INFO)
logger = logging.getLogger(__name__)
scheduler = BlockingScheduler(timezone="UTC")
# ────────────────────────────────────────────────────────────

def build_redirect_link(slug, coupon):
    return f"{BASE_REDIRECT_URL}?slug={slug}&coupon={coupon}"

def fetch_coupons():
    sheet_vals = get_coupons_from_sheet()
    if sheet_vals:
        logger.info(f"Loaded {len(sheet_vals)} coupons from Google Sheets")
        return [build_redirect_link(slug, code) for slug, code in sheet_vals]
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