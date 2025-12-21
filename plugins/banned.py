import asyncio
from datetime import datetime, timedelta

from hydrogram import Client, filters, enums
from hydrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

from utils import temp
from database.users_chats_db import db
from info import ADMINS, SUPPORT_LINK, LOG_CHANNEL

# ======================================================
# ⚙️ CONFIG
# ======================================================

WARN_LIMIT = 3
FLOOD_LIMIT = 5
FLOOD_TIME = 6  # seconds

USER_MSG_CACHE = {}  # user_id -> [timestamps]

# ======================================================
# 🧠 HELPERS
# ======================================================

def parse_time(text: str):
    text = text.lower()
    num = int("".join(filter(str.isdigit, text)) or 0)
    if "m" in text:
        return timedelta(minutes=num)
    if "h" in text:
        return timedelta(hours=num)
    if "d" in text:
        return timedelta(days=num)
    return None


def admin_panel(uid: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Warn", callback_data=f"warn#{uid}"),
            InlineKeyboardButton("🔇 Mute", callback_data=f"mute#{uid}")
        ],
        [
            InlineKeyboardButton("🔒 SoftBan", callback_data=f"softban#{uid}"),
            InlineKeyboardButton("⏱ TempBan", callback_data=f"tempban#{uid}")
        ],
        [
            InlineKeyboardButton("🔓 Unban", callback_data=f"unban#{uid}")
        ]
    ])

# ======================================================
# 🔒 FILTERS
# ======================================================

async def banned_user(_, __, m: Message):
    return m.from_user and m.from_user.id in temp.BANNED_USERS

banned_filter = filters.create(banned_user)

# ======================================================
# 🚫 PRIVATE BANNED USER
# ======================================================

@Client.on_message(filters.private & banned_filter)
async def banned_pm(bot, message):
    ban = await db.get_ban_status(message.from_user.id)
    exp = ban.get("expire_at")

    if exp and exp < datetime.utcnow():
        await db.unban_user(message.from_user.id)
        temp.BANNED_USERS.remove(message.from_user.id)
        return await message.reply("✅ You are unbanned.")

    txt = (
        "🚫 <b>You are restricted</b>\n\n"
        f"<b>Reason:</b> <code>{ban.get('ban_reason','N/A')}</code>\n"
    )
    if exp:
        txt += f"<b>Expires:</b> {exp.strftime('%d %b %Y, %I:%M %p')}"

    await message.reply_text(
        txt,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🧑‍💻 Support", url=SUPPORT_LINK)]]
        )
    )

# ======================================================
# 👮 GROUP READ-ONLY (SOFTBAN / MUTE)
# ======================================================

@Client.on_message(filters.group & filters.incoming)
async def moderation_guard(bot, message: Message):
    if not message.from_user or message.from_user.id in ADMINS:
        return

    uid = message.from_user.id

    # --- flood detection ---
    now = datetime.utcnow().timestamp()
    USER_MSG_CACHE.setdefault(uid, [])
    USER_MSG_CACHE[uid].append(now)
    USER_MSG_CACHE[uid] = [t for t in USER_MSG_CACHE[uid] if now - t < FLOOD_TIME]

    if len(USER_MSG_CACHE[uid]) >= FLOOD_LIMIT:
        await auto_warn(bot, message, "Flood detected")
        return await message.delete()

    # --- banned / muted ---
    if uid in temp.BANNED_USERS:
        return await message.delete()

# ======================================================
# ⚠️ WARN SYSTEM
# ======================================================

async def auto_warn(bot, message, reason="Rule violation"):
    uid = message.from_user.id
    warns = await db.add_warn(uid)

    if warns >= WARN_LIMIT:
        await mute_user(bot, message.chat.id, uid, timedelta(hours=1))
        await db.reset_warn(uid)
        await bot.send_message(
            message.chat.id,
            f"🔇 {message.from_user.mention} muted (auto)"
        )
    else:
        await bot.send_message(
            message.chat.id,
            f"⚠️ Warning {warns}/{WARN_LIMIT}\nReason: {reason}",
            reply_markup=admin_panel(uid)
        )

@Client.on_message(filters.command("warn") & filters.group & filters.user(ADMINS))
async def warn_cmd(bot, message):
    if not message.reply_to_message:
        return
    await auto_warn(bot, message.reply_to_message, "Manual warn")

# ======================================================
# 🔇 MUTE / UNMUTE
# ======================================================

async def mute_user(bot, chat_id, uid, duration):
    await bot.restrict_chat_member(
        chat_id,
        uid,
        enums.ChatPermissions(),
        until_date=datetime.utcnow() + duration
    )
    await db.log_action("mute", uid)

@Client.on_message(filters.command("mute") & filters.group & filters.user(ADMINS))
async def mute_cmd(bot, message):
    if not message.reply_to_message:
        return
    duration = parse_time(message.command[1])
    if not duration:
        return await message.reply("Usage: /mute 10m | 1h | 1d")
    await mute_user(
        bot,
        message.chat.id,
        message.reply_to_message.from_user.id,
        duration
    )

@Client.on_message(filters.command("unmute") & filters.group & filters.user(ADMINS))
async def unmute_cmd(bot, message):
    if not message.reply_to_message:
        return
    await bot.restrict_chat_member(
        message.chat.id,
        message.reply_to_message.from_user.id,
        enums.ChatPermissions(can_send_messages=True)
    )

# ======================================================
# 🔒 SOFTBAN / TEMPBAN
# ======================================================

@Client.on_message(filters.command("softban") & filters.user(ADMINS))
async def softban(bot, message):
    uid = message.reply_to_message.from_user.id
    await db.ban_user(uid, "SoftBan", None)
    temp.BANNED_USERS.append(uid)

@Client.on_message(filters.command("tempban") & filters.user(ADMINS))
async def tempban(bot, message):
    uid = message.reply_to_message.from_user.id
    duration = parse_time(message.command[1])
    expire = datetime.utcnow() + duration
    await db.ban_user(uid, "TempBan", expire)
    temp.BANNED_USERS.append(uid)

@Client.on_message(filters.command("unban") & filters.user(ADMINS))
async def unban(bot, message):
    uid = int(message.command[1])
    await db.unban_user(uid)
    if uid in temp.BANNED_USERS:
        temp.BANNED_USERS.remove(uid)

# ======================================================
# 🔁 AUTO-UNBAN WORKER
# ======================================================

async def auto_unban_worker(bot):
    while True:
        for u in await db.get_banned_users():
            exp = u.get("expire_at")
            if exp and exp < datetime.utcnow():
                uid = u["id"]
                await db.unban_user(uid)
                if uid in temp.BANNED_USERS:
                    temp.BANNED_USERS.remove(uid)
                try:
                    await bot.send_message(uid, "✅ Temp-ban expired.")
                except:
                    pass
        await asyncio.sleep(300)

@Client.on_start()
async def start_workers(bot):
    asyncio.create_task(auto_unban_worker(bot))
