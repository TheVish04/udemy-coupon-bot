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
TOKEN             = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_TOKEN')
CHAT_ID           = os.getenv('TELEGRAM_CHAT_ID', '@yourchannel')
INTERVAL          = int(os.getenv('INTERVAL_MINUTES', '10'))
SHEET_KEY         = os.getenv('SHEET_KEY', 'YOUR_SHEET_KEY')
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
PORT              = int(os.getenv('PORT', 10000))
# ────────────────────────────────────────────────────────────

STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
]

# ─── LOGGING SETUP ─────────────────────────────────────────
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
    # listen on all interfaces so Render can reach it
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
        data = sheet.get_all_records()
        logger.info(f"Fetched {len(data)} records from Google Sheets")
        return data
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
    records = get_coupons_from_sheet()
    if records:
        return [
            build_redirect_link(r['slug'], r['couponCode'])
            for r in records
            if 'slug' in r and 'couponCode' in r
        ]
    else:
        # fallback
        return [
            build_redirect_link(slug, code)
            for slug, code in STATIC_COUPONS
        ]

# ─── TELEGRAM SENDER ───────────────────────────────────────
def send_coupon():
    coupons = fetch_coupons()
    url = random.choice(coupons)
    logger.info(f"Sending coupon: {url}")

    resp = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={'chat_id': CHAT_ID, 'text': f"🔖 Grab this discount:\n{url}"},
        timeout=10
    )
    try:
        resp.raise_for_status()
        j = resp.json()
        if j.get('ok'):
            logger.info(f"Message sent (id={j['result']['message_id']})")
        else:
            logger.error(f"Telegram error: {j}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

# ─── MAIN ───────────────────────────────────────────────────
if __name__ == '__main__':
    # 1) Start the health endpoint in a background thread
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info(f"Health check endpoint running on port {PORT}")

    # 2) Fire off the first coupon immediately
    logger.info("Startup: sending first coupon immediately")
    send_coupon()

    # 3) Schedule periodic coupons
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
