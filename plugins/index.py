import asyncio
from datetime import datetime
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from hydrogram.errors import FloodWait, MessageNotModified

from info import ADMINS
from database.ia_filterdb import save_file

# =====================================================
# STATE TRACKING
# =====================================================
INDEXING_STATE = {}
CANCEL_INDEX = {}  # 🛑 To track cancellation requests

# =====================================================
# MANUAL INDEX COMMAND
# =====================================================
@Client.on_message(filters.command("index") & filters.private)
async def index_command(bot: Client, message: Message):
    """Manual indexing command - /index"""
    uid = message.from_user.id
    
    # Admin check
    if uid not in ADMINS:
        return await message.reply("❌ This is an admin-only command!")
    
    # Show options
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Channel Post Link", callback_data="idx#link")],
        [InlineKeyboardButton("2️⃣ Forward Message", callback_data="idx#forward")],
        [InlineKeyboardButton("❌ Cancel", callback_data="idx#cancel")]
    ])
    
    await message.reply(
        "📑 **Manual Indexing**\n\n"
        "**Send me one of the following:**\n"
        "1️⃣ Channel post link (https://t.me/c/...)\n"
        "2️⃣ Forward any message from the channel\n\n"
        "⏱ **Timeout:** 60 seconds",
        reply_markup=buttons
    )
    
    # Set state
    INDEXING_STATE[uid] = {
        "active": True,
        "method": None,
        "timestamp": datetime.utcnow()
    }
    
    # Auto timeout after 60 seconds
    asyncio.create_task(auto_timeout(uid))

# =====================================================
# AUTO TIMEOUT
# =====================================================
async def auto_timeout(uid: int):
    """Auto-remove state after timeout"""
    await asyncio.sleep(60)
    if uid in INDEXING_STATE:
        INDEXING_STATE.pop(uid, None)

# =====================================================
# CALLBACK HANDLER (SETUP & STOP)
# =====================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def index_callback(bot: Client, query: CallbackQuery):
    """Handle indexing option callbacks"""
    uid = query.from_user.id
    
    if uid not in ADMINS:
        return await query.answer("❌ Admin only!", show_alert=True)
    
    data = query.data.split("#")[1]
    
    if data == "cancel":
        INDEXING_STATE.pop(uid, None)
        try:
            await query.message.edit("❌ Indexing cancelled.")
        except MessageNotModified:
            pass
        return await query.answer()
    
    if data == "link":
        INDEXING_STATE[uid] = {"active": True, "method": "link"}
        try:
            await query.message.edit(
                "📎 **Send Channel Post Link**\n\n"
                "**Example:**\n"
                "`https://t.me/c/1234567890/123`\n\n"
                "⏱ **Timeout:** 60 seconds"
            )
        except MessageNotModified:
            pass
    
    elif data == "forward":
        INDEXING_STATE[uid] = {"active": True, "method": "forward"}
        try:
            await query.message.edit(
                "📨 **Forward Message**\n\n"
                "Forward any message from the channel you want to index\n\n"
                "⏱ **Timeout:** 60 seconds"
            )
        except MessageNotModified:
            pass
    
    await query.answer()
    asyncio.create_task(auto_timeout(uid))

# 🛑 NEW: Callback to STOP indexing
@Client.on_callback_query(filters.regex("^stopidx#"))
async def stop_indexing_callback(bot: Client, query: CallbackQuery):
    uid = query.from_user.id
    
    if uid not in ADMINS:
        return await query.answer("❌ Admin only!", show_alert=True)
        
    _, channel_id = query.data.split("#")
    
    # Set global cancel flag for this channel
    CANCEL_INDEX[int(channel_id)] = True
    
    await query.answer("🛑 Stopping Indexing...", show_alert=True)
    try:
        await query.message.edit_text("🛑 **Stopping process... Please wait.**")
    except:
        pass

# =====================================================
# PROCESS FORWARDED MESSAGE
# =====================================================
@Client.on_message(filters.private & filters.forwarded)
async def process_forwarded(bot: Client, message: Message):
    """Handle forwarded messages for indexing"""
    uid = message.from_user.id
    
    if uid not in ADMINS:
        return
    
    state = INDEXING_STATE.get(uid)
    if not state or not state.get("active"):
        return
    
    if not message.forward_from_chat:
        return await message.reply("❌ Message must be forwarded from a channel!")
    
    channel = message.forward_from_chat
    channel_id = channel.id
    channel_title = channel.title or "Unknown Channel"
    
    try:
        chat = await bot.get_chat(channel_id)
        if not chat:
            return await message.reply("❌ Bot doesn't have access to this channel!")
    except Exception as e:
        return await message.reply(f"❌ Cannot access channel:\n`{str(e)[:150]}`")
    
    INDEXING_STATE.pop(uid, None)
    
    # Reset Cancel Flag
    CANCEL_INDEX[channel_id] = False
    
    status = await message.reply(
        f"⚡ **Starting Indexing**\n\n"
        f"📢 **Channel:** `{channel_title}`\n"
        f"🆔 **ID:** `{channel_id}`\n\n"
        f"⏳ Please wait, this may take a while..."
    )
    
    await run_channel_indexing(bot, status, channel_id, channel_title)

