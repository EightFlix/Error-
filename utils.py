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
# 🧠 GLOBAL RUNTIME STATE (Koyeb Optimized)
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

    INDEX_STATS = {
        "running": False,
        "start": 0,
        "scanned": 0,
        "saved": 0,
        "dup": 0,
        "err": 0
    }
    
    # Koyeb optimization flags
    _cleanup_running = False
    _reminder_running = False


# ======================================================
# 👑 PREMIUM CONFIG (Koyeb Optimized)
# ======================================================

GRACE_PERIOD = timedelta(minutes=20)
PREMIUM_CACHE_TTL = 600  # 10 min cache


# ======================================================
# ⚡ ULTRA FAST PREMIUM CHECK
# ======================================================

async def is_premium(user_id, bot=None) -> bool:
    """
    Koyeb optimized premium check with extended cache
    Returns True if user is premium, False otherwise
    """
    # Admins always have premium
    if user_id in ADMINS:
        return True
    
    # If premium system is disabled, everyone has access
    if not IS_PREMIUM:
        return True

    now_ts = time.time()
    cached = temp.PREMIUM.get(user_id)

    # Check cache first (10 min TTL)
    if cached and now_ts - cached["checked_at"] < PREMIUM_CACHE_TTL:
        expire = cached["expire"]
        if expire:
            return datetime.utcnow() <= expire + GRACE_PERIOD
        return False

    # Fetch from database
    try:
        plan = await db.get_plan(user_id)
    except Exception as e:
        print(f"[ERROR] is_premium DB error for user {user_id}: {e}")
        # On error, return cached value if exists
        if cached:
            expire = cached["expire"]
            return bool(expire and datetime.utcnow() <= expire + GRACE_PERIOD)
        return False

    # No plan or not premium
    if not plan or not plan.get("premium"):
        temp.PREMIUM[user_id] = {"expire": None, "checked_at": now_ts}
        return False

    # Get expiry date
    expire = plan.get("expire")
    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)
    elif not isinstance(expire, datetime):
        temp.PREMIUM[user_id] = {"expire": None, "checked_at": now_ts}
        return False

    # Check if expired (with grace period)
    now_utc = datetime.utcnow()
    if now_utc > expire + GRACE_PERIOD:
        # Don't auto-remove here - let background task handle it
        temp.PREMIUM[user_id] = {"expire": None, "checked_at": now_ts}
        return False

    # Cache and return
    temp.PREMIUM[user_id] = {"expire": expire, "checked_at": now_ts}
    return True


# ======================================================
# 🔔 PREMIUM EXPIRY REMINDER (Koyeb Optimized)
# ======================================================

REMINDER_STEPS = [
    ("1 day", timedelta(days=1)),
    ("6 hours", timedelta(hours=6)),
    ("1 hour", timedelta(hours=1))
]

async def premium_expiry_reminder(bot):
    """
    Koyeb optimized reminder with batch processing
    Sends reminders at: 1 day, 6 hours, 1 hour before expiry
    """
    if temp._reminder_running:
        print("[INFO] Reminder task already running, skipping...")
        return
    
    temp._reminder_running = True
    print("[INFO] ✅ Premium expiry reminder task started")
    
    while True:
        try:
            now = datetime.utcnow()
            users = await db.get_premium_users()
            
            if not users:
                await asyncio.sleep(1800)  # 30 min
                continue
            
            reminder_count = 0
            
            for user in users:
                try:
                    uid = user.get("_id") or user.get("id")
                    
                    if not uid or uid in ADMINS:
                        continue

                    plan = user.get("plan", {})
                    expire = plan.get("expire")
                    last = plan.get("last_reminder")

                    if not expire:
                        continue

                    # Convert to datetime
                    if isinstance(expire, (int, float)):
                        expire = datetime.utcfromtimestamp(expire)
                    elif not isinstance(expire, datetime):
                        continue

                    # Check each reminder step
                    for tag, delta in REMINDER_STEPS:
                        # Skip if already sent this reminder
                        if last == tag:
                            continue
                        
                        # Check if it's time for this reminder
                        if expire - delta <= now < expire:
                            try:
                                await bot.send_message(
                                    uid,
                                    "⏰ **Premium Expiry Alert**\n\n"
                                    f"Your premium will expire in **{tag}**.\n\n"
                                    "Use /plan to renew and continue enjoying premium benefits!"
                                )
                                
                                # Update last reminder
                                plan["last_reminder"] = tag
                                await db.update_plan(uid, plan)
                                
                                reminder_count += 1
                                print(f"[INFO] Sent {tag} reminder to user {uid}")
                                
                            except FloodWait as e:
                                print(f"[WARN] FloodWait {e.value}s for user {uid}")
                                await asyncio.sleep(e.value)
                            except Exception as e:
                                print(f"[ERROR] Failed to send reminder to {uid}: {e}")
                            
                            break  # Only send one reminder per user per iteration
                    
                    await asyncio.sleep(0.2)  # Rate limiting
                    
                except Exception as e:
                    print(f"[ERROR] Error processing reminder for user: {e}")
                    continue
            
            if reminder_count > 0:
                print(f"[INFO] Sent {reminder_count} premium expiry reminders")
                    
        except Exception as e:
            print(f"[ERROR] Premium reminder task error: {e}")
        
        await asyncio.sleep(1800)  # Run every 30 minutes


