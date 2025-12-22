import asyncio
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from hydrogram.errors import MessageNotModified

from info import IS_STREAM, PM_FILE_DELETE_TIME, PROTECT_CONTENT, ADMINS
from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import get_settings, get_size, get_shortlink, get_readable_time, temp


# ======================================================
# 🔐 CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=30)
RESEND_EXPIRE_TIME = 60  # seconds

if not hasattr(temp, "FILES"):
    temp.FILES = {}


# ======================================================
# 🧠 PREMIUM CHECK (WITH GRACE)
# ======================================================

async def has_premium_or_grace(user_id: int) -> bool:
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
# ⏱ COUNTDOWN TASK (CAPTION BASED)
# ======================================================

async def countdown_task(msg_id: int, seconds: int):
    try:
        while seconds > 0:
            await asyncio.sleep(60)
            seconds -= 60

            data = temp.FILES.get(msg_id)
            if not data:
                return

            try:
                await data["file"].edit_caption(
                    data["base_caption"]
                    + f"\n\n⚠️ <i>Auto delete in {get_readable_time(seconds)}</i>",
                    reply_markup=data["markup"]
                )
            except MessageNotModified:
                pass
            except:
                return
    except asyncio.CancelledError:
        return


# ======================================================
# 📦 FILE BUTTON (GROUP)
# ======================================================

@Client.on_callback_query(filters.regex(r"^file#"))
async def file_button_handler(client: Client, query: CallbackQuery):
    _, file_id = query.data.split("#", 1)

    file = await get_file_details(file_id)
    if not file:
        return await query.answer("❌ File not found", show_alert=True)

    settings = await get_settings(query.message.chat.id)
    uid = query.from_user.id
    premium_ok = await has_premium_or_grace(uid)

    if settings.get("shortlink") and not premium_ok:
        link = await get_shortlink(
            settings.get("url"),
            settings.get("api"),
            f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
        )
        return await query.message.reply_text(
            f"<b>📁 {file['file_name']}</b>\n"
            f"📦 <b>Size:</b> {get_size(file['file_size'])}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Get File", url=link)],
                [InlineKeyboardButton("❌ Close", callback_data="close_data")]
            ])
        )

    await query.answer(
        url=f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
    )


# ======================================================
# 📩 /START FILE DELIVERY (PM)
# ======================================================

@Client.on_message(filters.command("start") & filters.private & filters.regex(r"^/start file_"))
async def start_file_delivery(client: Client, message):
    data = message.text.split(maxsplit=1)[1]

    try:
        _, grp_id, file_id = data.split("_", 2)
        grp_id = int(grp_id)
    except:
        return await message.reply("❌ Invalid file link")

    file = await get_file_details(file_id)
    if not file:
        return await message.reply("❌ File not found")

    settings = await get_settings(grp_id)
    uid = message.from_user.id

    if settings.get("shortlink") and not await has_premium_or_grace(uid):
        return await message.reply("🔒 Premium required")

    # 🔥 clean previous file of same user
    for k, v in list(temp.FILES.items()):
        if v["owner"] == uid:
            try:
                v["task"].cancel()
            except:
                pass
            try:
                await v["file"].delete()
            except:
                pass
            temp.FILES.pop(k, None)

    caption_tpl = settings.get("caption") or "{file_name}\n\n{file_caption}"
    base_caption = caption_tpl.format(
        file_name=file["file_name"],
        file_caption=file.get("caption", "")
    )

    buttons = []
    if IS_STREAM:
        buttons.append([
            InlineKeyboardButton("▶️ Watch / Download", callback_data=f"stream#{file_id}")
        ])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])

    markup = InlineKeyboardMarkup(buttons)

    sent = await client.send_cached_media(
        chat_id=uid,
        file_id=file_id,
        caption=base_caption
        + f"\n\n⚠️ <i>Auto delete in {get_readable_time(PM_FILE_DELETE_TIME)}</i>",
        protect_content=PROTECT_CONTENT,
        reply_markup=markup
    )

    await message.delete()

    task = asyncio.create_task(countdown_task(sent.id, PM_FILE_DELETE_TIME))

    temp.FILES[sent.id] = {
        "owner": uid,
        "file_id": file_id,
        "file": sent,
        "task": task,
        "base_caption": base_caption,
        "markup": markup
    }

    # ================= FINAL DELETE =================
    await asyncio.sleep(PM_FILE_DELETE_TIME)

    data = temp.FILES.pop(sent.id, None)
    if not data:
        return

    try:
        await data["file"].delete()
    except:
        pass

    # 🔁 Resend button (valid 60s)
    resend_msg = await client.send_message(
        uid,
        "⌛ <b>File expired</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Resend File", callback_data=f"resend#{file_id}")]
        ])
    )

    await asyncio.sleep(RESEND_EXPIRE_TIME)
    try:
        await resend_msg.delete()
    except:
        pass


# ======================================================
# 🔁 RESEND HANDLER (NO /START)
# ======================================================

@Client.on_callback_query(filters.regex(r"^resend#"))
async def resend_handler(client, query: CallbackQuery):
    file_id = query.data.split("#", 1)[1]
    uid = query.from_user.id

    file = await get_file_details(file_id)
    if not file:
        return await query.answer("Expired", show_alert=True)

    await query.message.delete()
    await start_file_delivery(
        client,
        query.message.reply_to_message or query.message
    )
