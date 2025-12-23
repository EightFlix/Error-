import asyncio
from datetime import datetime
from pymongo import MongoClient

from hydrogram import Client, filters
from hydrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from hydrogram.errors import FloodWait, MessageNotModified

from info import ADMINS, DATA_DATABASE_URL, DATABASE_NAME
from database.ia_filterdb import save_file

# =====================================================
# GLOBAL STATE
# =====================================================
INDEXING_STATE = {}
CANCEL_INDEX = {}

# =====================================================
# MONGODB (RESUME SUPPORT)
# =====================================================
mongo = MongoClient(DATA_DATABASE_URL)
db = mongo[DATABASE_NAME]
index_state = db["index_state"]

def get_last_id(channel_id: int):
    d = index_state.find_one({"_id": channel_id})
    return d["last_id"] if d else None

def set_last_id(channel_id: int, msg_id: int):
    index_state.update_one(
        {"_id": channel_id},
        {"$set": {"last_id": msg_id}},
        upsert=True
    )

# =====================================================
# MULTI-CHANNEL PARALLEL LIMIT
# =====================================================
CHANNEL_SEMAPHORE = asyncio.Semaphore(3)  # change as per server

# =====================================================
# /index COMMAND
# =====================================================
@Client.on_message(filters.command("index") & filters.private)
async def index_cmd(bot: Client, msg: Message):
    if msg.from_user.id not in ADMINS:
        return await msg.reply("❌ Admin only")

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 Channel Link / Post Link", callback_data="idx#link")],
        [InlineKeyboardButton("📨 Forward Message", callback_data="idx#forward")],
        [InlineKeyboardButton("❌ Cancel", callback_data="idx#cancel")]
    ])

    await msg.reply(
        "🔥 **Manual Indexing**\n\n"
        "• Channel link\n"
        "• Channel post link (`/c/xxxx/123`)\n"
        "• Forwarded message\n\n"
        "⏱ Timeout: 60 sec",
        reply_markup=btn
    )

    INDEXING_STATE[msg.from_user.id] = {
        "active": True,
        "method": None,
        "time": datetime.utcnow()
    }

    asyncio.create_task(auto_timeout(msg.from_user.id))

# =====================================================
# AUTO TIMEOUT
# =====================================================
async def auto_timeout(uid):
    await asyncio.sleep(60)
    INDEXING_STATE.pop(uid, None)

# =====================================================
# CALLBACK HANDLER
# =====================================================
@Client.on_callback_query(filters.regex("^idx#"))
async def idx_callback(bot: Client, q: CallbackQuery):
    uid = q.from_user.id
    if uid not in ADMINS:
        return await q.answer("Admin only", show_alert=True)

    data = q.data.split("#")[1]

    if data == "cancel":
        INDEXING_STATE.pop(uid, None)
        return await q.message.edit("❌ Cancelled")

    INDEXING_STATE[uid]["method"] = data
    text = "Send channel link or post link" if data == "link" else "Forward channel message"
    await q.message.edit(f"📥 **{text}**")

    await q.answer()

# =====================================================
# LINK HANDLER
# =====================================================
@Client.on_message(filters.private & filters.text)
async def handle_link(bot: Client, msg: Message):
    uid = msg.from_user.id
    st = INDEXING_STATE.get(uid)

    if not st or st.get("method") != "link":
        return

    text = msg.text.strip()
    start_from = None

    try:
        if "/c/" in text:
            raw = text.split("/c/")[1].split("/")
            channel_id = int("-100" + raw[0])
            if len(raw) > 1:
                start_from = int(raw[1])
        else:
            username = text.split("t.me/")[1].split("/")[0]
            chat = await bot.get_chat(username)
            channel_id = chat.id

        chat = await bot.get_chat(channel_id)
        title = chat.title or "Unknown"

    except Exception as e:
        return await msg.reply(f"❌ `{e}`")

    INDEXING_STATE.pop(uid, None)
    CANCEL_INDEX[channel_id] = False

    status = await msg.reply(f"⚡ Starting index\n📢 `{title}`")

    asyncio.create_task(
        run_parallel_index(
            bot,
            status,
            channel_id,
            title,
            start_from
        )
    )

