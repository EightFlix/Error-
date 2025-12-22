import time
import asyncio
import logging
from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait, MessageNotModified, ChatAdminRequired, UserNotParticipant
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, INDEX_LOG_CHANNEL
from database.ia_filterdb import save_file, detect_quality
from utils import temp, get_readable_time

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Lock to prevent concurrent indexing
lock = asyncio.Lock()

# Store active sessions
active_sessions = {}

# ======================================================
# 🛡️ SAFE MESSAGE EDIT (NO MESSAGE_NOT_MODIFIED)
# ======================================================
async def safe_edit(msg, text, **kwargs):
    """Safely edit message without raising MessageNotModified"""
    if not msg:
        return False
    
    try:
        # Check if text actually changed
        if hasattr(msg, 'text') and msg.text == text:
            return True
        
        await msg.edit_text(text, **kwargs)
        return True
    except MessageNotModified:
        return True
    except FloodWait as e:
        logger.warning(f"FloodWait in edit: {e.value}s")
        await asyncio.sleep(e.value)
        try:
            await msg.edit_text(text, **kwargs)
            return True
        except:
            return False
    except Exception as e:
        logger.error(f"Safe edit failed: {e}")
        return False


# ======================================================
# 🔁 CUSTOM ITERATOR (ANTI FLOOD SAFE)
# ======================================================
async def iter_messages(bot, chat_id, last_msg_id, skip):
    """
    Iterate through messages in batches with flood protection
    """
    current = skip
    total_fetched = 0
    
    while current < last_msg_id:
        # Check if cancelled
        if temp.CANCEL:
            logger.info("Iteration cancelled by user")
            break
        
        # Calculate batch range (max 200 messages per request)
        end = min(current + 200, last_msg_id)
        ids = list(range(current + 1, end + 1))
        
        try:
            # Fetch messages in batch
            messages = await bot.get_messages(chat_id, ids)
            
            # Yield each valid message
            for msg in messages:
                if msg and not msg.empty:
                    total_fetched += 1
                    yield msg
            
            logger.info(f"Fetched batch: {current}-{end} | Total: {total_fetched}")
            
        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value}s for batch {current}-{end}")
            await asyncio.sleep(e.value)
            continue
            
        except ChatAdminRequired:
            logger.error(f"Bot is not admin in chat {chat_id}")
            raise
            
        except Exception as e:
            logger.error(f"Fetch error {current}-{end}: {e}")
            # Continue to next batch instead of stopping
        
        # Update current position
        current = end
        
        # Small delay to avoid hitting rate limits
        await asyncio.sleep(0.5)


# ======================================================
# 🔍 VALIDATE CHANNEL ACCESS
# ======================================================
async def validate_channel_access(bot, chat_id):
    """Validate bot has access to channel"""
    try:
        chat = await bot.get_chat(chat_id)
        
        # Check if bot is member
        try:
            member = await bot.get_chat_member(chat_id, "me")
            if member.status not in [
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.OWNER
            ]:
                return False, "Bot must be admin in the channel"
        except UserNotParticipant:
            return False, "Bot is not a member of the channel"
        
        return True, chat
        
    except Exception as e:
        return False, str(e)


# ======================================================
# 📝 EXTRACT MEDIA INFO SAFELY
# ======================================================
def get_media_from_message(message):
    """Safely extract media from message"""
    if not message or not message.media:
        return None
    
    try:
        media_type = message.media.value
        media = getattr(message, media_type, None)
        
        if not media:
            return None
        
        # Set caption
        if hasattr(media, 'caption'):
            media.caption = message.caption or ""
        else:
            media.caption = message.caption or ""
        
        # Validate essential attributes
        if not hasattr(media, 'file_id') or not media.file_id:
            return None
        
        return media
        
    except Exception as e:
        logger.error(f"Media extraction error: {e}")
        return None


