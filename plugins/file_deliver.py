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

# Track active deletion tasks
active_tasks = {}


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
    try:
        _, grp_id, file_id = message.text.split("_", 2)
        grp_id = int(grp_id)
    except Exception as e:
        return

    # Cancel previous file task for this user (optional - limits to 1 file at a time)
    user_task_key = f"user_{message.from_user.id}"
    if user_task_key in active_tasks:
        active_tasks[user_task_key].cancel()

    # Create new task and track it
    task = asyncio.create_task(
        deliver_file(client, message.from_user.id, grp_id, file_id)
    )
    active_tasks[user_task_key] = task

    # Clean up task reference when done
    def cleanup_task(t):
        active_tasks.pop(user_task_key, None)
    
    task.add_done_callback(cleanup_task)

    # 🔥 ALWAYS DELETE /start
    try:
        await message.delete()
    except Exception as e:
        pass


# ======================================================
# AUTO DELETE TASK (SEPARATE FROM DELIVERY)
# ======================================================

async def schedule_file_deletion(client, sent_msg, uid, file_id):
    """Separate task for file deletion"""
    msg_id = sent_msg.id
    
    # Track in temp storage
    temp.FILES[msg_id] = {
        "owner": uid,
        "file_id": file_id,
        "expire": int(time.time()) + PM_FILE_DELETE_TIME
    }
    
    try:
        # Wait for expiry
        await asyncio.sleep(PM_FILE_DELETE_TIME)
        
        # Remove from tracking
        data = temp.FILES.pop(msg_id, None)
        if not data:
            return
        
        # Delete the file message
        try:
            await sent_msg.delete()
        except Exception as e:
            pass
        
        # Send resend button
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
        
        # Auto-delete resend button after timeout
        await asyncio.sleep(RESEND_EXPIRE_TIME)
        try:
            await resend.delete()
        except Exception as e:
            pass
            
    except asyncio.CancelledError:
        # Task was cancelled, clean up
        temp.FILES.pop(msg_id, None)
        raise


# ======================================================
# CORE DELIVERY (NON-BLOCKING)
# ======================================================

async def deliver_file(client, uid, grp_id, file_id):
    try:
        file = await get_file_details(file_id)
        if not file:
            return

        settings = await get_settings(grp_id)

        if settings.get("shortlink") and not await has_premium_or_grace(uid):
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

        # ==================================================
        # SCHEDULE DELETION (NON-BLOCKING)
        # ==================================================
        deletion_task = asyncio.create_task(
            schedule_file_deletion(client, sent, uid, file_id)
        )
        
        # Track deletion task
        task_key = f"delete_{sent.id}"
        active_tasks[task_key] = deletion_task
        
        # Cleanup when done
        def cleanup_deletion(t):
            active_tasks.pop(task_key, None)
        
        deletion_task.add_done_callback(cleanup_deletion)
        
    except Exception as e:
        pass


# ======================================================
# RESEND HANDLER
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

    # Use the same delivery mechanism
    asyncio.create_task(deliver_file(client, uid, 0, file_id))
