import os
import logging
import random
import requests
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse

# ─── CONFIG ────────────────────────────────────────────────
TOKEN             = '7918306173:AAFFIedi9d4R8XDA0AlsOin8BCfJRJeNGWE'
CHAT_ID           = '@udemyfreecourses2080'
INTERVAL          = 10
SHEET_KEY         = '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70'
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
PORT              = 10000
# ────────────────────────────────────────────────────────────

# Static fallback coupons (only used if sheet fetch yields none)
STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
]

# ─── LOGGING & SCHEDULER SETUP ─────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
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
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            '/etc/secrets/credentials.json', scope
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY).sheet1
        records = sheet.get_all_records()
        logger.info(f"Fetched {len(records)} rows from Google Sheets")
        return records
    except Exception as e:
        logger.error(f"Error fetching sheet: {e}", exc_info=True)
        return None

# ─── URL BUILDERS ──────────────────────────────────────────
def build_udemy_url(slug, coupon):
    return f"https://www.udemy.com/course/{slug}/?couponCode={coupon}"

def build_redirect_link(slug, coupon):
    udemy_url = build_udemy_url(slug, coupon)
    encoded = urllib.parse.quote(udemy_url, safe='')
    return f"{BASE_REDIRECT_URL}?udemy_url={encoded}"

def fetch_coupons():
    sheet_vals = get_coupons_from_sheet()
    # If sheet fetch failed, immediately use static fallback
    if not sheet_vals:
        logger.info("No sheet data—using static coupons")
        return [build_redirect_link(s, c) for s, c in STATIC_COUPONS]

    # Normalize keys to lowercase & strip whitespace
    normalized = []
    for row in sheet_vals:
        low = {k.strip().lower(): v for k, v in row.items()}
        normalized.append(low)

    # Collect only rows that have both slug and couponcode
    valid = []
    for rec in normalized:
        if rec.get('slug') and rec.get('couponcode'):
            valid.append(build_redirect_link(rec['slug'], rec['couponcode']))

    if not valid:
        logger.warning("Sheet rows present but no valid slug/couponcode fields—using static coupons")
        return [build_redirect_link(s, c) for s, c in STATIC_COUPONS]

    logger.info(f"Using {len(valid)} coupons from sheet")
    return valid

# ─── TELEGRAM SENDER ───────────────────────────────────────
def send_coupon():
    coupons = fetch_coupons()
    url = random.choice(coupons)
    logger.info(f"Sending coupon: {url}")

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={'chat_id': CHAT_ID, 'text': f"🔖 Grab this discount:\n{url}"},
            timeout=10
        )
        resp.raise_for_status()
        j = resp.json()
        if j.get('ok'):
            logger.info(f"Message sent (id={j['result']['message_id']})")
        else:
            logger.error(f"Telegram API error: {j}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

# ─── MAIN ───────────────────────────────────────────────────
if __name__ == '__main__':
    # 1) Start health-check server in background
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info(f"Health-check endpoint listening on port {PORT}")

    # 2) Send first coupon immediately
    logger.info("Startup: sending first coupon immediately")
    send_coupon()

    # 3) Schedule further coupons every INTERVAL minutes
    logger.info(f"Scheduling coupons every {INTERVAL} minutes")
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
