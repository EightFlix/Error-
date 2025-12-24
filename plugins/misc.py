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
# 🆔 ID COMMAND - Get User/Group/Channel IDs (ULTRA PREMIUM UI)
# ======================================================

@Client.on_message(filters.command("id"))
async def get_id(client, message):
    """Get ID of user, group, or channel with PREMIUM ADVANCED UI"""
    
    # Header with premium styling
    text = "╔════════════════════════════╗\n"
    text += "║   🆔 <b>IDENTITY SCANNER</b>   ║\n"
    text += "╚════════════════════════════╝\n\n"
    
    # If reply to a message
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        if replied_user:
            text += "╭─────────────────────────╮\n"
            text += "│ 👤 <b>REPLIED USER DETECTED</b> │\n"
            text += "╰─────────────────────────╯\n"
            text += f"┌ 📛 <b>Name</b>\n"
            text += f"│ ➜ <i>{replied_user.first_name or ''} {replied_user.last_name or ''}</i>\n"
            text += f"├ 🔖 <b>User ID</b>\n"
            text += f"│ ➜ <code>{replied_user.id}</code>\n"
            text += f"├ 🏷️ <b>Username</b>\n"
            text += f"│ ➜ @{replied_user.username if replied_user.username else '❌ Not Set'}\n"
            text += f"└ 🔗 <b>Profile Link</b>\n"
            text += f"  ➜ <a href='tg://user?id={replied_user.id}'>Click Here</a>\n\n"
        
        # If forwarded message
        if message.reply_to_message.forward_from:
            fwd_user = message.reply_to_message.forward_from
            text += "╭─────────────────────────╮\n"
            text += "│ 📤 <b>FORWARDED MESSAGE</b>   │\n"
            text += "╰─────────────────────────╯\n"
            text += f"┌ 📛 <b>Original Sender</b>\n"
            text += f"│ ➜ <i>{fwd_user.first_name or ''} {fwd_user.last_name or ''}</i>\n"
            text += f"├ 🔖 <b>Sender ID</b>\n"
            text += f"│ ➜ <code>{fwd_user.id}</code>\n"
            text += f"└ 🏷️ <b>Username</b>\n"
            text += f"  ➜ @{fwd_user.username if fwd_user.username else '❌ Not Set'}\n\n"
        
        # If forwarded from channel
        if message.reply_to_message.forward_from_chat:
            fwd_chat = message.reply_to_message.forward_from_chat
            chat_type_emoji = "📢" if fwd_chat.type == enums.ChatType.CHANNEL else "👥"
            chat_type_name = "CHANNEL" if fwd_chat.type == enums.ChatType.CHANNEL else "GROUP"
            text += f"╭─────────────────────────╮\n"
            text += f"│ {chat_type_emoji} <b>SOURCE {chat_type_name}</b>      │\n"
            text += f"╰─────────────────────────╯\n"
            text += f"┌ 📛 <b>Title</b>\n"
            text += f"│ ➜ <i>{fwd_chat.title}</i>\n"
            text += f"├ 🔖 <b>Chat ID</b>\n"
            text += f"│ ➜ <code>{fwd_chat.id}</code>\n"
            text += f"└ 🏷️ <b>Username</b>\n"
            text += f"  ➜ @{fwd_chat.username if fwd_chat.username else '❌ Not Set'}\n\n"
    
    # Current user info (ALWAYS SHOW)
    text += "╭─────────────────────────╮\n"
    text += "│ 🙋‍♂️ <b>YOUR IDENTITY</b>      │\n"
    text += "╰─────────────────────────╯\n"
    text += f"┌ 📛 <b>Name</b>\n"
    text += f"│ ➜ <i>{message.from_user.first_name or ''} {message.from_user.last_name or ''}</i>\n"
    text += f"├ 🔖 <b>User ID</b>\n"
    text += f"│ ➜ <code>{message.from_user.id}</code>\n"
    text += f"├ 🏷️ <b>Username</b>\n"
    text += f"│ ➜ @{message.from_user.username if message.from_user.username else '❌ Not Set'}\n"
    text += f"└ 🔗 <b>Profile Link</b>\n"
    text += f"  ➜ <a href='tg://user?id={message.from_user.id}'>Click Here</a>\n\n"
    
    # Chat info (if in group/channel)
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        text += "╭─────────────────────────╮\n"
        text += "│ 👥 <b>GROUP INFORMATION</b>  │\n"
        text += "╰─────────────────────────╯\n"
        text += f"┌ 📛 <b>Title</b>\n"
        text += f"│ ➜ <i>{message.chat.title}</i>\n"
        text += f"├ 🔖 <b>Group ID</b>\n"
        text += f"│ ➜ <code>{message.chat.id}</code>\n"
        text += f"└ 🏷️ <b>Username</b>\n"
        text += f"  ➜ @{message.chat.username if message.chat.username else '❌ Not Set'}\n\n"
    elif message.chat.type == enums.ChatType.CHANNEL:
        text += "╭─────────────────────────╮\n"
        text += "│ 📢 <b>CHANNEL INFO</b>        │\n"
        text += "╰─────────────────────────╯\n"
        text += f"┌ 📛 <b>Title</b>\n"
        text += f"│ ➜ <i>{message.chat.title}</i>\n"
        text += f"├ 🔖 <b>Channel ID</b>\n"
        text += f"│ ➜ <code>{message.chat.id}</code>\n"
        text += f"└ 🏷️ <b>Username</b>\n"
        text += f"  ➜ @{message.chat.username if message.chat.username else '❌ Not Set'}\n\n"
    
    # Footer
    text += "╔════════════════════════════╗\n"
    text += "║ ⚡ <b>POWERED BY ULTRA-PRO</b> ║\n"
    text += "╚════════════════════════════╝"
    
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)


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