# ======================================================
# 🚀 /index COMMAND
# ======================================================
@Client.on_message(filters.command("index") & filters.private & filters.user(ADMINS))
async def index_start(_, message):
    """Start indexing process"""
    if lock.locked():
        return await message.reply(
            "⚠️ **Indexing already running!**\n\n"
            "Please wait for current process to complete."
        )
    
    # Store user session
    active_sessions[message.from_user.id] = {
        "state": "waiting_source",
        "timestamp": time.time()
    }
    
    await message.reply(
        "📌 **Manual Indexing**\n\n"
        "Send me one of the following:\n"
        "1️⃣ Channel post link (https://t.me/c/...)\n"
        "2️⃣ Forward any message from the channel\n\n"
        "⏱️ Timeout: 60 seconds",
        quote=True
    )


# ======================================================
# 📥 SOURCE HANDLER (LINK OR FORWARD)
# ======================================================
@Client.on_message(filters.private & filters.incoming & filters.user(ADMINS), group=20)
async def receive_source(bot, message):
    """Handle source input (link or forward)"""
    
    # Check if user has active session
    user_id = message.from_user.id
    if user_id not in active_sessions:
        return
    
    session = active_sessions[user_id]
    
    # Check session timeout (60 seconds)
    if time.time() - session["timestamp"] > 60:
        del active_sessions[user_id]
        return await message.reply("⏱️ Session expired. Use /index again.")
    
    # Prevent concurrent indexing
    if lock.locked():
        return await message.reply("⚠️ Indexing already running!")
    
    chat_id = None
    last_msg_id = None
    
    # ---- PARSE LINK ----
    if message.text and message.text.startswith("https://t.me"):
        try:
            parts = message.text.rstrip("/").split("/")
            last_msg_id = int(parts[-1])
            cid = parts[-2]
            
            # Convert channel username or ID
            if cid.startswith("c"):
                cid = cid[1:]  # Remove 'c'
            
            if cid.isnumeric():
                chat_id = int("-100" + cid)
            else:
                chat_id = "@" + cid
                
        except (IndexError, ValueError) as e:
            del active_sessions[user_id]
            return await message.reply(
                "❌ **Invalid message link!**\n\n"
                "Format: `https://t.me/c/123456/789`"
            )
    
    # ---- PARSE FORWARD ----
    elif message.forward_from_chat:
        if message.forward_from_chat.type == enums.ChatType.CHANNEL:
            chat_id = message.forward_from_chat.id
            last_msg_id = message.forward_from_message_id
        else:
            del active_sessions[user_id]
            return await message.reply("❌ Please forward from a **channel**, not a group!")
    
    else:
        # Not a valid source
        return
    
    # ---- VALIDATE CHANNEL ----
    if not chat_id or not last_msg_id:
        del active_sessions[user_id]
        return await message.reply("❌ Could not extract channel info!")
    
    checking = await message.reply("🔍 Validating channel access...")
    
    success, result = await validate_channel_access(bot, chat_id)
    if not success:
        del active_sessions[user_id]
        return await safe_edit(
            checking,
            f"❌ **Access Error**\n\n`{result}`\n\n"
            "Make sure:\n"
            "• Bot is added to the channel\n"
            "• Bot is admin with 'Read Messages' permission"
        )
    
    chat = result
    await safe_edit(checking, "✅ Channel access verified!")
    
    # ---- ASK FOR SKIP COUNT ----
    ask = await message.reply(
        "🔢 **Skip Count**\n\n"
        "Enter the message ID to start from (0 to start from beginning):\n\n"
        "⏱️ Timeout: 30 seconds"
    )
    
    try:
        response = await bot.listen(message.chat.id, timeout=30, filters=filters.text)
        skip = int(response.text)
        
        if skip < 0:
            skip = 0
        if skip >= last_msg_id:
            del active_sessions[user_id]
            return await safe_edit(ask, "❌ Skip value must be less than last message ID!")
        
    except asyncio.TimeoutError:
        del active_sessions[user_id]
        return await safe_edit(ask, "⏱️ Timeout! Use /index to restart.")
    except ValueError:
        del active_sessions[user_id]
        return await safe_edit(ask, "❌ Invalid number! Use /index to restart.")
    except Exception as e:
        del active_sessions[user_id]
        return await safe_edit(ask, f"❌ Error: {e}")
    
    # ---- CONFIRMATION ----
    total_to_scan = last_msg_id - skip
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🚀 START INDEXING",
            callback_data=f"idx#start#{chat_id}#{last_msg_id}#{skip}"
        )],
        [InlineKeyboardButton(
            "❌ CANCEL",
            callback_data="idx#cancel"
        )]
    ])
    
    await message.reply(
        f"📊 **Indexing Configuration**\n\n"
        f"📢 **Channel:** `{chat.title}`\n"
        f"🆔 **Chat ID:** `{chat_id}`\n"
        f"📦 **Last Message:** `{last_msg_id}`\n"
        f"⏭️ **Skip From:** `{skip}`\n"
        f"📂 **Total to Scan:** `{total_to_scan:,}`\n\n"
        f"⚡ This may take a while depending on channel size.",
        reply_markup=btn
    )
    
    # Update session state
    active_sessions[user_id]["state"] = "confirmed"


