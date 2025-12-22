import re
import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL
from database.users_chats_db import db

# =========================
# CONFIG
# =========================
LINK_DELETE_TIME = 300
MAX_WARNS = 3
AUTO_MUTE_TIME = 600

LINK_REGEX = re.compile(
    r"(https?://|t\.me/|telegram\.me/|bit\.ly|tinyurl|@\w+)",
    re.IGNORECASE
)

# =========================
# HELPERS
# =========================

def ist_time():
    """Get IST formatted time"""
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %I:%M %p")

async def log_action(client, text):
    """Safe logging to channel"""
    if not LOG_CHANNEL:
        return
    try:
        await client.send_message(LOG_CHANNEL, text)
    except Exception as e:
        print(f"Log failed: {e}")

async def warn_user(user_id, chat_id):
    """Increment user warning count"""
    try:
        data = await db.get_warn(user_id, chat_id)
        if not data:
            data = {"count": 0}
        data["count"] += 1
        await db.set_warn(user_id, chat_id, data)
        return data["count"]
    except:
        return 1

async def reset_warn(user_id, chat_id):
    """Clear user warnings"""
    try:
        await db.clear_warn(user_id, chat_id)
    except:
        pass

async def is_admin(client, chat_id, user_id):
    """Check if user is admin"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        )
    except:
        return False

# =========================
# AUTO-DELETE LINKS
# =========================

@Client.on_message(filters.group & filters.text, group=1)
async def auto_delete_links(client, message):
    """Auto-delete links after delay (for all users including admins)"""
    if not message.text:
        return

    try:
        settings = await db.get_settings(message.chat.id)
        if not settings or not settings.get("auto_delete", False):
            return
    except:
        return

    # Check if message contains link
    if LINK_REGEX.search(message.text):
        await asyncio.sleep(LINK_DELETE_TIME)
        try:
            await message.delete()
        except Exception as e:
            print(f"Auto-delete failed: {e}")

# =========================
# ANTI-LINK + WARN + MUTE
# =========================

@Client.on_message(filters.group & filters.text, group=2)
async def anti_link_handler(client, message):
    """Anti-link with warnings and auto-mute (skip admins)"""
    if not message.from_user or not message.text:
        return

    # Skip if user is admin or bot admin
    if await is_admin(client, message.chat.id, message.from_user.id):
        return
    
    if message.from_user.id in ADMINS:
        return

    try:
        settings = await db.get_settings(message.chat.id)
        if not settings or not settings.get("anti_link", False):
            return
    except:
        return

    # Check for links
    if not LINK_REGEX.search(message.text):
        return

    # Delete the message
    try:
        await message.delete()
    except Exception as e:
        print(f"Delete failed: {e}")
        return

    # Increment warnings
    warns = await warn_user(message.from_user.id, message.chat.id)

    # Auto-mute after MAX_WARNS
    if warns >= MAX_WARNS:
        until = datetime.utcnow() + timedelta(seconds=AUTO_MUTE_TIME)
        try:
            await client.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=message.from_user.id,
                permissions=enums.ChatPermissions(),
                until_date=until
            )
            
            # Reset warnings
            await reset_warn(message.from_user.id, message.chat.id)

            # Log action
            await log_action(
                client,
                f"🔇 **Auto Mute Triggered**\n\n"
                f"👤 User: {message.from_user.mention}\n"
                f"🆔 ID: `{message.from_user.id}`\n"
                f"🏷 Group: {message.chat.title}\n"
                f"💬 Chat ID: `{message.chat.id}`\n"
                f"⏱ Duration: 10 minutes\n"
                f"🕒 {ist_time()}"
            )
            
            # Notify in group
            try:
                await client.send_message(
                    message.chat.id,
                    f"🔇 {message.from_user.mention} has been muted for 10 minutes due to repeated link violations."
                )
            except:
                pass

        except Exception as e:
            print(f"Mute failed: {e}")

    else:
        # Send warning to user
        try:
            await client.send_message(
                message.from_user.id,
                f"⚠️ **Warning {warns}/{MAX_WARNS}**\n\n"
                f"Links are not allowed in **{message.chat.title}**.\n"
                f"After {MAX_WARNS} warnings, you will be muted for 10 minutes."
            )
        except:
            # If PM fails, send in group and delete after 5 seconds
            try:
                warn_msg = await message.reply(
                    f"⚠️ {message.from_user.mention} Warning {warns}/{MAX_WARNS}\n"
                    f"Links are not allowed!"
                )
                await asyncio.sleep(5)
                await warn_msg.delete()
            except:
                pass

        # Log warning
        await log_action(
            client,
            f"⚠️ **Link Violation**\n\n"
            f"👤 User: {message.from_user.mention}\n"
            f"🆔 ID: `{message.from_user.id}`\n"
            f"🏷 Group: {message.chat.title}\n"
            f"💬 Chat ID: `{message.chat.id}`\n"
            f"📊 Warns: {warns}/{MAX_WARNS}\n"
            f"🕒 {ist_time()}"
        )

# =========================
# SETTINGS MENU
# =========================

@Client.on_message(filters.command("settings") & filters.group)
async def settings_entry(client, message):
    """Entry point for settings in group"""
    if not message.from_user:
        return

    user_id = message.from_user.id
    
    # Check if user is admin
    if not await is_admin(client, message.chat.id, user_id) and user_id not in ADMINS:
        return await message.reply("❌ Only admins can access settings.")

    if not client.me:
        await client.get_me()

    await message.reply(
        "⚙️ **Group Settings**\n\n"
        "Click the button below to manage settings in PM 👇",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔐 Open Settings in PM",
                    url=f"https://t.me/{client.me.username}?start=connect_{message.chat.id}"
                )
            ]
        ])
    )

@Client.on_message(filters.command("start") & filters.private & filters.regex(r"^/start connect_"))
async def settings_pm(client, message):
    """Handle settings in PM"""
    try:
        chat_id = int(message.text.split("_")[1])
    except:
        return await message.reply("❌ Invalid connection data.")

    # Check if user is admin in that chat
    if not await is_admin(client, chat_id, message.from_user.id) and message.from_user.id not in ADMINS:
        return await message.reply("❌ You're not an admin in that group.")

    try:
        chat = await client.get_chat(chat_id)
        settings = await db.get_settings(chat_id)
        
        if not settings:
            settings = {"auto_delete": False, "anti_link": False}

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🧹 Auto Delete Links",
                    callback_data=f"gs_label"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Enabled" if settings.get("auto_delete", False) else "❌ Disabled",
                    callback_data=f"gs#auto_delete#{settings.get('auto_delete', False)}#{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 Anti-Link System",
                    callback_data=f"gs_label"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Enabled" if settings.get("anti_link", False) else "❌ Disabled",
                    callback_data=f"gs#anti_link#{settings.get('anti_link', False)}#{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data=f"gs#refresh#0#{chat_id}"
                )
            ]
        ])

        await message.reply(
            f"⚙️ **Moderation Settings**\n"
            f"**Group:** {chat.title}\n\n"
            f"🧹 **Auto Delete:** Deletes all links after 5 minutes\n"
            f"🚫 **Anti-Link:** Warns & mutes non-admins who send links",
            reply_markup=buttons
        )
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("^gs#"))
async def toggle_settings(client, query):
    """Handle settings toggle"""
    try:
        parts = query.data.split("#")
        if len(parts) != 4:
            return await query.answer("❌ Invalid data", show_alert=True)
        
        _, field, current, chat_id = parts
        chat_id = int(chat_id)

        # Check if user is admin
        if not await is_admin(client, chat_id, query.from_user.id) and query.from_user.id not in ADMINS:
            return await query.answer("❌ You're not an admin!", show_alert=True)

        # Handle refresh
        if field == "refresh":
            settings = await db.get_settings(chat_id)
            if not settings:
                settings = {"auto_delete": False, "anti_link": False}
        else:
            # Toggle setting
            new_value = current != "True"
            settings = await db.get_settings(chat_id)
            
            if not settings:
                settings = {}
            
            settings[field] = new_value
            await db.update_settings(chat_id, settings)

        # Update buttons
        chat = await client.get_chat(chat_id)
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🧹 Auto Delete Links",
                    callback_data=f"gs_label"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Enabled" if settings.get("auto_delete", False) else "❌ Disabled",
                    callback_data=f"gs#auto_delete#{settings.get('auto_delete', False)}#{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 Anti-Link System",
                    callback_data=f"gs_label"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Enabled" if settings.get("anti_link", False) else "❌ Disabled",
                    callback_data=f"gs#anti_link#{settings.get('anti_link', False)}#{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Refresh",
                    callback_data=f"gs#refresh#0#{chat_id}"
                )
            ]
        ])

        await query.edit_message_text(
            f"⚙️ **Moderation Settings**\n"
            f"**Group:** {chat.title}\n\n"
            f"🧹 **Auto Delete:** Deletes all links after 5 minutes\n"
            f"🚫 **Anti-Link:** Warns & mutes non-admins who send links",
            reply_markup=buttons
        )
        
        await query.answer("✅ Settings updated!")

    except Exception as e:
        print(f"Toggle error: {e}")
        await query.answer("❌ Error updating settings", show_alert=True)
