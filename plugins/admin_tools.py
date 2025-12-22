import os
import sys
import time
import asyncio
from datetime import datetime

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from hydrogram.errors import MessageNotModified

from info import ADMINS, LOG_CHANNEL
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents, delete_files
from utils import get_size, get_readable_time, temp

# ======================================================
# 🧠 LIVE DASHBOARD CONFIG
# ======================================================

DASH_REFRESH = 45  # seconds
DASH_CACHE = {}   # admin_id -> (text, ts)

# ======================================================
# 🛡 SAFE EDIT (FIX MESSAGE_NOT_MODIFIED)
# ======================================================

async def safe_edit(msg, text, **kwargs):
    try:
        if msg.text == text:
            return
        await msg.edit(text, **kwargs)
    except MessageNotModified:
        pass
    except Exception:
        pass

# ======================================================
# 📊 DASHBOARD BUILDER
# ======================================================

async def build_dashboard():
    try:
        users = await db.total_users_count()
    except:
        users = 0

    try:
        chats = db.groups.count_documents({})
    except:
        chats = 0

    try:
        files = db_count_documents()
    except:
        files = 0

    try:
        premium = db.premium.count_documents({"plan.premium": True})
    except:
        premium = 0

    try:
        used_data = get_size(await db.get_data_db_size())
    except:
        used_data = "0 B"

    uptime = get_readable_time(time.time() - temp.START_TIME)
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")

    # ---- live indexing stats ----
    idx = temp.INDEX_STATS if hasattr(temp, "INDEX_STATS") else {}
    idx_text = "❌ Not running"
    if idx.get("running"):
        dur = max(1, time.time() - idx.get("start", time.time()))
        speed = idx.get("saved", 0) / dur
        idx_text = f"🚀 {speed:.2f} files/sec"

    return (
        "📊 <b>LIVE ADMIN DASHBOARD</b>\n\n"
        f"👤 <b>Users</b>        : <code>{users}</code>\n"
        f"👥 <b>Groups</b>       : <code>{chats}</code>\n"
        f"📦 <b>Indexed Files</b>: <code>{files}</code>\n"
        f"💎 <b>Premium Users</b>: <code>{premium}</code>\n\n"
        f"⚡ <b>Index Speed</b>  : <code>{idx_text}</code>\n"
        f"🗃 <b>DB Size</b>      : <code>{used_data}</code>\n\n"
        f"⏱ <b>Uptime</b>       : <code>{uptime}</code>\n"
        f"🔄 <b>Updated</b>      : <code>{now}</code>"
    )

# ======================================================
# 🎛 DASHBOARD BUTTONS
# ======================================================

def dashboard_buttons():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="dash_refresh"),
                InlineKeyboardButton("🩺 Health", callback_data="dash_health")
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="dash_broadcast"),
                InlineKeyboardButton("🗑 Delete", callback_data="dash_delete")
            ],
            [
                InlineKeyboardButton("🔄 Restart", callback_data="dash_restart"),
                InlineKeyboardButton("❌ Close", callback_data="close_data")
            ]
        ]
    )

# ======================================================
# 🚀 OPEN DASHBOARD
# ======================================================

@Client.on_message(filters.command(["admin", "dashboard"]) & filters.user(ADMINS))
async def open_dashboard(bot, message):
    text = await build_dashboard()
    msg = await message.reply(
        text,
        reply_markup=dashboard_buttons(),
        disable_web_page_preview=True
    )
    DASH_CACHE[message.from_user.id] = (text, time.time())

# ======================================================
# 🔁 DASHBOARD CALLBACKS
# ======================================================

