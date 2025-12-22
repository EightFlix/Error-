import asyncio
import pytz
import qrcode
import time
import random
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram.errors import UserNotParticipant, FloodWait
from hydrogram.types import InlineKeyboardButton

from info import ADMINS, IS_PREMIUM, TIME_ZONE
from database.users_chats_db import db
from shortzy import Shortzy


# =========================
# OPTIONAL SHORTLINK
# =========================
try:
    from info import SHORTLINK_API, SHORTLINK_URL
except ImportError:
    SHORTLINK_API = None
    SHORTLINK_URL = None


# ======================================================
# 🧠 GLOBAL RUNTIME STATE
# ======================================================

class temp(object):
    START_TIME = 0
    BOT = None

    ME = None
    U_NAME = None
    B_NAME = None

    SETTINGS = {}
    VERIFICATIONS = {}

    FILES = {}          # msg_id -> data
    PREMIUM = {}        # ⚡ RAM premium cache
    KEYWORDS = {}       # 🧠 auto-learned keywords

    INDEX_STATS = {
        "running": False,
        "start": 0,
        "scanned": 0,
        "saved": 0,
        "dup": 0,
        "err": 0
    }


# ======================================================
# 👑 PREMIUM CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=20)
PREMIUM_CACHE_TTL = 300   # 5 minutes


# ======================================================
# ⚡ ULTRA FAST PREMIUM CHECK (RAM → DB)
# ======================================================

async def is_premium(user_id, bot=None) -> bool:
    if not IS_PREMIUM or user_id in ADMINS:
        return True

    now_ts = time.time()
    cached = temp.PREMIUM.get(user_id)

    # ---- RAM CACHE ----
    if cached and now_ts - cached["checked_at"] < PREMIUM_CACHE_TTL:
        expire = cached["expire"]
        return bool(expire and datetime.utcnow() <= expire + GRACE_PERIOD)

    # ---- DB FALLBACK ----
    plan = db.get_plan(user_id)
    if not plan or not plan.get("premium"):
        temp.PREMIUM[user_id] = {
            "expire": None,
            "checked_at": now_ts
        }
        return False

    expire = plan.get("expire")
    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    if datetime.utcnow() > expire + GRACE_PERIOD:
        plan.update({
            "premium": False,
            "expire": "",
            "plan": "",
            "last_reminder": "expired"
        })
        db.update_plan(user_id, plan)
        temp.PREMIUM[user_id] = {
            "expire": None,
            "checked_at": now_ts
        }
        return False

    temp.PREMIUM[user_id] = {
        "expire": expire,
        "checked_at": now_ts
    }
    return True


# ======================================================
# 🛡 PREMIUM AUTO DOWNGRADE WATCHER
# ======================================================

async def check_premium(bot):
    while True:
        try:
            now = datetime.utcnow()

            for u in db.get_premium_users():
                uid = u["id"]
                if uid in ADMINS:
                    continue

                plan = u.get("plan", {})
                expire = plan.get("expire")
                if not expire:
                    continue

                if isinstance(expire, (int, float)):
                    expire = datetime.utcfromtimestamp(expire)

                if now > expire + GRACE_PERIOD:
                    plan.update({
                        "premium": False,
                        "expire": "",
                        "plan": ""
                    })
                    db.update_plan(uid, plan)

                    # clear RAM cache
                    temp.PREMIUM.pop(uid, None)

        except Exception:
            pass

        await asyncio.sleep(1800)  # 30 min


# ======================================================
# 🔔 SMART PREMIUM EXPIRY REMINDER
# ======================================================

REMINDER_STEPS = [
    ("1d", timedelta(days=1)),
    ("6h", timedelta(hours=6)),
    ("1h", timedelta(hours=1))
]

