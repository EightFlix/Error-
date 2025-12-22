import asyncio
import pytz
import qrcode
import time
import re
from io import BytesIO
from datetime import datetime, timedelta
from difflib import get_close_matches

from hydrogram.errors import UserNotParticipant, FloodWait
from hydrogram.types import InlineKeyboardButton

from info import ADMINS, IS_PREMIUM, TIME_ZONE

try:
    from info import SHORTLINK_API, SHORTLINK_URL
except ImportError:
    SHORTLINK_API = None
    SHORTLINK_URL = None

from database.users_chats_db import db
from shortzy import Shortzy


# ======================================================
# 🧠 GLOBAL RUNTIME STATE
# ======================================================

class temp(object):
    START_TIME = 0
    BOT = None

    ME = None
    U_NAME = None
    B_NAME = None

    BANNED_USERS = set()
    BANNED_CHATS = set()

    CANCEL = False
    USERS_CANCEL = False
    GROUPS_CANCEL = False

    SETTINGS = {}
    VERIFICATIONS = {}

    FILES = {}

    PREMIUM = {}

    INDEX_STATS = {
        "running": False,
        "start": 0,
        "scanned": 0,
        "saved": 0,
        "dup": 0,
        "err": 0
    }

    # 🔥 SMART SEARCH MEMORY (RUNTIME ONLY)
    SEARCH_MEMORY = set()


# ======================================================
# 👑 PREMIUM CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=20)


# ======================================================
# 🔁 MEMORY LEAK GUARD
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
                data = temp.FILES.pop(k, None)
                if data and data.get("task"):
                    data["task"].cancel()
        except:
            pass
        await asyncio.sleep(60)


# ======================================================
# 🔍 SMART SEARCH ENGINE (FAST)
# ======================================================

_HINDI_MAP = {
    "aa": "a", "ee": "i", "oo": "u",
    "ph": "f", "bh": "b", "sh": "s",
    "ch": "c", "kh": "k", "gh": "g"
}

_STOP_WORDS = {"the", "is", "of", "and", "to", "ka", "ki", "ke"}


def normalize_query(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)

    for k, v in _HINDI_MAP.items():
        text = text.replace(k, v)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_keywords(text: str):
    return [
        w for w in text.split()
        if len(w) > 1 and w not in _STOP_WORDS
    ]


def prefix_match(word: str):
    return {word[:i] for i in range(2, min(len(word) + 1, 7))}


def smart_variants(query: str):
    """
    Returns set of smart variants
    """
    norm = normalize_query(query)
    words = split_keywords(norm)

    variants = set(words)

    for w in words:
        variants |= prefix_match(w)
        close = get_close_matches(w, temp.SEARCH_MEMORY, n=2, cutoff=0.85)
        variants |= set(close)

    temp.SEARCH_MEMORY |= set(words)
    return list(variants)


def smart_search_tokens(query: str):
    """
    Main entry for filter.py
    """
    tokens = smart_variants(query)

    # ensure original query is first (FAST PATH)
    return [query] + [t for t in tokens if t != query]


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
# 🔔 FORCE SUB CHECK
# ======================================================

async def is_subscribed(bot, query):
    buttons = []

    if await is_premium(query.from_user.id, bot):
        return buttons

    stg = db.get_bot_sttgs()
    if not stg or not stg.get("FORCE_SUB_CHANNELS"):
        return buttons

    for cid in stg["FORCE_SUB_CHANNELS"].split():
        try:
            chat = await bot.get_chat(int(cid))
            await bot.get_chat_member(int(cid), query.from_user.id)
        except UserNotParticipant:
            buttons.append([
                InlineKeyboardButton(
                    f"📢 Join {chat.title}",
                    url=chat.invite_link
                )
            ])
        except:
            pass

    return buttons


# ======================================================
# 👑 PREMIUM CHECK
# ======================================================

async def is_premium(user_id, bot=None) -> bool:
    if not IS_PREMIUM or user_id in ADMINS:
        return True

    plan = db.get_plan(user_id)
    if not plan or not plan.get("premium"):
        return False

    expire = plan.get("expire")
    if not expire:
        return False

    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    if datetime.utcnow() <= expire + GRACE_PERIOD:
        return True

    plan.update({
        "premium": False,
        "expire": "",
        "plan": "",
        "last_reminder": "expired"
    })
    db.update_plan(user_id, plan)
    return False


# ======================================================
# 🧰 UTILITIES (UNCHANGED)
# ======================================================

def get_size(size):
    size = float(size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


async def get_shortlink(url, api, link):
    if not api or not url:
        return link
    shortzy = Shortzy(api_key=api, base_site=url)
    return await shortzy.convert(link)


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


def get_wish():
    hour = datetime.now(pytz.timezone(TIME_ZONE)).hour
    if hour < 12:
        return "🌞 Good Morning"
    if hour < 18:
        return "🌤 Good Afternoon"
    return "🌙 Good Evening"
