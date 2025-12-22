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
# ❌ filters.edited REMOVED (Hydrogram compatible)
# ─────────────────────────────────────────────
media_filter = (filters.video | filters.document)

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

async def safe_react(message, emoji: str):
    try:
        await message.react(emoji)
        return True
    except ReactionInvalid:
        return False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await message.react(emoji)
            return True
        except:
            return False
    except Exception:
        return False


async def safe_log(client, text: str):
    if not LOG_CHANNEL:
        return False

    try:
        await client.send_message(LOG_CHANNEL, text)
        return True
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await client.send_message(LOG_CHANNEL, text)
            return True
        except:
            return False
    except ChatWriteForbidden:
        return False
    except Exception:
        return False


def get_media_info(message):
    if not message.media:
        return None
    try:
        media_type = message.media.value
        media = getattr(message, media_type, None)
        if not media or not getattr(media, "file_id", None):
            return None
        return media
    except:
        return None


def format_file_size(size_bytes: int) -> str:
    try:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KB"
        if size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MB"
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    except:
        return "Unknown"

# ─────────────────────────────────────────────
# 📥 NEW FILE INDEX
# ─────────────────────────────────────────────

@Client.on_message(filters.chat(INDEX_CHANNELS) & media_filter, group=10)
async def index_new_file(bot, message):
    media = get_media_info(message)
    if not media:
        return

    try:
        caption = message.caption or ""
        quality = detect_quality(media.file_name, caption)
        file_size = getattr(media, "file_size", 0)

        status = await save_file(media, quality=quality)

        emoji_map = {
            "suc": "✅",
            "dup": "♻️",
            "err": "❌",
            "skip": "⏭",
        }

        await safe_react(message, emoji_map.get(status, "❓"))

        log_text = (
            f"📥 **Index Event**\n\n"
            f"📄 **File:** `{media.file_name}`\n"
            f"📊 **Size:** `{format_file_size(file_size)}`\n"
            f"🎞 **Quality:** `{quality}`\n"
            f"✅ **Status:** `{status}`\n"
            f"💬 **Chat:** {message.chat.title or 'Unknown'}\n"
            f"🔗 **Message ID:** `{message.id}`"
        )

        if caption:
            log_text += f"\n📝 **Caption:** `{caption[:100]}`"

        await safe_log(bot, log_text)

    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        await safe_react(message, "❌")

# ─────────────────────────────────────────────
# ✏️ CAPTION EDIT → DB UPDATE
# ─────────────────────────────────────────────

@Client.on_edited_message(filters.chat(INDEX_CHANNELS) & (filters.video | filters.document), group=11)
async def update_caption(bot, message):
    media = get_media_info(message)
    if not media:
        return

    try:
        new_caption = message.caption or ""
        quality = detect_quality(media.file_name, new_caption)

        updated = await update_file_caption(
            media.file_id,
            new_caption,
            quality
        )

        if not updated:
            await safe_react(message, "⚠️")
            return

        await safe_react(message, "✏️")

        log_text = (
            f"✏️ **Caption Updated**\n\n"
            f"📄 **File:** `{media.file_name}`\n"
            f"🎞 **Quality:** `{quality}`\n"
            f"💬 **Chat:** {message.chat.title or 'Unknown'}\n"
            f"🔗 **Message ID:** `{message.id}`"
        )

        if new_caption:
            log_text += f"\n📝 **New Caption:** `{new_caption[:100]}`"
        else:
            log_text += "\n📝 **Caption:** Removed"

        await safe_log(bot, log_text)

    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        await safe_react(message, "❌")

# ─────────────────────────────────────────────
# 🗑️ DELETE HANDLER
# ─────────────────────────────────────────────

@Client.on_deleted_messages(filters.chat(INDEX_CHANNELS), group=12)
async def handle_deleted_files(bot, messages):
    try:
        await safe_log(
            bot,
            f"🗑️ **Files Deleted**\n\n"
            f"📊 Count: `{len(messages)}`\n"
            f"ℹ️ Files remain searchable"
        )
    except:
        pass

# ─────────────────────────────────────────────
# CONFIG VALIDATION
# ─────────────────────────────────────────────

def validate_config():
    if not INDEX_CHANNELS:
        print("⚠️ INDEX_CHANNELS empty")
    else:
        print("✅ Index handler config OK")

validate_config()
