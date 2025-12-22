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

    FILES = {}          # msg_id -> delivery data
    PREMIUM = {}        # RAM premium cache
    KEYWORDS = {}       # learned keywords (RAM)

    LANG_USER = {}      # user_id -> hi/en
    LANG_GROUP = {}     # group_id -> hi/en

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
PREMIUM_CACHE_TTL = 300


# ======================================================
# ⚡ ULTRA FAST PREMIUM CHECK
# ======================================================

async def is_premium(user_id, bot=None) -> bool:
    if not IS_PREMIUM or user_id in ADMINS:
        return True

    now_ts = time.time()
    cached = temp.PREMIUM.get(user_id)

    if cached and now_ts - cached["checked_at"] < PREMIUM_CACHE_TTL:
        expire = cached["expire"]
        return bool(expire and datetime.utcnow() <= expire + GRACE_PERIOD)

    plan = db.get_plan(user_id)
    if not plan or not plan.get("premium"):
        temp.PREMIUM[user_id] = {"expire": None, "checked_at": now_ts}
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
        temp.PREMIUM[user_id] = {"expire": None, "checked_at": now_ts}
        return False

    temp.PREMIUM[user_id] = {"expire": expire, "checked_at": now_ts}
    return True


# ======================================================
# 🛡 PREMIUM WATCHER
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
                    plan.update({"premium": False, "expire": "", "plan": ""})
                    db.update_plan(uid, plan)
                    temp.PREMIUM.pop(uid, None)
        except:
            pass

        await asyncio.sleep(1800)


# ======================================================
# 🔔 PREMIUM EXPIRY REMINDER
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
                                "⏰ **Premium Expiry Alert**\n\n"
                                f"Your premium will expire in **{tag}**.\n"
                                "Renew now to avoid interruption."
                            )
                        except:
                            pass
                        plan["last_reminder"] = tag
                        db.update_plan(uid, plan)
                        break
        except:
            pass

        await asyncio.sleep(1800)


# ======================================================
# ✅ VERIFY SYSTEM (inline.py dependency)
# ======================================================

async def get_verify_status(user_id: int):
    if user_id not in temp.VERIFICATIONS:
        temp.VERIFICATIONS[user_id] = await db.get_verify_status(user_id)
    return temp.VERIFICATIONS[user_id]


async def update_verify_status(user_id: int, **kwargs):
    verify = await get_verify_status(user_id)
    verify.update(kwargs)
    temp.VERIFICATIONS[user_id] = verify
    await db.update_verify_status(user_id, verify)


# ======================================================
# 🧠 SEARCH LEARNING + SUGGESTIONS
# ======================================================

def learn_keywords(text: str):
    for w in text.lower().split():
        if len(w) >= 3:
            temp.KEYWORDS[w] = temp.KEYWORDS.get(w, 0) + 1


def fast_similarity(a: str, b: str) -> int:
    if a == b:
        return 100
    a_set, b_set = set(a.split()), set(b.split())
    common = a_set & b_set
    if not common:
        return 0
    score = int((len(common) / max(len(a_set), len(b_set))) * 100)
    return min(score, 100)


def suggest_query(query: str):
    best, score = None, 0
    for k in temp.KEYWORDS:
        s = fast_similarity(query, k)
        if s > score:
            best, score = k, s
    return best if score >= 60 else None


# ======================================================
# 🌍 LANGUAGE SYSTEM
# ======================================================

def set_user_lang(user_id, lang):
    temp.LANG_USER[user_id] = lang


def set_group_lang(group_id, lang):
    temp.LANG_GROUP[group_id] = lang


def get_lang(user_id=None, group_id=None, default="en"):
    if user_id in temp.LANG_USER:
        return temp.LANG_USER[user_id]
    if group_id in temp.LANG_GROUP:
        return temp.LANG_GROUP[group_id]
    return default


# ======================================================
# 🎉 FESTIVAL + GREETING
# ======================================================

FESTIVALS = {
    (3, 25): "holi",
    (11, 1): "diwali",
    (4, 10): "eid"
}

FESTIVAL_MSG = {
    "holi": {"en": "🎨 Happy Holi", "hi": "🎨 होली मुबारक"},
    "diwali": {"en": "🪔 Happy Diwali", "hi": "🪔 दीपावली मुबारक"},
    "eid": {"en": "🌙 Eid Mubarak", "hi": "🌙 ईद मुबारक"}
}

EMOJI_DAY = ["🌞", "✨", "🌤"]
EMOJI_NIGHT = ["🌙", "⭐", "😴"]


def detect_festival():
    now = datetime.now(pytz.timezone(TIME_ZONE))
    return FESTIVALS.get((now.month, now.day))


def get_wish(user_name=None, lang="en", premium=False):
    fest = detect_festival()
    if fest:
        return FESTIVAL_MSG[fest][lang]

    hour = datetime.now(pytz.timezone(TIME_ZONE)).hour
    emoji = random.choice(EMOJI_DAY if hour < 18 else EMOJI_NIGHT)
    if premium:
        emoji = "👑 " + emoji

    name = f", {user_name}" if user_name else ""
    if hour < 12:
        return f"{emoji} {'सुप्रभात' if lang=='hi' else 'Good Morning'}{name}"
    if hour < 18:
        return f"{emoji} {'नमस्ते' if lang=='hi' else 'Good Afternoon'}{name}"
    return f"{emoji} {'शुभ रात्रि' if lang=='hi' else 'Good Evening'}{name}"


# ======================================================
# 🔁 FILE MEMORY CLEANER
# ======================================================

async def cleanup_files_memory():
    while True:
        try:
            now = int(time.time())
            for k, v in list(temp.FILES.items()):
                if v.get("expire", 0) <= now:
                    temp.FILES.pop(k, None)
        except:
            pass
        await asyncio.sleep(60)


# ======================================================
# 📢 BROADCAST HELPERS
# ======================================================

async def broadcast_messages(user_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=user_id)
        if pin:
            await msg.pin(both_sides=True)
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message, pin)
    except:
        try:
            await db.delete_user(int(user_id))
        except:
            pass
        return "Error"


async def groups_broadcast_messages(chat_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=chat_id)
        if pin:
            await msg.pin()
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except:
        try:
            await db.delete_chat(chat_id)
        except:
            pass
        return "Error"


# ======================================================
# 🔔 FORCE SUB CHECK (inline.py fix)
# ======================================================

async def is_subscribed(bot, query):
    buttons = []

    try:
        if await is_premium(query.from_user.id, bot):
            return buttons
    except:
        pass

    stg = db.get_bot_sttgs()
    if not stg or not stg.get("FORCE_SUB_CHANNELS"):
        return buttons

    for cid in stg["FORCE_SUB_CHANNELS"].split():
        try:
            chat = await bot.get_chat(int(cid))
            await bot.get_chat_member(int(cid), query.from_user.id)
        except UserNotParticipant:
            buttons.append(
                [InlineKeyboardButton(f"📢 Join {chat.title}", url=chat.invite_link)]
            )
        except:
            pass

    return buttons


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
    return await Shortzy(api_key=api, base_site=url).convert(link)


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
