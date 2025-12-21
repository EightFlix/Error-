import os
import sys
import time
import asyncio
from datetime import datetime

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from info import (
    ADMINS,
    LOG_CHANNEL,
    SECOND_FILES_DATABASE_URL,
    INDEX_CHANNELS,
    script
)

from database.users_chats_db import db
from database.ia_filterdb import (
    db_count_documents,
    second_db_count_documents,
    delete_files
)

from utils import get_size, get_readable_time, temp


# ======================================================
# 📊 SYSTEM STATS
# ======================================================

@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_cmd(bot, message):
    files = db_count_documents()
    users = await db.total_users_count()
    chats = await db.total_chat_count()
    premium = db.get_premium_count()

    used_files = get_size(await db.get_files_db_size())
    used_data = get_size(await db.get_data_db_size())

    if SECOND_FILES_DATABASE_URL:
        sec_files = second_db_count_documents()
        sec_used = get_size(await db.get_second_files_db_size())
    else:
        sec_files = sec_used = "-"

    uptime = get_readable_time(time.time() - temp.START_TIME)

    await message.reply_text(
        script.STATUS_TXT.format(
            users,
            premium,
            chats,
            used_data,
            files,
            used_files,
            sec_files,
            sec_used,
            uptime
        )
    )


# ======================================================
# 🩺 PREMIUM HEALTH CORE (shared)
# ======================================================

async def run_premium_health(auto_fix: bool = False):
    premium_users = db.get_premium_users()
    now = datetime.utcnow()

    total = expired_bug = missing_invoice = fixed = admin_skipped = 0

    for user in premium_users:
        uid = user["id"]

        if uid in ADMINS:
            admin_skipped += 1
            continue

        status = user.get("status", {})
        expire = status.get("expire")
        if not expire:
            continue

        if isinstance(expire, (int, float)):
            expire = datetime.utcfromtimestamp(expire)

        total += 1

        if expire < now:
            expired_bug += 1
            if auto_fix:
                status.update({
                    "premium": False,
                    "plan": "",
                    "expire": "",
                    "last_reminder": "expired"
                })
                db.update_plan(uid, status)
                fixed += 1
            continue

        if not status.get("invoice"):
            missing_invoice += 1

    report = (
        "🩺 **Premium Health Report**\n\n"
        f"👥 Active Premium Users : `{total}`\n"
        f"❌ Expired but Active   : `{expired_bug}`\n"
        f"🧾 Missing Invoices    : `{missing_invoice}`\n"
        f"👑 Admin Skipped       : `{admin_skipped}`\n\n"
        f"🛠️ Auto-Fix Applied    : `{'YES' if auto_fix else 'NO'}`\n"
        f"✅ Fixed Issues        : `{fixed}`\n\n"
        f"🕒 Checked At          : `{now.strftime('%d %b %Y, %I:%M %p')}`"
    )

    return report


# ======================================================
# 🩺 MANUAL PREMIUM HEALTH
# ======================================================

@Client.on_message(filters.command("premium_health") & filters.user(ADMINS))
async def premium_health(bot, message):
    auto_fix = "--fix" in message.text.lower()

    report = await run_premium_health(auto_fix)

    await message.reply_text(report)

    try:
        await bot.send_message(LOG_CHANNEL, report)
    except:
        pass


# ======================================================
# ⏰ DAILY AUTO HEALTH REPORT
# ======================================================

async def daily_health_report(bot):
    await asyncio.sleep(60)  # wait after startup

    while True:
        try:
            report = await run_premium_health(auto_fix=False)
            await bot.send_message(
                LOG_CHANNEL,
                "📅 **Daily Auto Premium Health Check**\n\n" + report
            )
        except:
            pass

        await asyncio.sleep(86400)  # 24 hours


# ======================================================
# ⚠️ SAFE DELETE
# ======================================================

@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_files_cmd(bot, message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: `/delete keyword`")

    keyword = message.text.split(" ", 1)[1]

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"confirm_delete#{keyword}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_data")],
        ]
    )

    await message.reply(
        f"⚠️ **Permanent Action**\n\nDelete all files related to:\n`{keyword}` ?",
        reply_markup=buttons
    )


@Client.on_callback_query(filters.regex("^confirm_delete#"))
async def confirm_delete_cb(bot, query):
    if query.from_user.id not in ADMINS:
        return await query.answer("Not allowed", show_alert=True)

    keyword = query.data.split("#", 1)[1]
    count = await delete_files(keyword)

    await query.message.edit(
        f"🗑️ **Delete Completed**\n\nKeyword: `{keyword}`\nFiles Removed: `{count}`"
    )


# ======================================================
# 🔄 RESTART
# ======================================================

@Client.on_message(filters.command("restart") & filters.user(ADMINS))
async def restart_bot(bot, message):
    msg = await message.reply("🔄 Restarting bot...")

    with open("restart.txt", "w") as f:
        f.write(f"{msg.chat.id}\n{msg.id}")

    try:
        await bot.send_message(
            LOG_CHANNEL,
            f"♻️ **Bot Restarted**\n"
            f"👤 Admin: {message.from_user.mention}\n"
            f"🕒 {time.strftime('%d %b %Y, %I:%M %p')}"
        )
    except:
        pass

    os.execl(sys.executable, sys.executable, "bot.py")


# ======================================================
# 📢 BROADCAST
# ======================================================

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_handler(bot, message):
    users = await db.get_all_users()
    src = message.reply_to_message

    status = await message.reply("📣 Broadcasting started...")

    success = failed = 0

    for user in users:
        try:
            await src.copy(chat_id=user["id"])
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
            await db.delete_user(user["id"])

    await status.edit(
        f"📊 **Broadcast Finished**\n\n"
        f"✅ Success: `{success}`\n"
        f"❌ Failed: `{failed}`"
    )


# ======================================================
# 🚀 START DAILY TASK
# ======================================================

@Client.on_start()
async def start_health_task(bot):
    asyncio.create_task(daily_health_report(bot))
