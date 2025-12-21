import asyncio
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import (
    IS_STREAM,
    PM_FILE_DELETE_TIME,
    PROTECT_CONTENT
)

from database.ia_filterdb import get_file_details
from database.users_chats_db import db
from utils import (
    get_settings,
    get_size,
    get_shortlink,
    get_readable_time,
    is_premium,
    temp
)

# ======================================================
# 🔐 CONFIG (ULTRA-PRO)
# ======================================================

GRACE_PERIOD = timedelta(minutes=30)
AUTO_UPGRADE_TRIGGER = 3          # shortlink unlock count
AUTO_UPGRADE_COOLDOWN = 6 * 3600  # 6 hours
EXPIRY_REMINDER_WINDOWS = [       # seconds
    12 * 3600,
    6 * 3600,
    3 * 3600,
    3600,
    600
]

# in-memory trackers (lightweight)
temp.AUTO_UPGRADE = {}      # user_id → {count, last_shown}
temp.PREMIUM_REMINDERS = {} # user_id → [msg_ids]


# ======================================================
# 🧠 PREMIUM CHECK WITH GRACE
# ======================================================

async def has_premium_or_grace(user_id, bot):
    if user_id in temp.BANNED_USERS:
        return False

    # admins are always premium
    if user_id in temp.PREMIUM or user_id in db.ADMINS if hasattr(db, "ADMINS") else False:
        return True

    plan = db.get_plan(user_id)
    if not plan.get("premium"):
        return False

    expire = plan.get("expire")
    if not expire:
        return False

    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    now = datetime.utcnow()

    if now <= expire:
        return True

    if now <= expire + GRACE_PERIOD:
        return True

    return False


# ======================================================
# 🔔 PREMIUM EXPIRY REMINDER (PM only)
# ======================================================

async def maybe_send_expiry_reminder(bot, user_id):
    if await is_premium(user_id, bot) is False:
        return

    plan = db.get_plan(user_id)
    expire = plan.get("expire")
    if not expire:
        return

    if isinstance(expire, (int, float)):
        expire = datetime.utcfromtimestamp(expire)

    remaining = int((expire - datetime.utcnow()).total_seconds())
    if remaining <= 0:
        return

    # prevent spam
    last = plan.get("last_reminder")
    for window in EXPIRY_REMINDER_WINDOWS:
        if remaining <= window and last != window:
            try:
                msg = await bot.send_message(
                    user_id,
                    f"⏰ **Premium Expiring Soon**\n\n"
                    f"Your premium expires in `{get_readable_time(remaining)}`.\n"
                    "Renew now to avoid interruption.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⚡ Renew Now", callback_data="buy_premium")]
                    ])
                )
                temp.PREMIUM_REMINDERS.setdefault(user_id, []).append(msg.id)
                plan["last_reminder"] = window
                db.update_plan(user_id, plan)
            except:
                pass
            break


# ======================================================
# 🧠 SMART AUTO-UPGRADE SUGGESTION
# ======================================================

async def maybe_suggest_upgrade(bot, user_id):
    if await is_premium(user_id, bot):
        return

    data = temp.AUTO_UPGRADE.get(user_id, {"count": 0, "last": 0})
    data["count"] += 1
    temp.AUTO_UPGRADE[user_id] = data

    now = int(datetime.utcnow().timestamp())
    if (
        data["count"] >= AUTO_UPGRADE_TRIGGER
        and now - data.get("last", 0) > AUTO_UPGRADE_COOLDOWN
    ):
        try:
            await bot.send_message(
                user_id,
                "✨ **Smart Tip**\n\n"
                "You're unlocking files frequently today.\n"
                "Premium will save your time ⏱️\n\n"
                "🚫 No ads\n⚡ Instant access",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚡ Upgrade Now", callback_data="buy_premium")]
                ])
            )
            data["last"] = now
            data["count"] = 0
            temp.AUTO_UPGRADE[user_id] = data
        except:
            pass


# ======================================================
# 📦 FILE DELIVERY (BUTTON)
# ======================================================

@Client.on_callback_query(filters.regex(r"^file#"))
async def file_delivery_handler(client: Client, query: CallbackQuery):
    _, file_id = query.data.split("#", 1)

    file = await get_file_details(file_id)
    if not file:
        return await query.answer("❌ File not found.", show_alert=True)

    settings = await get_settings(query.message.chat.id)
    uid = query.from_user.id

    premium_ok = await has_premium_or_grace(uid, client)

    # 🔔 expiry reminder hook
    asyncio.create_task(maybe_send_expiry_reminder(client, uid))

    # ❌ free user → shortlink
    if settings.get("shortlink") and not premium_ok:
        await maybe_suggest_upgrade(client, uid)

        link = await get_shortlink(
            settings["url"],
            settings["api"],
            f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
        )

        return await query.message.reply_text(
            f"<b>📁 File:</b> {file['file_name']}\n"
            f"<b>📦 Size:</b> {get_size(file['file_size'])}\n\n"
            "🔓 Unlock the file below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Get File", url=link)],
                [InlineKeyboardButton("⚡ Upgrade Premium", callback_data="buy_premium")],
                [InlineKeyboardButton("❌ Close", callback_data="close_data")]
            ])
        )

    # ✅ premium / grace
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
    except:
        return await message.reply("❌ Invalid link.")

    file = await get_file_details(file_id)
    if not file:
        return await message.reply("❌ File not found.")

    settings = await get_settings(int(grp_id))
    uid = message.from_user.id

    premium_ok = await has_premium_or_grace(uid, client)
    asyncio.create_task(maybe_send_expiry_reminder(client, uid))

    if settings.get("shortlink") and not premium_ok:
        return await message.reply(
            "🔒 Your premium has expired.\n\n"
            "Renew now to continue using premium features.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Renew Premium", callback_data="buy_premium")]
            ])
        )

    caption = settings["caption"].format(
        file_name=file["file_name"],
        file_size=get_size(file["file_size"]),
        file_caption=file.get("caption", "")
    )

    buttons = []
    if IS_STREAM:
        buttons.append([InlineKeyboardButton("▶️ Watch / Download", callback_data=f"stream#{file_id}")])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])

    sent = await client.send_cached_media(
        chat_id=uid,
        file_id=file_id,
        caption=caption,
        protect_content=PROTECT_CONTENT,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    notice = await sent.reply(
        f"⚠️ File will be deleted in {get_readable_time(PM_FILE_DELETE_TIME)}."
    )

    await asyncio.sleep(PM_FILE_DELETE_TIME)
    await sent.delete()
    await notice.edit(
        "⌛ Time expired. File deleted.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Get Again", callback_data=f"file#{file_id}")]
        ])
    )