# ======================================================
# ✅ VERIFY SYSTEM (Koyeb Optimized)
# ======================================================

async def get_verify_status(user_id: int):
    """Get verification status with error handling"""
    try:
        if user_id not in temp.VERIFICATIONS:
            temp.VERIFICATIONS[user_id] = await db.get_verify_status(user_id)
        return temp.VERIFICATIONS[user_id]
    except Exception as e:
        print(f"[ERROR] Get verify status error for user {user_id}: {e}")
        return {}


async def update_verify_status(user_id: int, **kwargs):
    """Update verification status with error handling"""
    try:
        verify = await get_verify_status(user_id)
        verify.update(kwargs)
        temp.VERIFICATIONS[user_id] = verify
        await db.update_verify_status(user_id, verify)
    except Exception as e:
        print(f"[ERROR] Update verify status error for user {user_id}: {e}")


# ======================================================
# 🧠 SEARCH LEARNING + SUGGESTIONS (Koyeb Optimized)
# ======================================================

def learn_keywords(text: str):
    """Lightweight keyword learning with memory limit"""
    try:
        # Prevent memory bloat
        if len(temp.KEYWORDS) > 10000:
            sorted_kw = sorted(temp.KEYWORDS.items(), key=lambda x: x[1], reverse=True)
            temp.KEYWORDS = dict(sorted_kw[:5000])
        
        # Learn keywords from search text
        for w in text.lower().split():
            if 3 <= len(w) <= 50:
                temp.KEYWORDS[w] = temp.KEYWORDS.get(w, 0) + 1
    except Exception as e:
        print(f"[ERROR] Keyword learn error: {e}")


def fast_similarity(a: str, b: str) -> int:
    """Fast similarity check (0-100)"""
    try:
        if a == b:
            return 100
        a_set, b_set = set(a.split()), set(b.split())
        common = a_set & b_set
        if not common:
            return 0
        return min(int((len(common) / max(len(a_set), len(b_set))) * 100), 100)
    except:
        return 0


def suggest_query(query: str):
    """Suggest similar query based on learned keywords"""
    try:
        best, score = None, 0
        query_lower = query.lower()
        
        # Check top 500 keywords only
        for i, k in enumerate(temp.KEYWORDS):
            if i > 500:
                break
            s = fast_similarity(query_lower, k)
            if s > score:
                best, score = k, s
            
        return best if score >= 60 else None
    except Exception as e:
        print(f"[ERROR] Suggest query error: {e}")
        return None


# ======================================================
# 🎉 GREETING SYSTEM
# ======================================================

EMOJI_DAY = ["🌞", "✨", "🌤"]
EMOJI_NIGHT = ["🌙", "⭐", "😴"]


def get_wish(user_name=None, premium=False):
    """Get greeting message based on time of day"""
    try:
        hour = datetime.now(pytz.timezone(TIME_ZONE)).hour
        emoji = random.choice(EMOJI_DAY if hour < 18 else EMOJI_NIGHT)
        
        if premium:
            emoji = "👑 " + emoji

        name = f", {user_name}" if user_name else ""
        
        if hour < 12:
            return f"{emoji} Good Morning{name}"
        elif hour < 18:
            return f"{emoji} Good Afternoon{name}"
        else:
            return f"{emoji} Good Evening{name}"
    except Exception as e:
        print(f"[ERROR] Get wish error: {e}")
        return "Hello!"


# ======================================================
# 🔁 FILE MEMORY CLEANER (Koyeb Optimized)
# ======================================================

