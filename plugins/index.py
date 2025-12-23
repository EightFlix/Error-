import re
import time
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait, MessageNotModified
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, INDEX_EXTENSIONS
from database.ia_filterdb import save_file
from utils import get_readable_time

LOCK = asyncio.Lock()
CANCEL = False


# =====================================================
# /index COMMAND
# =====================================================
@Client.on_message(filters.command("index") & filters.private & filters.user(ADMINS))
async def start_index(bot, message):
    global CANCEL

    if LOCK.locked():
        return await message.reply("⏳ Previous indexing still running")

    ask = await message.reply("📤 Forward **last channel message** or send **last message link**")
    reply = await bot.listen(message.chat.id, message.from_user.id)
    await ask.delete()

    # ---------------------------------------------
    # PARSE INPUT
    # ---------------------------------------------
    try:
        if reply.text and reply.text.startswith("https://t.me"):
            parts = reply.text.split("/")
            last_msg_id = int(parts[-1])
            raw_chat = parts[-2]
            chat_id = int("-100" + raw_chat) if raw_chat.isdigit() else raw_chat

        elif reply.forward_from_chat:
            last_msg_id = reply.forward_from_message_id
            chat_id = reply.forward_from_chat.id

        else:
            return await message.reply("❌ Invalid input")

        chat = await bot.get_chat(chat_id)
        if chat.type != enums.ChatType.CHANNEL:
            return await message.reply("❌ Only channels supported")

    except Exception as e:
        return await message.reply(f"❌ Error: `{e}`")

    # ---------------------------------------------
    # SKIP INPUT
    # ---------------------------------------------
    ask_skip = await message.reply("⏩ Send skip message number (0 for none)")
    skip_msg = await bot.listen(message.chat.id, message.from_user.id)
    await ask_skip.delete()

    try:
        skip = int(skip_msg.text)
    except:
        return await message.reply("❌ Invalid skip number")

    # ---------------------------------------------
    # CONFIRM
    # ---------------------------------------------
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ START", callback_data=f"idx#start#{chat_id}#{last_msg_id}#{skip}")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="idx#close")]
    ])

    await message.reply(
        f"📢 **Channel:** `{chat.title}`\n"
        f"📊 **Total Messages:** `{last_msg_id}`\n\n"
        f"Start indexing?",
        reply_markup=btn
    )


# =====================================================
# CALLBACK
# =====================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def index_callback(bot, query):
    global CANCEL
    data = query.data.split("#")

    if data[1] == "close":
        return await query.message.edit("❌ Cancelled")

    _, _, chat_id, last_id, skip = data
    await query.message.edit("⚡ Indexing started...")

    async with LOCK:
        CANCEL = False
        await index_worker(
            bot,
            query.message,
            int(chat_id),
            int(last_id),
            int(skip)
        )


# =====================================================
# MAIN INDEX WORKER (🔥 PROVEN LOGIC 🔥)
# =====================================================
async def index_worker(bot, status, chat_id, last_msg_id, skip):
    global CANCEL

    start = time.time()
    saved = dup = err = deleted = nomedia = unsupported = 0
    current = skip

    try:
        async for msg in bot.iter_messages(chat_id, last_msg_id, skip):
            if CANCEL:
                break

            current += 1

            if current % 30 == 0:
                try:
                    btn = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🛑 STOP", callback_data="idx#cancel")]]
                    )
                    await status.edit(
                        f"📊 Processed: `{current}`\n"
                        f"✅ Saved: `{saved}` | ♻️ Dup: `{dup}` | ❌ Err: `{err}`",
                        reply_markup=btn
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except MessageNotModified:
                    pass

            if msg.empty:
                deleted += 1
                continue

            if not msg.media:
                nomedia += 1
                continue

            if msg.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT]:
                unsupported += 1
                continue

            media = getattr(msg, msg.media.value, None)
            if not media or not media.file_name:
                unsupported += 1
                continue

            if not media.file_name.lower().endswith(tuple(INDEX_EXTENSIONS)):
                unsupported += 1
                continue

            media.caption = msg.caption
            res = await save_file(media)

            if res == "suc":
                saved += 1
            elif res == "dup":
                dup += 1
            else:
                err += 1

    except Exception as e:
        return await status.edit(f"❌ Failed: `{e}`")

    time_taken = get_readable_time(time.time() - start)
    await status.edit(
        f"✅ **Index Completed**\n\n"
        f"⏱ Time: `{time_taken}`\n"
        f"📥 Saved: `{saved}`\n"
        f"♻️ Duplicate: `{dup}`\n"
        f"❌ Errors: `{err}`\n"
        f"🚫 Non-media: `{nomedia + unsupported}`"
    )


# =====================================================
# STOP BUTTON
# =====================================================
@Client.on_callback_query(filters.regex("^idx#cancel"))
async def stop_index(bot, query):
    global CANCEL
    CANCEL = True
    await query.answer("Stopping...", show_alert=True)
