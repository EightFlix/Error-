import asyncio
import time
import logging
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import IS_STREAM, PM_FILE_DELETE_TIME, PROTECT_CONTENT, ADMINS
from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import get_settings, get_size, get_shortlink, temp


# ======================================================
# LOGGING
# ======================================================

logger = logging.getLogger(__name__)


# ======================================================
# CONFIG
# ======================================================

GRACE_PERIOD = timedelta(minutes=30)
RESEND_EXPIRE_TIME = 60  # seconds


# ======================================================
# PREMIUM CHECK
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
# FILE BUTTON (GROUP)
# ======================================================

@Client.on_callback_query(filters.regex(r"^file#"))
async def file_button_handler(client: Client, query: CallbackQuery):
    _, file_id = query.data.split("#", 1)

    logger.info(
        f"[FILE_CLICK] uid={query.from_user.id} "
        f"group={query.message.chat.id} file={file_id}"
    )

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
            f"<b>📁 {file['file_name']}</b>\n"
            f"📦 <b>Size:</b> {get_size(file['file_size'])}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Get File", url=link)],
                [InlineKeyboardButton("❌ Close", callback_data="close_data")]
            ])
        )

    # ---- PREMIUM → PM ----
    await query.answer(
        url=f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
    )


# ======================================================
# /START FILE DELIVERY (PM)
# ======================================================

@Client.on_message(
    filters.private &
    filters.command("start") &
    filters.regex(r"file_")
)
async def start_file_delivery(client: Client, message):
    logger.info(
        f"[START_PM] uid={message.from_user.id} text={message.text}"
    )

    try:
        _, grp_id, file_id = message.text.split("_", 2)
        grp_id = int(grp_id)
    except Exception as e:
        logger.error(f"[START_PARSE_ERROR] {e}")
        return

    await deliver_file(client, message.from_user.id, grp_id, file_id)

    # 🔥 ALWAYS DELETE /start
    try:
        await message.delete()
        logger.info(f"[START_DELETED] uid={message.from_user.id}")
    except Exception as e:
        logger.warning(f"[START_DELETE_FAIL] {e}")


# ======================================================
# CORE DELIVERY (INDEPENDENT SESSION)
# ======================================================

async def deliver_file(client, uid, grp_id, file_id):
    logger.info(
        f"[DELIVER_START] uid={uid} grp={grp_id} file={file_id}"
    )

    file = await get_file_details(file_id)
    if not file:
        logger.error(f"[DELIVER_FAIL] file not found {file_id}")
        return

    settings = await get_settings(grp_id)

    if settings.get("shortlink") and not await has_premium_or_grace(uid):
        logger.info(f"[DELIVER_BLOCKED] uid={uid} shortlink enabled")
        return

    # ==================================================
    # CLEAN CAPTION (NO DUPLICATE EVER)
    # ==================================================
    file_name = (file.get("file_name") or "").strip()
    file_caption = (file.get("caption") or "").strip()

    if not file_caption or file_caption == file_name:
        caption = file_name
    else:
        caption = f"{file_name}\n\n{file_caption}"

    # ==================================================
    # BUTTONS
    # ==================================================
    buttons = []
    if IS_STREAM:
        buttons.append([
            InlineKeyboardButton(
                "▶️ Watch / Download",
                callback_data=f"stream#{file_id}"
            )
        ])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])

    markup = InlineKeyboardMarkup(buttons)

    sent = await client.send_cached_media(
        chat_id=uid,
        file_id=file_id,
        caption=caption,
        protect_content=PROTECT_CONTENT,
        reply_markup=markup
    )

    logger.info(
        f"[FILE_SENT] uid={uid} msg_id={sent.id} file={file_id}"
    )

    # ==================================================
    # TRACK FILE (NO INTERFERENCE WITH OTHER FILES)
    # ==================================================
    temp.FILES[sent.id] = {
        "owner": uid,
        "file_id": file_id,
        "expire": int(time.time()) + PM_FILE_DELETE_TIME
    }

    # ==================================================
    # AUTO DELETE (ONLY THIS FILE)
    # ==================================================
    await asyncio.sleep(PM_FILE_DELETE_TIME)

    data = temp.FILES.pop(sent.id, None)
    if not data:
        logger.info(f"[AUTO_DELETE_SKIP] msg_id={sent.id}")
        return

    try:
        await sent.delete()
        logger.info(
            f"[AUTO_DELETE] uid={uid} msg_id={sent.id}"
        )
    except Exception as e:
        logger.warning(f"[AUTO_DELETE_FAIL] {e}")

    # ==================================================
    # RESEND MESSAGE (TEMP)
    # ==================================================
    resend = await client.send_message(
        uid,
        "⌛ <b>File expired</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔁 Resend File",
                callback_data=f"resend#{file_id}"
            )]
        ])
    )

    await asyncio.sleep(RESEND_EXPIRE_TIME)
    try:
        await resend.delete()
    except:
        pass


# ======================================================
# RESEND HANDLER
# ======================================================

@Client.on_callback_query(filters.regex(r"^resend#"))
async def resend_handler(client, query: CallbackQuery):
    file_id = query.data.split("#", 1)[1]
    uid = query.from_user.id

    logger.info(
        f"[RESEND_CLICK] uid={uid} file={file_id}"
    )

    await query.answer()
    try:
        await query.message.delete()
    except:
        pass

    await deliver_file(client, uid, 0, file_id)
