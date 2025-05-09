import os
import logging
import random
import requests
import threading
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
INTERVAL          = 1  # minutes
SHEET_KEY         = '1aoHvwptKb6S3IbBFF6WdsWt6FsTeWlAKEcvk05IZj70'
BASE_REDIRECT_URL = 'https://udemyfreecoupons2080.blogspot.com'
PORT              = 10000
# ────────────────────────────────────────────────────────────

STATIC_COUPONS = [
    ('the-complete-python-bootcamp-from-zero-to-expert', 'ST6MT60525G3'),
    ('the-complete-matlab-course-for-wireless-comm-engineering', '59DE4A717B657B340C67'),
]

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
scheduler = BlockingScheduler(timezone="UTC")
app = Flask(__name__)

@app.route('/healthz')
def healthz(): return 'OK', 200

def run_health_server(): app.run(host='0.0.0.0', port=PORT)

# ─── Google Sheets Fetch ───────────────────────────────────
def get_coupons_from_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('/etc/secrets/credentials.json', scope)
        client = gspread.authorize(creds)
        rows = client.open_by_key(SHEET_KEY).sheet1.get_all_records()
        logger.info(f"Fetched {len(rows)} rows")
        return rows
    except Exception:
        logger.error('Sheet fetch failed', exc_info=True)
        return None

# ─── Coupon List ───────────────────────────────────────────
def fetch_coupons():
    rows = get_coupons_from_sheet()
    if not rows:
        logger.info('Using fallback coupons')
        return STATIC_COUPONS
    valid = [(r['slug'], r.get('couponcode') or r.get('coupon_code')) for r in rows if r.get('slug') and (r.get('couponcode') or r.get('coupon_code'))]
    return valid or STATIC_COUPONS

# ─── Udemy Scraper with OG tags ────────────────────────────
def fetch_course_details(full_url: str):
    headers = {'User-Agent':'Mozilla/5.0','Accept-Language':'en-US'}
    resp = requests.get(full_url, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, 'html.parser')

    def get_meta(prop):
        tag = soup.find('meta', property=prop)
        return tag['content'].strip() if tag and tag.get('content') else ''

    title = get_meta('og:title') or 'N/A'
    img = get_meta('og:image')
    desc = get_meta('og:description')
    locale = get_meta('og:locale')  # e.g. en_US
    if locale:
        parts = locale.split('_')
        lang = parts[0].capitalize() + (f" ({parts[1]})" if len(parts)>1 else '')
    else:
        # fallback to html lang
        lang_attr = soup.html.attrs.get('lang','')
        lang = lang_attr.capitalize() if lang_attr else 'N/A'

    # Rating & Enrollment
    rating_tag = soup.select_one('span[data-purpose="rating-number"]')
    rating = rating_tag.text.strip() if rating_tag else 'N/A'
    enroll_tag = soup.select_one('div[data-purpose="enrollment"]')
    students = enroll_tag.text.strip().split()[0] if enroll_tag else 'N/A'

    # Trim description snippet
    snippet = ''
    if desc:
        snippet = (desc[:197].rsplit(' ',1)[0] + '...') if len(desc)>200 else desc

    return title, img, snippet, rating, students, lang

# ─── Telegram Sender ───────────────────────────────────────
def send_coupon():
    slug, coupon = random.choice(fetch_coupons())
    udemy_link = f"https://www.udemy.com/course/{slug}/?couponCode={coupon}"
    redirect = f"{BASE_REDIRECT_URL}?udemy_url=" + urllib.parse.quote(udemy_link, safe='')

    title, img, snippet, rating, students, lang = fetch_course_details(udemy_link)

    lines = [
        f"📚 <b>{title}</b>",
        f"⏰ ASAP ({students} enrolled)",
        f"⭐ {rating}/5    👩‍🎓 {students} students",
        f"💬 {lang}",
    ]
    if snippet:
        lines.append(f"💡 {snippet}")

    caption = '\n'.join(lines)
    keyboard = {'inline_keyboard': [[{'text':'🎓 Enroll Now','url':redirect}]]}
    payload = {'chat_id':CHAT_ID,'parse_mode':'HTML','reply_markup':json.dumps(keyboard)}

    if img:
        payload.update({'photo':img,'caption':caption})
        api = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    else:
        payload['text'] = caption + f"\n\n🔗 <a href=\"{redirect}\">Enroll Here</a>"
        api = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        r = requests.post(api, data=payload, timeout=10)
        r.raise_for_status()
        logger.info(f"Sent: {slug} ({coupon})")
    except Exception:
        logger.error('Telegram send failed', exc_info=True)

# ─── Main ─────────────────────────────────────────────────
if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info(f"Health-check on port {PORT}")
    send_coupon()
    scheduler.add_job(send_coupon,'interval',minutes=INTERVAL,next_run_time=datetime.now()+timedelta(minutes=INTERVAL))
    try: scheduler.start()
    except: logger.info('Stopped')