@Client.on_callback_query(filters.regex("^dash_"))
async def dashboard_callbacks(bot, query: CallbackQuery):
    if query.from_user.id not in ADMINS:
        return await query.answer("Not allowed", show_alert=True)

    action = query.data

    # ---------- REFRESH ----------
    if action == "dash_refresh":
        cached = DASH_CACHE.get(query.from_user.id)
        if cached and time.time() - cached[1] < DASH_REFRESH:
            text = cached[0]
        else:
            text = await build_dashboard()
            DASH_CACHE[query.from_user.id] = (text, time.time())

        await safe_edit(
            query.message,
            text,
            reply_markup=dashboard_buttons(),
            disable_web_page_preview=True
        )

    # ---------- HEALTH ----------
    elif action == "dash_health":
        report = await run_premium_health(False)
        await safe_edit(query.message, report)

        try:
            await bot.send_message(LOG_CHANNEL, report)
        except:
            pass

    # ---------- BROADCAST ----------
    elif action == "dash_broadcast":
        await safe_edit(
            query.message,
            "📢 <b>Broadcast</b>\n\nReply to any message and use:\n<code>/broadcast</code>"
        )

    # ---------- DELETE ----------
    elif action == "dash_delete":
        await safe_edit(
            query.message,
            "🗑 <b>Delete Files</b>\n\nUse:\n<code>/delete keyword</code>"
        )

    # ---------- RESTART ----------
    elif action == "dash_restart":
        await safe_edit(query.message, "🔄 Restarting bot...")

        with open("restart.txt", "w") as f:
            f.write(f"{query.message.chat.id}\n{query.message.id}")

        try:
            await bot.send_message(
                LOG_CHANNEL,
                f"♻️ <b>Bot Restarted</b>\nAdmin: {query.from_user.mention}"
            )
        except:
            pass

        os.execl(sys.executable, sys.executable, "bot.py")

    await query.answer()

# ======================================================
# 🩺 PREMIUM HEALTH
# ======================================================

async def run_premium_health(auto_fix=False):
    now = datetime.utcnow()
    users = db.get_premium_users()

    total = expired = fixed = no_invoice = admin_skip = 0

    for u in users:
        uid = u.get("id")
        if uid in ADMINS:
            admin_skip += 1
            continue

        plan = u.get("plan", {})
        expire = plan.get("expire")
        if not expire:
            continue

        total += 1

        if expire < now:
            expired += 1
            if auto_fix:
                plan.update({
                    "premium": False,
                    "expire": "",
                    "plan": "free"
                })
                db.update_plan(uid, plan)
                fixed += 1

        if not plan.get("invoice"):
            no_invoice += 1

    return (
        "🩺 <b>PREMIUM HEALTH REPORT</b>\n\n"
        f"👥 Active Premium : <code>{total}</code>\n"
        f"❌ Expired Bug   : <code>{expired}</code>\n"
        f"🧾 No Invoice    : <code>{no_invoice}</code>\n"
        f"👑 Admin Skipped : <code>{admin_skip}</code>\n\n"
        f"🛠 Auto Fix      : <code>{'ON' if auto_fix else 'OFF'}</code>\n"
        f"✅ Fixed         : <code>{fixed}</code>\n\n"
        f"🕒 Checked At    : <code>{now.strftime('%d %b %Y, %I:%M %p')}</code>"
    )

# ======================================================
# 🗑 SAFE DELETE
# ======================================================

@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_cmd(bot, message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: <code>/delete keyword</code>")

    key = message.text.split(" ", 1)[1]

    btn = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"del#{key}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_data")]
        ]
    )

    await message.reply(
        f"⚠️ <b>Permanent Delete</b>\n\nKeyword:\n<code>{key}</code>",
        reply_markup=btn
    )


@Client.on_callback_query(filters.regex("^del#"))
async def confirm_delete(bot, query: CallbackQuery):
    if query.from_user.id not in ADMINS:
        return

    key = query.data.split("#", 1)[1]
    count = await delete_files(key)

    await safe_edit(
        query.message,
        f"🗑 <b>Delete Completed</b>\n\n"
        f"Keyword: <code>{key}</code>\n"
        f"Files Removed: <code>{count}</code>"
    )