# ======================================================
# 🎛 CALLBACK HANDLER
# ======================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def index_callback(bot, query):
    """Handle indexing callbacks"""
    
    # Admin check
    if query.from_user.id not in ADMINS:
        return await query.answer("❌ Admin access only!", show_alert=True)
    
    data = query.data.split("#")
    action = data[1]
    
    # ---- CANCEL ----
    if action == "cancel":
        temp.CANCEL = True
        
        # Clear session
        if query.from_user.id in active_sessions:
            del active_sessions[query.from_user.id]
        
        await safe_edit(
            query.message,
            "⛔ **Indexing Cancelled**\n\n"
            "Use /index to start again."
        )
        return await query.answer("Cancelled!")
    
    # ---- START ----
    if action == "start":
        if lock.locked():
            return await query.answer("⚠️ Already running!", show_alert=True)
        
        await query.answer("🚀 Starting indexing...")
        await safe_edit(query.message, "🚀 **Indexing Started...**\n\nPlease wait...")
        
        try:
            chat_id = int(data[2]) if data[2].lstrip("-").isdigit() else data[2]
            last_msg_id = int(data[3])
            skip = int(data[4])
            
            await run_indexing(bot, query.message, chat_id, last_msg_id, skip)
            
        except Exception as e:
            logger.error(f"Start error: {e}")
            await safe_edit(
                query.message,
                f"❌ **Error**\n\n`{str(e)}`"
            )
        finally:
            # Clear session
            if query.from_user.id in active_sessions:
                del active_sessions[query.from_user.id]