# =====================================================
# PROCESS CHANNEL LINK
# =====================================================
@Client.on_message(filters.private & filters.text)
async def process_link(bot: Client, message: Message):
    """Handle channel links for indexing"""
    uid = message.from_user.id
    
    if uid not in ADMINS:
        return
    
    state = INDEXING_STATE.get(uid)
    if not state or not state.get("active") or state.get("method") != "link":
        return
    
    if "t.me/" not in message.text:
        return await message.reply("❌ Please send a valid Telegram link!")
    
    text = message.text.strip()
    channel_id = None
    
    try:
        if "/c/" in text:
            parts = text.split("/c/")[1].split("/")
            raw_id = parts[0]
            channel_id = int("-100" + raw_id)
        elif "t.me/" in text:
            username = text.split("t.me/")[1].split("/")[0].replace("@", "")
            chat = await bot.get_chat(username)
            channel_id = chat.id
        else:
            return await message.reply("❌ Invalid link format!")
    
    except Exception as e:
        return await message.reply(f"❌ Error: `{str(e)[:100]}`")
    
    try:
        chat = await bot.get_chat(channel_id)
        channel_title = chat.title or "Unknown Channel"
    except Exception as e:
        return await message.reply(f"❌ Cannot access channel:\n`{str(e)[:150]}`")
    
    INDEXING_STATE.pop(uid, None)
    
    # Reset Cancel Flag
    CANCEL_INDEX[channel_id] = False
    
    status = await message.reply(
        f"⚡ **Starting Indexing**\n\n"
        f"📢 **Channel:** `{channel_title}`\n"
        f"🆔 **ID:** `{channel_id}`\n\n"
        f"⏳ Please wait, this may take a while..."
    )
    
    await run_channel_indexing(bot, status, channel_id, channel_title)

# =====================================================
# MAIN INDEXING LOGIC (UPDATED WITH FIX & STOP)
# =====================================================
async def run_channel_indexing(bot: Client, status: Message, channel_id: int, channel_title: str):
    """Index all media files from channel"""
    
    indexed = 0
    duplicates = 0
    errors = 0
    skipped = 0
    last_update = 0
    
    # 🛑 STOP BUTTON MARKUP
    stop_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop Indexing", callback_data=f"stopidx#{channel_id}")]])
    
    try:
        # ✅ FIX: Using get_chat_history instead of iter_chat_history
        async for msg in bot.get_chat_history(channel_id):
            
            # 🛑 CHECK CANCELLATION
            if CANCEL_INDEX.get(channel_id):
                await status.edit(
                    f"🛑 **Indexing Cancelled by Admin!**\n\n"
                    f"📢 **Channel:** `{channel_title}`\n"
                    f"📊 **Final Stats:**\n"
                    f"✅ New: `{indexed}` | ⏭ Dups: `{duplicates}`"
                )
                return  # Exit function completely

            # Skip non-media messages
            if not msg.media:
                skipped += 1
                continue
            
            media = msg.document or msg.video or msg.audio
            if not media:
                skipped += 1
                continue
            
            try:
                result = await save_file(media)
                
                if result == "suc":
                    indexed += 1
                elif result == "dup":
                    duplicates += 1
                else:
                    errors += 1
                
                # Update status every 50 files
                total_processed = indexed + duplicates + errors
                if total_processed > last_update + 50:
                    last_update = total_processed
                    try:
                        await status.edit(
                            f"⚡ **Indexing in Progress...**\n\n"
                            f"📢 {channel_title}\n\n"
                            f"✅ **New:** `{indexed}`\n"
                            f"⏭ **Duplicate:** `{duplicates}`\n"
                            f"❌ **Errors:** `{errors}`\n"
                            f"📊 **Total:** `{total_processed}`",
                            reply_markup=stop_btn  # 🛑 Added Stop Button
                        )
                        await asyncio.sleep(1)
                    except (MessageNotModified, Exception):
                        pass
            
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            
            except Exception:
                errors += 1
                continue
        
        # Final status (Completed)
        total = indexed + duplicates
        await status.edit(
            f"✅ **Indexing Complete!**\n\n"
            f"📢 **Channel:** `{channel_title}`\n"
            f"🆔 **ID:** `{channel_id}`\n\n"
            f"✅ **New Files:** `{indexed}`\n"
            f"⏭ **Duplicates:** `{duplicates}`\n"
            f"❌ **Errors:** `{errors}`\n"
            f"⏩ **Skipped:** `{skipped}`\n\n"
            f"🎉 **Total Indexed:** `{total}`"
        )
    
    except Exception as e:
        await status.edit(
            f"❌ **Indexing Failed!**\n\n"
            f"**Error:** `{str(e)[:200]}`\n\n"
            f"**Stats:**\n"
            f"✅ New: `{indexed}`\n"
            f"⏭ Duplicates: `{duplicates}`\n"
            f"❌ Errors: `{errors}`"
        )

# =====================================================
# QUICK INDEX & AUTO INDEX (UNCHANGED)
# =====================================================
@Client.on_message(filters.private & filters.media & filters.forwarded)
async def quick_index(bot: Client, message: Message):
    uid = message.from_user.id
    if uid not in ADMINS or not message.forward_from_chat:
        return
    
    media = message.document or message.video or message.audio
    if not media:
        return
    
    try:
        result = await save_file(media)
        if result == "suc": await message.react("✅")
        elif result == "dup": await message.react("⏭")
        else: await message.react("❌")
    except:
        pass

@Client.on_message(filters.channel & (filters.document | filters.video | filters.audio))
async def auto_index_channel(bot: Client, message: Message):
    media = message.document or message.video or message.audio
    if not media: return
    try: await save_file(media)
    except: pass

