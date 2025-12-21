import time
import os
import sys
import platform
from datetime import datetime

from hydrogram import Client, filters, enums
from hydrogram.errors import UserNotParticipant
from utils import temp
from info import IS_PREMIUM


# ======================================================
# 👤 USER INFO
# ======================================================

@Client.on_message(filters.command("info"))
async def user_info(client, message):
    status = await message.reply_text("🔍 Fetching user info…")

    user_id = (
        message.reply_to_message.from_user.id
        if message.reply_to_message
        else message.from_user.id
    )

    try:
        user = await client.get_users(user_id)
    except Exception as e:
        return await status.edit(f"❌ Error: {e}")

    text = (
        f"<b>👤 USER INFO</b>\n\n"
        f"<b>Name:</b> {user.first_name or ''} {user.last_name or ''}\n"
        f"<b>User ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> @{user.username if user.username else 'N/A'}\n"
        f"<b>DC ID:</b> <code>{user.dc_id or 'Unknown'}</code>\n"
        f"<b>Status:</b> {last_online(user)}\n"
        f"<b>Profile:</b> <a href='tg://user?id={user.id}'>Open</a>\n"
    )

    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        try:
            member = await message.chat.get_member(user.id)
            if member.joined_date:
                text += (
                    f"<b>Joined Group:</b> "
                    f"<code>{member.joined_date.strftime('%d %b %Y')}</code>\n"
                )
        except UserNotParticipant:
            pass

    if user.photo:
        photo = await client.download_media(user.photo.big_file_id)
        await message.reply_photo(photo, caption=text, parse_mode=enums.ParseMode.HTML)
        os.remove(photo)
    else:
        await message.reply_text(text, parse_mode=enums.ParseMode.HTML)

    await status.delete()


# ======================================================
# ⏱️ UPTIME
# ======================================================

@Client.on_message(filters.command("uptime"))
async def uptime_cmd(client, message):
    uptime = int(time.time() - temp.START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60

    await message.reply_text(
        f"⏱️ <b>Bot Uptime</b>\n\n<code>{h}h {m}m</code>",
        parse_mode=enums.ParseMode.HTML
    )


# ======================================================
# 🏓 PING
# ======================================================

@Client.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    start = time.time()
    msg = await message.reply_text("🏓 Pinging…")
    end = time.time()

    await msg.edit_text(
        f"🏓 <b>Pong!</b>\n\n⚡ <code>{int((end - start) * 1000)} ms</code>",
        parse_mode=enums.ParseMode.HTML
    )


# ======================================================
# 🤖 BOT INFO
# ======================================================

@Client.on_message(filters.command("botinfo"))
async def bot_info(client, message):
    uptime = int(time.time() - temp.START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60

    text = (
        f"🤖 <b>BOT INFO</b>\n\n"
        f"⏱️ Uptime: <code>{h}h {m}m</code>\n"
        f"🐍 Python: <code>{sys.version.split()[0]}</code>\n"
        f"⚙️ Platform: <code>{platform.system()}</code>\n"
        f"📦 Library: <code>Hydrogram</code>\n"
        f"💎 Premium System: <code>{'ON' if IS_PREMIUM else 'OFF'}</code>\n"
        f"🚀 Mode: <code>Ultra-Pro (Optimized)</code>"
    )

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


# ======================================================
# 🩺 HEALTH CHECK (ULTRA-LIGHT)
# ======================================================

@Client.on_message(filters.command("health"))
async def health_cmd(client, message):
    start = time.time()
    # micro await to ensure event loop is responsive
    await client.get_me()
    latency = int((time.time() - start) * 1000)

    uptime = int(time.time() - temp.START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60

    text = (
        f"🩺 <b>BOT HEALTH</b>\n\n"
        f"🟢 Status: <b>Healthy</b>\n"
        f"⚡ Event Loop: <code>{latency} ms</code>\n"
        f"⏱️ Uptime: <code>{h}h {m}m</code>\n"
        f"💎 Premium: <code>{'Enabled' if IS_PREMIUM else 'Disabled'}</code>\n"
        f"🧠 Memory: <code>Stable</code>\n"
        f"🚀 Performance: <code>Optimal</code>"
    )

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


# ======================================================
# 🕒 LAST ONLINE HELPER
# ======================================================

def last_online(user):
    if user.is_bot:
        return "🤖 Bot"
    if user.status == enums.UserStatus.ONLINE:
        return "🟢 Online"
    if user.status == enums.UserStatus.RECENTLY:
        return "Recently"
    if user.status == enums.UserStatus.LAST_WEEK:
        return "Within last week"
    if user.status == enums.UserStatus.LAST_MONTH:
        return "Within last month"
    if user.status == enums.UserStatus.LONG_AGO:
        return "Long time ago"
    if user.status == enums.UserStatus.OFFLINE:
        return user.last_online_date.strftime("%d %b %Y, %I:%M %p")
    return "Unknown"