async def cleanup_files_memory():
    """
    Koyeb optimized memory cleanup
    Removes expired files and old premium cache
    """
    if temp._cleanup_running:
        print("[INFO] Cleanup task already running, skipping...")
        return
    
    temp._cleanup_running = True
    print("[INFO] ✅ File memory cleanup task started")
    
    while True:
        try:
            now = int(time.time())
            
            # Cleanup expired files
            expired = [k for k, v in temp.FILES.items() if v.get("expire", 0) <= now]
            if expired:
                for k in expired:
                    temp.FILES.pop(k, None)
                print(f"[INFO] Cleaned {len(expired)} expired files from memory")
            
            # Cleanup old premium cache (keep only 1000 most recent)
            if len(temp.PREMIUM) > 1000:
                old_keys = list(temp.PREMIUM.keys())[:500]
                for k in old_keys:
                    temp.PREMIUM.pop(k, None)
                print(f"[INFO] Cleaned {len(old_keys)} old premium cache entries")
            
            # Cleanup keywords if too many
            if len(temp.KEYWORDS) > 10000:
                sorted_kw = sorted(temp.KEYWORDS.items(), key=lambda x: x[1], reverse=True)
                temp.KEYWORDS = dict(sorted_kw[:5000])
                print(f"[INFO] Cleaned keywords, kept top 5000")
                    
        except Exception as e:
            print(f"[ERROR] Cleanup task error: {e}")
        
        await asyncio.sleep(120)  # Run every 2 minutes


# ======================================================
# 📢 BROADCAST HELPERS (Koyeb Optimized)
# ======================================================

async def broadcast_messages(user_id, message, pin=False):
    """Broadcast message to user with flood protection"""
    try:
        msg = await message.copy(chat_id=user_id)
        if pin:
            try:
                await msg.pin(both_sides=True)
            except:
                pass
        return "Success"
    except FloodWait as e:
        if e.value > 300:
            return "Error"
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message, pin)
    except Exception as e:
        print(f"[ERROR] Broadcast error for user {user_id}: {e}")
        try:
            await db.delete_user(int(user_id))
        except:
            pass
        return "Error"


async def groups_broadcast_messages(chat_id, message, pin=False):
    """Broadcast message to group with flood protection"""
    try:
        msg = await message.copy(chat_id=chat_id)
        if pin:
            try:
                await msg.pin()
            except:
                pass
        return "Success"
    except FloodWait as e:
        if e.value > 300:
            return "Error"
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except Exception as e:
        print(f"[ERROR] Group broadcast error for {chat_id}: {e}")
        try:
            await db.delete_chat(chat_id)
        except:
            pass
        return "Error"


# ======================================================
# 🔔 FORCE SUB CHECK (Koyeb Optimized)
# ======================================================

async def is_subscribed(bot, query):
    """Check if user is subscribed to required channels"""
    buttons = []

    try:
        # Premium users bypass force sub
        if await is_premium(query.from_user.id, bot):
            return buttons
    except Exception as e:
        print(f"[ERROR] Premium check error in is_subscribed: {e}")

    try:
        stg = await db.get_bot_sttgs()
        if not stg or not stg.get("FORCE_SUB_CHANNELS"):
            return buttons

        channels = stg["FORCE_SUB_CHANNELS"].split()
        
        for cid in channels:
            try:
                chat = await bot.get_chat(int(cid))
                await bot.get_chat_member(int(cid), query.from_user.id)
            except UserNotParticipant:
                invite = getattr(chat, 'invite_link', None)
                if invite:
                    buttons.append(
                        [InlineKeyboardButton(f"📢 Join {chat.title}", url=invite)]
                    )
            except Exception as e:
                print(f"[ERROR] Force sub check error for channel {cid}: {e}")
                continue
    except Exception as e:
        print(f"[ERROR] is_subscribed error: {e}")

    return buttons


# ======================================================
# 🔳 QR CODE (Koyeb Optimized)
# ======================================================

async def generate_qr_code(data: str):
    """Generate QR code with error handling"""
    try:
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        bio.name = "qr.png"
        img.save(bio, "PNG")
        bio.seek(0)
        return bio
    except Exception as e:
        print(f"[ERROR] QR generation error: {e}")
        return None


# ======================================================
# 📦 SHORTLINK (Koyeb Optimized)
# ======================================================

async def get_shortlink(url, api, link):
    """Get shortlink with timeout and error handling"""
    if not api or not url:
        return link
    
    try:
        return await asyncio.wait_for(
            Shortzy(api_key=api, base_site=url).convert(link),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        print(f"[WARN] Shortlink timeout")
        return link
    except Exception as e:
        print(f"[ERROR] Shortlink error: {e}")
        return link


# ======================================================
# 🧰 UTILITIES
# ======================================================

def get_size(size):
    """Convert bytes to human readable format"""
    try:
        size = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"
    except:
        return "0 B"


def get_readable_time(seconds):
    """Convert seconds to readable time"""
    try:
        periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
        out = ""
        for name, sec in periods:
            if seconds >= sec:
                val, seconds = divmod(seconds, sec)
                out += f"{int(val)}{name} "
        return out.strip() or "0s"
    except:
        return "0s"


async def get_settings(group_id):
    """Get group settings with caching"""
    try:
        if group_id not in temp.SETTINGS:
            temp.SETTINGS[group_id] = await db.get_settings(group_id)
        return temp.SETTINGS[group_id]
    except Exception as e:
        print(f"[ERROR] Get settings error for group {group_id}: {e}")
        return {}
