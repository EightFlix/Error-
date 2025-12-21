import os
import sys
import time
import asyncio
from datetime import datetime

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from info import ADMINS, LOG_CHANNEL, script
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents, delete_files
from utils import get_size, get_readable_time, temp


# ======================================================
# 🧠 ADMIN PANEL
# ======================================================

@Client.on_message(filters.command("admin") & filters.user(ADMINS))
async def admin_panel(bot, message):
    btn = [
        [
            InlineKeyboardButton("📊 Stats", callback_data="ap_stats"),
            InlineKeyboardButton("🩺 Premium Health", callback_data="ap_health")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="ap_broadcast"),
            InlineKeyboardButton("🗑 Delete Files", callback_data="ap_delete")
        ],
        [
            InlineKeyboardButton("🔄 Restart Bot", callback_data="ap_restart"),
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ]
    ]

    await message.reply(
        "👮 **Admin Control Panel**\n\nSelect an action 👇",
        reply_markup=InlineKeyboardMarkup(btn)
    )


# ======================================================
# 📊 SYSTEM STATS
# ======================================================

async def build_stats():
    files = db_count_documents()
    users = await db.total_users_count()
    chats = await db.total_chat_count()
    premium = db.get_premium_count()

    used_files = get_size(await db.get_files_db_size())
    used_data = get_size(await db.get_data_db_size())
    uptime = get_readable_time(time.time() - temp.START_TIME)

    return script.STATUS_TXT.format(
        users,
        premium,
        chats,
        files,
        used_files,
        used_data,
        uptime
    )


# ======================================================
# 🩺 PREMIUM HEALTH CORE
# ======================================================

async def run_premium_health(auto_fix=False):
    now = datetime.utcnow()
    users = db.get_premium_users()

    total = expired_bug = fixed = missing_invoice = admin_skip = 0

    for u in users:
        uid = u["id"]
        if uid in ADMINS:
            admin_skip += 1
            continue

        st = u.get("status", {})
        expire = st.get("expire")
        if not expire:
            continue

        total += 1

        if expire < now:
            expired_bug += 1
            if auto_fix:
                st.update({
                    "premium": False,
                    "expire": "",
                    "plan": "",
                    "last_reminder": "expired"
                })
                db.update_plan(uid, st)
                fixed += 1

        if not st.get("invoice"):
            missing_invoice += 1

    report = (
        "🩺 **Premium Health Report**\n\n"
        f"👥 Active Premium Users : `{total}`\n"
        f"❌ Expired but Active   : `{expired_bug}`\n"
        f"🧾 Missing Invoices    : `{missing_invoice}`\n"
        f"👑 Admin Skipped       : `{admin_skip}`\n\n"
        f"🛠 Auto Fix            : `{'ON' if auto_fix else 'OFF'}`\n"
        f"✅ Fixed               : `{fixed}`\n\n"
        f"🕒 Checked At          : `{now.strftime('%d %b %Y, %I:%M %p')}`"
    )
    return report


# ======================================================
# ⏰ DAILY AUTO HEALTH
# ======================================================

async def daily_health_report(bot):
    await asyncio.sleep(60)
    while True:
        try:
            report = await run_premium_health(False)
            await bot.send_message(
                LOG_CHANNEL,
                "📅 **Daily Premium Health Check**\n\n" + report
            )
        except:
            pass
        await asyncio.sleep(86400)


# ======================================================
# 🧲 CALLBACK HANDLER
# ======================================================

@Client.on_callback_query(filters.regex("^ap_"))
async def admin_callbacks(bot, query: CallbackQuery):
    if query.from_user.id not in ADMINS:
        return await query.answer("Not allowed", show_alert=True)

    data = query.data

    if data == "ap_stats":
        text = await build_stats()
        await query.message.edit(text)

    elif data == "ap_health":
        report = await run_premium_health(False)
        await query.message.edit(report)
        await bot.send_message(LOG_CHANNEL, report)

    elif data == "ap_delete":
        await query.message.edit(
            "🗑 **Delete Files**\n\nUse command:\n`/delete keyword`"
        )

    elif data == "ap_restart":
        await query.message.edit("🔄 Restarting bot...")
        with open("restart.txt", "w") as f:
            f.write(f"{query.message.chat.id}\n{query.message.id}")

        await bot.send_message(
            LOG_CHANNEL,
            f"♻️ **Bot Restarted**\nAdmin: {query.from_user.mention}"
        )
        os.execl(sys.executable, sys.executable, "bot.py")


# ======================================================
# 🗑 SAFE DELETE
# ======================================================

@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_cmd(bot, message):
    if len(message.command) < 2:
        return await message.reply("⚠️ `/delete keyword`")

    key = message.text.split(" ", 1)[1]
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data=f"del#{key}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="close_data")]
    ])

    await message.reply(
        f"⚠️ Delete all files related to:\n`{key}` ?",
        reply_markup=btn
    )


@Client.on_callback_query(filters.regex("^del#"))
async def confirm_delete(bot, query):
    if query.from_user.id not in ADMINS:
        return

    key = query.data.split("#", 1)[1]
    count = await delete_files(key)
    await query.message.edit(
        f"🗑 **Delete Complete**\n\nKeyword: `{key}`\nRemoved: `{count}`"
    )


# ======================================================
# 🚀 START TASKS
# ======================================================

@Client.on_start()
async def start_tasks(bot):
    asyncio.create_task(daily_health_report(bot))
