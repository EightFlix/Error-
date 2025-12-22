import asyncio
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from hydrogram.errors import MessageNotModified

from info import (
    IS_STREAM,
    PM_FILE_DELETE_TIME,
    PROTECT_CONTENT,
    ADMINS
)

from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import (
    get_settings,
    get_size,
    get_shortlink,
    get_readable_time,
    temp
)

# ======================================================
# 🔐 CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=30)

# temp memory init
if not hasattr(temp, "FILES"):
    temp.FILES = {}

# ======================================================
# 🧠 PREMIUM CHECK (SAFE)
# ======================================================

async def has_premium_or_grace(user_id, bot):
    if user_id in ADMINS:
        return True

    plan = db.get_plan(user_id)
    if not plan or not plan.get("premium"):
        return False

    expire = plan.get("expire")
    if not expire:
        return False

    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    now = datetime.utcnow()
    return now <= expire or now <= expire + GRACE_PERIOD


# ======================================================
# ⏱️ COUNTDOWN TASK
# ======================================================

async def countdown_task(user_id, seconds):
    try:
        while seconds > 0:
            await asyncio.sleep(60)
            seconds -= 60

            data = temp.FILES.get(user_id)
            if not data:
                return

            notice = data["notice"]
            try:
                await notice.edit(
                    f"⚠️ File will be deleted in {get_readable_time(seconds)}"
                )
            except MessageNotModified:
                pass
            except:
                return
    except asyncio.CancelledError:
        return


# ======================================================
# 📦 FILE DELIVERY (GROUP BUTTON)
# ======================================================

@Client.on_callback_query(filters.regex(r"^file#"))
async def file_delivery_handler(client: Client, query: CallbackQuery):
    _, file_id = query.data.split("#", 1)

    file = await get_file_details(file_id)
    if not file:
        return await query.answer("❌ File not found", show_alert=True)

    settings = await get_settings(query.message.chat.id)
    uid = query.from_user.id

    premium_ok = await has_premium_or_grace(uid, client)

    if settings.get("shortlink") and not premium_ok:
        link = await get_shortlink(
            settings.get("url"),
            settings.get("api"),
            f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
        )

        return await query.message.reply_text(
            f"<b>📁 File:</b> {file.get('file_name')}\n"
            f"<b>📦 Size:</b> {get_size(file.get('file_size', 0))}\n\n"
            "🔓 Unlock below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Get File", url=link)],
                [InlineKeyboardButton("⚡ Upgrade Premium", callback_data="buy_premium")],
                [InlineKeyboardButton("❌ Close", callback_data="close_data")]
            ])
        )

    await query.answer(
        url=f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
    )


# ======================================================
# 📩 START HANDLER (PM DELIVERY)
# ======================================================

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) < 2:
        return

    data = message.command[1]
    if not data.startswith("file_"):
        return

    try:
        _, grp_id, file_id = data.split("_", 2)
        grp_id = int(grp_id)
    except:
        return await message.reply("❌ Invalid link")

    file = await get_file_details(file_id)
    if not file:
        return await message.reply("❌ File not found")

    settings = await get_settings(grp_id)
    uid = message.from_user.id

    premium_ok = await has_premium_or_grace(uid, client)

    if settings.get("shortlink") and not premium_ok:
        return await message.reply(
            "🔒 Your premium has expired.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Renew Premium", callback_data="buy_premium")]
            ])
        )

    caption_tpl = settings.get("caption") or "{file_name}\n\n{file_caption}"
    caption = caption_tpl.format(
        file_name=file.get("file_name", "File"),
        file_size=get_size(file.get("file_size", 0)),
        file_caption=file.get("caption", "")
    )

    buttons = []
    if IS_STREAM:
        buttons.append([
            InlineKeyboardButton("▶️ Watch / Download", callback_data=f"stream#{file_id}")
        ])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])

    sent = await client.send_cached_media(
        chat_id=uid,
        file_id=file_id,
        caption=caption,
        protect_content=PROTECT_CONTENT,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    notice = await sent.reply(
        f"⚠️ File will be deleted in {get_readable_time(PM_FILE_DELETE_TIME)}"
    )

    # delete /start message
    try:
        await message.delete()
    except:
        pass

    task = asyncio.create_task(countdown_task(uid, PM_FILE_DELETE_TIME))

    temp.FILES[uid] = {
        "file": sent,
        "notice": notice,
        "task": task
    }

    await asyncio.sleep(PM_FILE_DELETE_TIME)

    data = temp.FILES.pop(uid, None)
    if not data:
        return

    try:
        await data["file"].delete()
    except:
        pass

    try:
        await data["notice"].edit(
            "⌛ Time expired. File deleted.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Get Again", callback_data=f"file#{file_id}")]
            ])
        )
    except:
        pass