async def premium_expiry_reminder(bot):
    while True:
        try:
            now = datetime.utcnow()

            for user in db.get_premium_users():
                uid = user["id"]
                if uid in ADMINS:
                    continue

                plan = user.get("plan", {})
                expire = plan.get("expire")
                last = plan.get("last_reminder")

                if not expire:
                    continue

                if isinstance(expire, (int, float)):
                    expire = datetime.utcfromtimestamp(expire)

                for tag, delta in REMINDER_STEPS:
                    if last == tag:
                        continue

                    if expire - delta <= now < expire:
                        try:
                            await bot.send_message(
                                uid,
                                f"⏰ **Premium Expiry Alert**\n\n"
                                f"Your premium will expire in **{tag}**.\n"
                                "Renew now to avoid interruption."
                            )
                        except:
                            pass

                        plan["last_reminder"] = tag
                        db.update_plan(uid, plan)
                        break

        except Exception:
            pass

        await asyncio.sleep(1800)


# ======================================================
# 🧠 SMART SEARCH LEARNING (OFFLINE)
# ======================================================

def learn_keywords(text: str):
    for w in text.lower().split():
        if len(w) >= 3:
            temp.KEYWORDS[w] = temp.KEYWORDS.get(w, 0) + 1


def fast_similarity(a: str, b: str) -> int:
    if a == b:
        return 100
    a_set = set(a.split())
    b_set = set(b.split())
    common = a_set & b_set
    if not common:
        return 0
    score = int((len(common) / max(len(a_set), len(b_set))) * 100)
    for x in a_set:
        for y in b_set:
            if x.startswith(y) or y.startswith(x):
                score += 10
    return min(score, 100)


def suggest_query(query: str):
    best, score = None, 0
    for k in temp.KEYWORDS.keys():
        s = fast_similarity(query, k)
        if s > score:
            best, score = k, s
    return best if score >= 60 else None


# ======================================================
# 🎉 FESTIVAL + SMART GREETING
# ======================================================

FESTIVALS = {
    (3, 25): "holi",
    (11, 1): "diwali",
    (4, 10): "eid"
}

FESTIVAL_MSG = {
    "holi": "🎨 Happy Holi | होली मुबारक",
    "diwali": "🪔 Happy Diwali | दीपावली मुबारक",
    "eid": "🌙 Eid Mubarak | ईद मुबारक"
}

EMOJI_DAY = ["🌞", "✨", "🌤"]
EMOJI_NIGHT = ["🌙", "⭐", "😴"]


def detect_festival():
    now = datetime.now(pytz.timezone(TIME_ZONE))
    return FESTIVALS.get((now.month, now.day))


def get_wish(user_name: str = None):
    fest = detect_festival()
    if fest:
        return FESTIVAL_MSG.get(fest)

    hour = datetime.now(pytz.timezone(TIME_ZONE)).hour
    name = f", {user_name}" if user_name else ""

    if hour < 12:
        return f"{random.choice(EMOJI_DAY)} Good Morning{name}"
    if hour < 18:
        return f"{random.choice(EMOJI_DAY)} Good Afternoon{name}"
    return f"{random.choice(EMOJI_NIGHT)} Good Evening{name}"


# ======================================================
# 🔁 FILE MEMORY CLEANER (LEAK GUARD)
# ======================================================

async def cleanup_files_memory():
    while True:
        try:
            now = int(time.time())
            expired = [
                k for k, v in temp.FILES.items()
                if v.get("expire", 0) <= now
            ]
            for k in expired:
                temp.FILES.pop(k, None)
        except:
            pass

        await asyncio.sleep(60)


# ======================================================
# 🔳 QR CODE
# ======================================================

async def generate_qr_code(data: str):
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = "qr.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


# ======================================================
# 📦 SHORTLINK
# ======================================================

async def get_shortlink(url, api, link):
    if not api or not url:
        return link
    shortzy = Shortzy(api_key=api, base_site=url)
    return await shortzy.convert(link)


# ======================================================
# 🧰 SMALL UTILITIES
# ======================================================

def get_size(size):
    size = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def get_readable_time(seconds):
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    out = ""
    for name, sec in periods:
        if seconds >= sec:
            val, seconds = divmod(seconds, sec)
            out += f"{int(val)}{name} "
    return out.strip() or "0s"


async def get_settings(group_id):
    if group_id not in temp.SETTINGS:
        temp.SETTINGS[group_id] = await db.get_settings(group_id)
    return temp.SETTINGS[group_id]
