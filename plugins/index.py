import time
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait, MessageNotModified
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS
from database.ia_filterdb import save_file
from utils import get_readable_time

LOCK = asyncio.Lock()
CANCEL = False
INDEX_STATE = {}


# =====================================================
# /index COMMAND
# =====================================================
@Client.on_message(filters.command("index") & filters.private & filters.user(ADMINS))
async def start_index(bot, message):
    uid = message.from_user.id
    if LOCK.locked():
        return await message.reply("⏳ Previous indexing running")

    INDEX_STATE[uid] = {"step": "WAIT_SOURCE"}
    await message.reply(
        "📤 Send **last channel message link**\n"
        "OR **forward last channel message**"
    )


# =====================================================
# STATE HANDLER
# =====================================================
@Client.on_message(filters.private & filters.user(ADMINS))
async def index_flow(bot, message):
    uid = message.from_user.id
    state = INDEX_STATE.get(uid)
    if not state:
        return

    # ---------- STEP 1 ----------
    if state["step"] == "WAIT_SOURCE":
        try:
            if message.text and message.text.startswith("https://t.me"):
                parts = message.text.split("/")
                last_msg_id = int(parts[-1])
                raw = parts[-2]
                chat_id = int("-100" + raw) if raw.isdigit() else raw

            elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
                last_msg_id = message.forward_from_message_id
                chat_id = message.forward_from_chat.id

            else:
                return await message.reply("❌ Invalid link or forward")

            chat = await bot.get_chat(chat_id)
            if chat.type != enums.ChatType.CHANNEL:
                raise Exception("Not a channel")

        except Exception as e:
            INDEX_STATE.pop(uid, None)
            return await message.reply(f"❌ Error: `{e}`")

        INDEX_STATE[uid] = {
            "step": "WAIT_SKIP",
            "chat_id": chat_id,
            "last_msg_id": last_msg_id,
            "title": chat.title
        }

        return await message.reply("⏩ Send skip message number (0 for none)")

    # ---------- STEP 2 ----------
    if state["step"] == "WAIT_SKIP":
        try:
            skip = int(message.text)
        except:
            return await message.reply("❌ Skip must be number")

        chat_id = state["chat_id"]
        last_msg_id = state["last_msg_id"]
        title = state["title"]
        INDEX_STATE.pop(uid, None)

        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ START", callback_data=f"idx#start#{chat_id}#{last_msg_id}#{skip}")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="idx#close")]
        ])

        return await message.reply(
            f"📢 **Channel:** `{title}`\n"
            f"📊 **Last Message ID:** `{last_msg_id}`\n\n"
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
# 🔥 MAIN INDEX WORKER (Hydrogram-safe)
# =====================================================
async def index_worker(bot, status, chat_id, last_msg_id, skip):
    global CANCEL

    start = time.time()
    saved = dup = err = nomedia = 0
    processed = 0

    current_id = last_msg_id - skip

    try:
        while current_id > 0:
            if CANCEL:
                break

            try:
                msg = await bot.get_messages(chat_id, current_id)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            except:
                current_id -= 1
                continue

            processed += 1

            if processed % 30 == 0:
                try:
                    btn = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🛑 STOP", callback_data="idx#cancel")]]
                    )
                    await status.edit(
                        f"📊 Processed: `{processed}`\n"
                        f"✅ Saved: `{saved}` | ♻️ Dup: `{dup}` | ❌ Err: `{err}`",
                        reply_markup=btn
                    )
                except MessageNotModified:
                    pass

            if not msg or not msg.media:
                nomedia += 1
                current_id -= 1
                continue

            if msg.media not in (
                enums.MessageMediaType.VIDEO,
                enums.MessageMediaType.DOCUMENT
            ):
                nomedia += 1
                current_id -= 1
                continue

            media = getattr(msg, msg.media.value, None)
            if not media:
                current_id -= 1
                continue

            media.caption = msg.caption
            res = await save_file(media)

            if res == "suc":
                saved += 1
            elif res == "dup":
                dup += 1
            else:
                err += 1

            current_id -= 1

    except Exception as e:
        return await status.edit(f"❌ Failed: `{e}`")

    time_taken = get_readable_time(time.time() - start)
    await status.edit(
        f"✅ **Index Completed**\n\n"
        f"⏱ Time: `{time_taken}`\n"
        f"📥 Saved: `{saved}`\n"
        f"♻️ Duplicate: `{dup}`\n"
        f"❌ Errors: `{err}`\n"
        f"🚫 Non-media: `{nomedia}`"
    )


# =====================================================
# STOP
# =====================================================
@Client.on_callback_query(filters.regex("^idx#cancel"))
async def stop_index(bot, query):
    global CANCEL
    CANCEL = True
    await query.answer("Stopping...", show_alert=True)
