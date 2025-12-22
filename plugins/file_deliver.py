import asyncio
import time
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import IS_STREAM, PM_FILE_DELETE_TIME, PROTECT_CONTENT, ADMINS
from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import get_settings, get_shortlink, temp


# ======================================================
# 🔐 CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=30)
RESEND_EXPIRE_TIME = 60  # seconds


# ======================================================
# 🧠 RUNTIME DELIVERY STATE
# ======================================================

if not hasattr(temp, "ACTIVE_DELIVERY"):
    temp.ACTIVE_DELIVERY = set()

if not hasattr(temp, "DELIVERY_STATS"):
    temp.DELIVERY_STATS = {
        "total": 0,
        "admin": 0,
        "user": 0,
        "active": 0
    }


# ======================================================
# 🧠 PREMIUM CHECK
# ======================================================

async def has_premium_or_grace(user_id: int) -> bool:
    if user_id in ADMINS:
        return True

    plan = db.get_plan(user_id)
    if not plan or not plan.get("premium"):
        return False

    expire = plan.get("expire")
    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    return bool(expire and datetime.utcnow() <= expire + GRACE_PERIOD)


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

    # ---- FREE USER → SHORTLINK ----
    if settings.get("shortlink") and not await has_premium_or_grace(uid):
        link = await get_shortlink(
            settings.get("url"),
            settings.get("api"),
            f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
        )
        return await query.message.reply_text(
            f"<b>{file['file_name']}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Get File", url=link)],
                [InlineKeyboardButton("❌ Close", callback_data="close_data")]
            ])
        )

    # ---- PREMIUM / ADMIN ----
    await query.answer(
        url=f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
    )


# ======================================================
# 📩 /START FILE DELIVERY (PM)
# ======================================================

@Client.on_message(filters.command("start") & filters.private & filters.regex(r"^/start file_"))
async def start_file_delivery(client: Client, message):
    try:
        _, grp_id, file_id = message.text.split("_", 2)
        grp_id = int(grp_id)
    except:
        return

    uid = message.from_user.id

    # 🔥 USER QUEUE LOCK (ADMIN BYPASS)
    if uid not in ADMINS and uid in temp.ACTIVE_DELIVERY:
        await message.reply("⏳ Please wait, your previous file is processing")
        try:
            await message.delete()
        except:
            pass
        return

    try:
        await deliver_file(client, uid, grp_id, file_id)
    finally:
        try:
            await message.delete()  # 🔥 ALWAYS DELETE /start
        except:
            pass


# ======================================================
# 🚚 CORE DELIVERY ENGINE
# ======================================================

async def deliver_file(client, uid, grp_id, file_id):
    file = await get_file_details(file_id)
    if not file:
        return

    # ---- LOCK (USER ONLY) ----
    is_admin = uid in ADMINS
    if not is_admin:
        temp.ACTIVE_DELIVERY.add(uid)

    temp.DELIVERY_STATS["active"] += 1

    try:
        settings = await get_settings(grp_id)

        if settings.get("shortlink") and not await has_premium_or_grace(uid):
            return

        # ---- CLEAN OLD FILES (SAME USER) ----
        for k, v in list(temp.FILES.items()):
            if v.get("owner") == uid:
                try:
                    await v["file"].delete()
                except:
                    pass
                temp.FILES.pop(k, None)

        # ---- CLEAN CAPTION (NO DUPLICATE) ----
        caption_tpl = settings.get("caption") or "{file_name}\n\n{file_caption}"
        caption = caption_tpl.format(
            file_name=file.get("file_name", "File"),
            file_caption=file.get("caption", "")
        )

        buttons = []
        if IS_STREAM:
            buttons.append([
                InlineKeyboardButton("▶️ Watch / Download", callback_data=f"stream#{file_id}")
            ])
        buttons.append([
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ])

        sent = await client.send_cached_media(
            chat_id=uid,
            file_id=file_id,
            caption=caption,
            protect_content=PROTECT_CONTENT,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        # ---- STATS ----
        temp.DELIVERY_STATS["total"] += 1
        if is_admin:
            temp.DELIVERY_STATS["admin"] += 1
        else:
            temp.DELIVERY_STATS["user"] += 1

        temp.FILES[sent.id] = {
            "owner": uid,
            "file": sent,
            "expire": int(time.time()) + PM_FILE_DELETE_TIME
        }

        # ---- AUTO DELETE (SILENT) ----
        await asyncio.sleep(PM_FILE_DELETE_TIME)

        data = temp.FILES.pop(sent.id, None)
        if data:
            try:
                await sent.delete()
            except:
                pass

        # ---- RESEND BUTTON ----
        resend = await client.send_message(
            uid,
            "⌛ <b>File expired</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Resend File", callback_data=f"resend#{file_id}")]
            ])
        )

        await asyncio.sleep(RESEND_EXPIRE_TIME)
        try:
            await resend.delete()
        except:
            pass

    finally:
        # ---- UNLOCK ----
        if not is_admin:
            temp.ACTIVE_DELIVERY.discard(uid)
        temp.DELIVERY_STATS["active"] -= 1


# ======================================================
# 🔁 RESEND HANDLER
# ======================================================

@Client.on_callback_query(filters.regex(r"^resend#"))
async def resend_handler(client, query: CallbackQuery):
    file_id = query.data.split("#", 1)[1]
    uid = query.from_user.id

    await query.answer()
    try:
        await query.message.delete()
    except:
        pass

    if uid not in ADMINS and uid in temp.ACTIVE_DELIVERY:
        return

    await deliver_file(client, uid, 0, file_id)
