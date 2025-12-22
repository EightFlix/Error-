import asyncio
import pytz
import qrcode
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram.errors import UserNotParticipant, FloodWait
from hydrogram.types import InlineKeyboardButton

from info import (
    ADMINS,
    IS_PREMIUM,
    TIME_ZONE
)

# ---- OPTIONAL SHORTLINK CONFIG (SAFE IMPORT) ----
try:
    from info import SHORTLINK_API, SHORTLINK_URL
except ImportError:
    SHORTLINK_API = None
    SHORTLINK_URL = None

from database.users_chats_db import db
from shortzy import Shortzy


# ======================================================
# 🧠 TEMP RUNTIME CACHE (GLOBAL STATE)
# ======================================================

class temp(object):
    START_TIME = 0
    BOT = None

    # runtime info
    ME = None
    U_NAME = None
    B_NAME = None

    # moderation
    BANNED_USERS = []
    BANNED_CHATS = []

    # index / broadcast flags
    CANCEL = False
    USERS_CANCEL = False
    GROUPS_CANCEL = False

    # runtime caches
    SETTINGS = {}
    VERIFICATIONS = {}
    FILES = {}

    # premium cache
    PREMIUM = {}

    # 🔥 INDEX LIVE STATS (ADMIN DASHBOARD USES THIS)
    INDEX_STATS = {
        "running": False,
        "start": 0,
        "scanned": 0,
        "saved": 0,
        "dup": 0,
        "err": 0
    }


# ======================================================
# 👑 PREMIUM CORE CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=20)


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

    # premium bypass
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
# ✅ VERIFY SYSTEM
# ======================================================

async def get_verify_status(user_id):
    if user_id not in temp.VERIFICATIONS:
        temp.VERIFICATIONS[user_id] = await db.get_verify_status(user_id)
    return temp.VERIFICATIONS[user_id]


async def update_verify_status(user_id, **kwargs):
    verify = await get_verify_status(user_id)
    verify.update(kwargs)
    temp.VERIFICATIONS[user_id] = verify
    await db.update_verify_status(user_id, verify)


# ======================================================
# 👑 PREMIUM CHECK (SYNCED)
# ======================================================

async def is_premium(user_id, bot=None) -> bool:
    if not IS_PREMIUM or user_id in ADMINS:
        return True

    mp = db.get_plan(user_id)
    if not mp or not mp.get("premium"):
        return False

    expire = mp.get("expire")
    if not expire:
        return False

    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    now = datetime.utcnow()

    if now <= expire + GRACE_PERIOD:
        return True

    mp.update({
        "premium": False,
        "plan": "",
        "expire": "",
        "last_reminder": "expired"
    })
    db.update_plan(user_id, mp)
    return False


# ======================================================
# 🛡️ LIGHT PREMIUM GUARDIAN
# ======================================================

async def check_premium(bot):
    while True:
        try:
            users = db.get_premium_users()
            now = datetime.utcnow()

            for u in users:
                uid = u["id"]
                if uid in ADMINS:
                    continue

                mp = u.get("status", {})
                expire = mp.get("expire")
                if not expire:
                    continue

                if isinstance(expire, (int, float)):
                    expire = datetime.utcfromtimestamp(expire)

                if now > expire + GRACE_PERIOD:
                    mp.update({
                        "premium": False,
                        "plan": "",
                        "expire": ""
                    })
                    db.update_plan(uid, mp)
        except:
            pass

        await asyncio.sleep(1800)


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
        await db.delete_user(int(user_id))
        return "Error"


async def groups_broadcast_messages(chat_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=chat_id)
        if pin:
            try:
                await msg.pin()
            except:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except:
        await db.delete_chat(chat_id)
        return "Error"


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
