from hydrogram import Client, filters, enums
from info import INDEX_CHANNELS, LOG_CHANNEL
from database.ia_filterdb import (
    save_file,
    update_file_caption,
    detect_quality
)

# ─────────────────────────────────────────────
# MEDIA FILTER (VIDEO + DOCUMENT ONLY)
# ─────────────────────────────────────────────
media_filter = filters.video | filters.document


# ─────────────────────────────────────────────
# 📥 NEW FILE INDEX
# ─────────────────────────────────────────────
@Client.on_message(filters.chat(INDEX_CHANNELS) & media_filter)
async def index_new_file(bot, message):
    media = getattr(message, message.media.value, None)
    if not media or not media.file_name:
        return

    media.caption = message.caption or ""

    # 🧠 auto quality detect
    quality = detect_quality(media.file_name, media.caption)

    status = await save_file(media, quality=quality)

    # ───── Emoji feedback in channel ─────
    if status == "suc":
        emoji = "✅"        # indexed
    elif status == "dup":
        emoji = "♻️"        # duplicate
    else:
        emoji = "❌"

    try:
        await message.react(emoji)
    except:
        pass

    # ───── LOG ─────
    if LOG_CHANNEL:
        await bot.send_message(
            LOG_CHANNEL,
            f"📥 **Index Event**\n"
            f"📄 `{media.file_name}`\n"
            f"🎞 Quality: `{quality}`\n"
            f"📊 Status: `{status}`"
        )


# ─────────────────────────────────────────────
# ✏️ CAPTION EDIT → DB AUTO UPDATE
# ─────────────────────────────────────────────
@Client.on_edited_message(filters.chat(INDEX_CHANNELS) & media_filter)
async def update_caption(bot, message):
    media = getattr(message, message.media.value, None)
    if not media or not media.file_name:
        return

    new_caption = message.caption or ""

    # 🧠 re-detect quality on caption edit
    quality = detect_quality(media.file_name, new_caption)

    updated = await update_file_caption(
        media.file_id,
        new_caption,
        quality
    )

    if not updated:
        return

    # ───── Emoji feedback ─────
    try:
        await message.react("✏️")   # caption updated
    except:
        pass

    # ───── LOG ─────
    if LOG_CHANNEL:
        await bot.send_message(
            LOG_CHANNEL,
            f"✏️ **Caption Updated**\n"
            f"📄 `{media.file_name}`\n"
            f"🎞 New Quality: `{quality}`"
        )
