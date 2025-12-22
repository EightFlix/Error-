import asyncio
from hydrogram import Client, filters, enums
from hydrogram.errors import (
    FloodWait, 
    MessageNotModified,
    ReactionInvalid,
    ChatWriteForbidden
)
from info import INDEX_CHANNELS, LOG_CHANNEL
from database.ia_filterdb import (
    save_file,
    update_file_caption,
    detect_quality
)

# ─────────────────────────────────────────────
# MEDIA FILTER (VIDEO + DOCUMENT ONLY)
# ─────────────────────────────────────────────
media_filter = (filters.video | filters.document) & ~filters.edited

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

async def safe_react(message, emoji: str):
    """Safely react to message with error handling"""
    try:
        await message.react(emoji)
        return True
    except ReactionInvalid:
        # Reactions not supported in this chat
        return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await message.react(emoji)
            return True
        except:
            return False
    except Exception as e:
        print(f"React error: {e}")
        return False


async def safe_log(client, text: str):
    """Safely send log message"""
    if not LOG_CHANNEL:
        return False
    
    try:
        await client.send_message(LOG_CHANNEL, text)
        return True
    except FloodWait as e:
        print(f"FloodWait in log: {e.value}s")
        await asyncio.sleep(e.value)
        try:
            await client.send_message(LOG_CHANNEL, text)
            return True
        except:
            return False
    except ChatWriteForbidden:
        print(f"Bot can't write to LOG_CHANNEL: {LOG_CHANNEL}")
        return False
    except Exception as e:
        print(f"Log error: {e}")
        return False


def get_media_info(message):
    """Extract media object from message safely"""
    if not message.media:
        return None
    
    try:
        # Get the media type value
        media_type = message.media.value
        media = getattr(message, media_type, None)
        
        if not media:
            return None
        
        # Validate required attributes
        if not hasattr(media, 'file_id') or not media.file_id:
            return None
        
        if not hasattr(media, 'file_name') or not media.file_name:
            return None
        
        return media
    except Exception as e:
        print(f"Media extraction error: {e}")
        return None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    try:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    except:
        return "Unknown"


# ─────────────────────────────────────────────
# 📥 NEW FILE INDEX
# ─────────────────────────────────────────────

@Client.on_message(filters.chat(INDEX_CHANNELS) & media_filter, group=10)
async def index_new_file(bot, message):
    """Index new files from index channels"""
    
    # Extract media safely
    media = get_media_info(message)
    if not media:
        print(f"Invalid media in message {message.id}")
        return
    
    try:
        # Get caption
        caption = message.caption or ""
        
        # Auto detect quality
        quality = detect_quality(media.file_name, caption)
        
        # Get file size
        file_size = getattr(media, 'file_size', 0)
        
        # Save to database
        status = await save_file(media, quality=quality)
        
        # Determine emoji based on status
        emoji_map = {
            "suc": "✅",      # Successfully indexed
            "dup": "♻️",      # Duplicate file
            "err": "❌",      # Error
            "skip": "⏭",     # Skipped
        }
        emoji = emoji_map.get(status, "❓")
        
        # React to message
        await safe_react(message, emoji)
        
        # Prepare log message
        log_text = (
            f"📥 **Index Event**\n\n"
            f"📄 **File:** `{media.file_name}`\n"
            f"🆔 **File ID:** `{media.file_id[:20]}...`\n"
            f"📊 **Size:** `{format_file_size(file_size)}`\n"
            f"🎞 **Quality:** `{quality}`\n"
            f"✅ **Status:** `{status}`\n"
            f"💬 **Chat:** {message.chat.title or 'Unknown'}\n"
            f"🔗 **Message ID:** `{message.id}`"
        )
        
        # Add caption preview if exists
        if caption:
            preview = caption[:100] + "..." if len(caption) > 100 else caption
            log_text += f"\n📝 **Caption:** `{preview}`"
        
        # Send log
        await safe_log(bot, log_text)
        
    except FloodWait as e:
        print(f"FloodWait in index: {e.value}s")
        await asyncio.sleep(e.value)
    except Exception as e:
        print(f"Index error for {media.file_name}: {e}")
        await safe_react(message, "❌")
        await safe_log(
            bot,
            f"❌ **Index Error**\n\n"
            f"📄 File: `{media.file_name}`\n"
            f"⚠️ Error: `{str(e)[:200]}`"
        )