# ======================================================
# ⚙️ CORE INDEX ENGINE (FIXED & OPTIMIZED)
# ======================================================
async def run_indexing(bot, msg, chat_id, last_msg_id, skip):
    """Main indexing logic with proper error handling"""
    
    start_time = time.time()
    scanned = saved = dup = err = skipped = 0
    last_update = time.time()
    
    temp.CANCEL = False
    
    async with lock:
        try:
            logger.info(f"Starting index: chat={chat_id}, last={last_msg_id}, skip={skip}")
            
            async for message in iter_messages(bot, chat_id, last_msg_id, skip):
                
                # Check cancel flag
                if temp.CANCEL:
                    logger.info("Indexing cancelled by user")
                    temp.CANCEL = False
                    break
                
                scanned += 1
                
                # Skip messages without media
                if not message.media:
                    skipped += 1
                    continue
                
                # Extract media safely
                media = get_media_from_message(message)
                if not media:
                    skipped += 1
                    continue
                
                # Detect quality
                quality = detect_quality(
                    getattr(media, 'file_name', ''),
                    media.caption
                )
                
                # Save to database
                try:
                    status = await save_file(media, quality=quality)
                    
                    if status == "suc":
                        saved += 1
                    elif status == "dup":
                        dup += 1
                    else:
                        err += 1
                        
                except Exception as e:
                    logger.error(f"Save error: {e}")
                    err += 1
                
                # Update progress every 5 seconds or every 100 files
                current_time = time.time()
                if (current_time - last_update > 5) or (scanned % 100 == 0):
                    elapsed = current_time - start_time
                    rate = scanned / elapsed if elapsed > 0 else 0
                    eta = ((last_msg_id - skip - scanned) / rate) if rate > 0 else 0
                    
                    progress_text = (
                        f"📦 **Indexing in Progress**\n\n"
                        f"📂 Scanned: `{scanned:,}`\n"
                        f"⚡ Saved: `{saved:,}`\n"
                        f"♻️ Duplicates: `{dup:,}`\n"
                        f"⏭️ Skipped: `{skipped:,}`\n"
                        f"❌ Errors: `{err:,}`\n\n"
                        f"📊 Rate: `{rate:.1f} msg/s`\n"
                        f"⏱️ Elapsed: `{get_readable_time(elapsed)}`\n"
                        f"⏳ ETA: `{get_readable_time(eta)}`"
                    )
                    
                    await safe_edit(
                        msg,
                        progress_text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⛔ STOP", callback_data="idx#cancel")]
                        ])
                    )
                    
                    last_update = current_time
            
            # ---- FINAL REPORT ----
            total_time = time.time() - start_time
            final_text = (
                f"✅ **Indexing Completed**\n\n"
                f"📂 Total Scanned: `{scanned:,}`\n"
                f"⚡ Successfully Saved: `{saved:,}`\n"
                f"♻️ Duplicates: `{dup:,}`\n"
                f"⏭️ Skipped: `{skipped:,}`\n"
                f"❌ Errors: `{err:,}`\n\n"
                f"⏱️ Total Time: `{get_readable_time(total_time)}`\n"
                f"📊 Average Rate: `{scanned/total_time:.1f} msg/s`"
            )
            
            await safe_edit(msg, final_text)
            
            # ---- LOG TO CHANNEL ----
            if INDEX_LOG_CHANNEL:
                try:
                    await bot.send_message(
                        INDEX_LOG_CHANNEL,
                        f"📊 **Indexing Summary**\n\n"
                        f"📢 Channel ID: `{chat_id}`\n"
                        f"📂 Scanned: `{scanned:,}`\n"
                        f"⚡ Saved: `{saved:,}`\n"
                        f"♻️ Duplicates: `{dup:,}`\n"
                        f"⏭️ Skipped: `{skipped:,}`\n"
                        f"❌ Errors: `{err:,}`\n"
                        f"⏱️ Time: `{get_readable_time(total_time)}`"
                    )
                except Exception as e:
                    logger.error(f"Log send error: {e}")
            
            logger.info(f"Indexing complete: scanned={scanned}, saved={saved}")
            
        except ChatAdminRequired:
            await safe_edit(
                msg,
                "❌ **Permission Error**\n\n"
                "Bot must be admin in the channel with 'Read Messages' permission."
            )
            
        except Exception as e:
            logger.error(f"Indexing error: {e}", exc_info=True)
            await safe_edit(
                msg,
                f"❌ **Indexing Error**\n\n"
                f"📂 Scanned: `{scanned:,}`\n"
                f"⚡ Saved: `{saved:,}`\n"
                f"Error: `{str(e)[:200]}`"
            )


# ======================================================
# 🧹 CLEANUP OLD SESSIONS (BACKGROUND TASK)
# ======================================================
async def cleanup_sessions():
    """Remove expired sessions every 5 minutes"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            
            current = time.time()
            expired = [
                uid for uid, session in active_sessions.items()
                if current - session["timestamp"] > 300  # 5 minutes
            ]
            
            for uid in expired:
                del active_sessions[uid]
            
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")
                
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


# Start cleanup task on import
asyncio.create_task(cleanup_sessions())
