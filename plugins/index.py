import time
import asyncio
import logging
from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait, MessageNotModified
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, INDEX_LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import temp, get_readable_time

logger = logging.getLogger(__name__)

lock = asyncio.Lock()

# ======================================================
# 🛡️ SAFE MESSAGE EDIT (NO MESSAGE_NOT_MODIFIED)
# ======================================================
async def safe_edit(msg, text, **kwargs):
    try:
        if msg.text != text:
            await msg.edit_text(text, **kwargs)
    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.warning(f"Safe edit failed: {e}")

# ======================================================
# 🔁 CUSTOM ITERATOR (ANTI FLOOD SAFE)
# ======================================================
async def iter_messages(bot, chat_id, last_msg_id, skip):
    current = skip
    while current < last_msg_id:
        end = min(current + 200, last_msg_id)
        ids = list(range(current + 1, end + 1))

        try:
            messages = await bot.get_messages(chat_id, ids)
            for msg in messages:
                if msg:
                    yield msg
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Fetch error {current}-{end}: {e}")

        current = end
        await asyncio.sleep(0.4)

# ======================================================
# 🚀 /index COMMAND
# ======================================================
@Client.on_message(filters.command("index") & filters.private & filters.user(ADMINS))
async def index_start(_, message):
    if lock.locked():
        return await message.reply("⚠️ Index already running.")

    await message.reply(
        "📌 Send **channel post link** OR **forward last channel message**"
    )

# ======================================================
# 📥 SOURCE HANDLER
# ======================================================
@Client.on_message(filters.private & filters.incoming & filters.user(ADMINS))
async def receive_source(bot, message):
    if lock.locked():
        return

    chat_id = last_msg_id = None

    # ---- LINK ----
    if message.text and message.text.startswith("https://t.me"):
        try:
            parts = message.text.rstrip("/").split("/")
            last_msg_id = int(parts[-1])
            cid = parts[-2]
            chat_id = int("-100" + cid) if cid.isnumeric() else cid
        except:
            return await message.reply("❌ Invalid message link.")

    # ---- FORWARD ----
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id
    else:
        return

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"❌ Cannot access channel:\n`{e}`")

    ask = await message.reply("🔢 Send **skip count** (0 recommended)")
    try:
        r = await bot.listen(message.chat.id, timeout=30)
        skip = int(r.text)
    except:
        return await safe_edit(ask, "❌ Invalid skip value.")

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 START INDEXING", callback_data=f"idx#start#{chat_id}#{last_msg_id}#{skip}")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="idx#cancel")]
    ])

    await message.reply(
        f"📢 **Channel:** {chat.title}\n"
        f"📦 **Last Msg ID:** `{last_msg_id}`\n"
        f"⏭️ **Skip:** `{skip}`",
        reply_markup=btn
    )

# ======================================================
# 🎛 CALLBACK HANDLER
# ======================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def index_callback(bot, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("Access denied", show_alert=True)

    data = query.data.split("#")

    if data[1] == "cancel":
        temp.CANCEL = True
        return await safe_edit(query.message, "⛔ Stopping indexing...")

    if data[1] == "start":
        await safe_edit(query.message, "🚀 Indexing started...")
        await run_indexing(
            bot,
            query.message,
            int(data[2]),
            int(data[3]),
            int(data[4])
        )

# ======================================================
# ⚙️ CORE INDEX ENGINE (FIXED)
# ======================================================
async def run_indexing(bot, msg, chat_id, last_msg_id, skip):
    start = time.time()
    scanned = saved = dup = err = 0

    async with lock:
        try:
            async for message in iter_messages(bot, chat_id, last_msg_id, skip):
                if temp.CANCEL:
                    temp.CANCEL = False
                    break

                scanned += 1

                if not message.media:
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    continue

                media.caption = message.caption
                status = await save_file(media)

                if status == "suc":
                    saved += 1
                elif status == "dup":
                    dup += 1
                else:
                    err += 1

                if scanned % 200 == 0:
                    await safe_edit(
                        msg,
                        f"📦 **Indexing in Progress**\n\n"
                        f"📂 Scanned: `{scanned}`\n"
                        f"⚡ Saved: `{saved}`\n"
                        f"♻️ Dupes: `{dup}`\n"
                        f"❌ Errors: `{err}`\n"
                        f"⏱️ Time: `{get_readable_time(time.time()-start)}`",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("⛔ STOP", callback_data="idx#cancel")]
                        ])
                    )

        finally:
            await safe_edit(
                msg,
                f"✅ **Indexing Completed**\n\n"
                f"📂 Scanned: `{scanned}`\n"
                f"⚡ Saved: `{saved}`\n"
                f"♻️ Dupes: `{dup}`\n"
                f"❌ Errors: `{err}`\n"
                f"⏱️ Time: `{get_readable_time(time.time()-start)}`"
            )

            try:
                await bot.send_message(
                    INDEX_LOG_CHANNEL,
                    f"📊 **Index Summary**\n"
                    f"📢 Channel: `{chat_id}`\n"
                    f"📂 Scanned: `{scanned}`\n"
                    f"⚡ Saved: `{saved}`\n"
                    f"♻️ Dupes: `{dup}`\n"
                    f"❌ Errors: `{err}`"
                )
            except:
                pass