# =====================================================
# FORWARD HANDLER
# =====================================================
@Client.on_message(filters.private & filters.forwarded)
async def handle_forward(bot: Client, msg: Message):
    uid = msg.from_user.id
    st = INDEXING_STATE.get(uid)

    if not st or st.get("method") != "forward":
        return

    if not msg.forward_from_chat:
        return await msg.reply("❌ Forward from channel only")

    channel = msg.forward_from_chat
    INDEXING_STATE.pop(uid, None)
    CANCEL_INDEX[channel.id] = False

    status = await msg.reply(f"⚡ Starting index\n📢 `{channel.title}`")

    asyncio.create_task(
        run_parallel_index(
            bot,
            status,
            channel.id,
            channel.title,
            None
        )
    )

# =====================================================
# PARALLEL CHANNEL RUNNER
# =====================================================
async def run_parallel_index(bot, status, channel_id, title, start_from):
    async with CHANNEL_SEMAPHORE:
        await channel_indexer(bot, status, channel_id, title, start_from)

# =====================================================
# MAIN INDEXER
# =====================================================
async def channel_indexer(bot, status, channel_id, title, start_from):
    indexed = dup = err = skip = 0
    buffer = []
    batch_size = 20
    last_saved = None

    if start_from is None:
        start_from = get_last_id(channel_id)

    stop_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Stop", callback_data=f"stopidx#{channel_id}")]
    ])

    try:
        async for msg in bot.get_chat_history(
            channel_id,
            offset_id=start_from - 1 if start_from else 0
        ):
            if CANCEL_INDEX.get(channel_id):
                break

            if not msg.media:
                skip += 1
                continue

            media = msg.document or msg.video or msg.audio
            if not media:
                skip += 1
                continue

            buffer.append((media, msg.id))

            if len(buffer) >= batch_size:
                res = await process_batch(buffer)
                buffer.clear()

                for r, mid in res:
                    if r == "suc":
                        indexed += 1
                        last_saved = mid
                    elif r == "dup":
                        dup += 1
                    else:
                        err += 1

                if last_saved:
                    set_last_id(channel_id, last_saved)

                await safe_edit(status, title, indexed, dup, err, skip, stop_btn)

        if buffer:
            res = await process_batch(buffer)
            for r, mid in res:
                if r == "suc":
                    indexed += 1
                    last_saved = mid
                elif r == "dup":
                    dup += 1
                else:
                    err += 1

            if last_saved:
                set_last_id(channel_id, last_saved)

        if CANCEL_INDEX.get(channel_id):
            return await status.edit(
                f"🛑 Stopped\n📢 `{title}`\n"
                f"✅ {indexed} ⏭ {dup} ❌ {err}"
            )

        await status.edit(
            f"✅ Completed\n\n"
            f"📢 `{title}`\n"
            f"✅ {indexed}\n"
            f"⏭ {dup}\n"
            f"❌ {err}\n"
            f"⏩ {skip}"
        )

    except Exception as e:
        await status.edit(f"❌ Failed:\n`{str(e)[:200]}`")

# =====================================================
# BATCH PROCESSING
# =====================================================
async def process_batch(batch):
    tasks = [save_wrap(m, i) for m, i in batch]
    return await asyncio.gather(*tasks)

async def save_wrap(media, mid):
    try:
        r = await save_file(media)
        return r, mid
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return "err", mid
    except:
        return "err", mid

# =====================================================
# SAFE EDIT
# =====================================================
async def safe_edit(msg, title, i, d, e, s, btn):
    try:
        await msg.edit(
            f"⚡ `{title}`\n"
            f"✅ {i} ⏭ {d} ❌ {e} ⏩ {s}",
            reply_markup=btn
        )
    except MessageNotModified:
        pass

# =====================================================
# STOP CALLBACK
# =====================================================
@Client.on_callback_query(filters.regex("^stopidx#"))
async def stop_idx(bot: Client, q: CallbackQuery):
    if q.from_user.id not in ADMINS:
        return
    cid = int(q.data.split("#")[1])
    CANCEL_INDEX[cid] = True
    await q.answer("Stopping...", show_alert=True)