# ─────────────────────────────────────────────
# ✏️ CAPTION EDIT → DB AUTO UPDATE
# ─────────────────────────────────────────────

@Client.on_edited_message(filters.chat(INDEX_CHANNELS) & (filters.video | filters.document), group=11)
async def update_caption(bot, message):
    """Update file caption when edited in index channel"""
    
    # Extract media safely
    media = get_media_info(message)
    if not media:
        print(f"Invalid media in edited message {message.id}")
        return
    
    try:
        # Get new caption
        new_caption = message.caption or ""
        
        # Re-detect quality based on new caption
        quality = detect_quality(media.file_name, new_caption)
        
        # Update in database
        updated = await update_file_caption(
            media.file_id,
            new_caption,
            quality
        )
        
        if not updated:
            print(f"Failed to update caption for {media.file_name}")
            await safe_react(message, "⚠️")
            return
        
        # React to show update success
        await safe_react(message, "✏️")
        
        # Prepare log message
        log_text = (
            f"✏️ **Caption Updated**\n\n"
            f"📄 **File:** `{media.file_name}`\n"
            f"🆔 **File ID:** `{media.file_id[:20]}...`\n"
            f"🎞 **New Quality:** `{quality}`\n"
            f"💬 **Chat:** {message.chat.title or 'Unknown'}\n"
            f"🔗 **Message ID:** `{message.id}`"
        )
        
        # Add caption preview
        if new_caption:
            preview = new_caption[:100] + "..." if len(new_caption) > 100 else new_caption
            log_text += f"\n📝 **New Caption:** `{preview}`"
        else:
            log_text += f"\n📝 **Caption:** Removed"
        
        # Send log
        await safe_log(bot, log_text)
        
    except FloodWait as e:
        print(f"FloodWait in caption update: {e.value}s")
        await asyncio.sleep(e.value)
    except MessageNotModified:
        print(f"Caption not modified for {media.file_name}")
    except Exception as e:
        print(f"Caption update error for {media.file_name}: {e}")
        await safe_react(message, "❌")
        await safe_log(
            bot,
            f"❌ **Caption Update Error**\n\n"
            f"📄 File: `{media.file_name}`\n"
            f"⚠️ Error: `{str(e)[:200]}`"
        )


# ─────────────────────────────────────────────
# 🗑️ FILE DELETE HANDLER (OPTIONAL)
# ─────────────────────────────────────────────

@Client.on_deleted_messages(filters.chat(INDEX_CHANNELS), group=12)
async def handle_deleted_files(bot, messages):
    """Handle deleted messages from index channels"""
    try:
        deleted_count = len(messages)
        
        await safe_log(
            bot,
            f"🗑️ **Files Deleted**\n\n"
            f"📊 Count: `{deleted_count}`\n"
            f"💬 Chat: Index Channel\n"
            f"ℹ️ Note: Files remain in database for search"
        )
    except Exception as e:
        print(f"Delete handler error: {e}")


# ─────────────────────────────────────────────
# 📊 INDEX STATS COMMAND (OPTIONAL)
# ─────────────────────────────────────────────

@Client.on_message(filters.command("indexstats") & filters.private)
async def index_stats(bot, message):
    """Show indexing statistics"""
    try:
        from database.ia_filterdb import get_total_files, get_total_size
        
        # Get stats
        total_files = await get_total_files()
        total_size = await get_total_size()
        
        # Format message
        stats_text = (
            f"📊 **Indexing Statistics**\n\n"
            f"📁 **Total Files:** `{total_files:,}`\n"
            f"💾 **Total Size:** `{format_file_size(total_size)}`\n"
            f"📡 **Index Channels:** `{len(INDEX_CHANNELS)}`"
        )
        
        await message.reply(stats_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────

def validate_config():
    """Validate configuration on startup"""
    errors = []
    
    if not INDEX_CHANNELS:
        errors.append("❌ INDEX_CHANNELS is empty")
    elif not isinstance(INDEX_CHANNELS, (list, tuple)):
        errors.append("❌ INDEX_CHANNELS must be a list")
    
    if LOG_CHANNEL and not isinstance(LOG_CHANNEL, int):
        errors.append("❌ LOG_CHANNEL must be an integer (chat ID)")
    
    if errors:
        print("\n⚠️ Configuration Warnings:")
        for error in errors:
            print(f"  {error}")
        print()
    else:
        print("✅ Index handler configuration valid")

# Run validation on import
validate_config()
