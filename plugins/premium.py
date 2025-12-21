import qrcode
import secrets
import asyncio
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from hydrogram.errors import ListenerTimeout

from info import (
    ADMINS,
    IS_PREMIUM,
    PRE_DAY_AMOUNT,
    UPI_ID,
    UPI_NAME,
    RECEIPT_SEND_USERNAME,
)

from database.users_chats_db import db
from utils import is_premium, temp

# ======================================================
# 🔧 HELPERS
# ======================================================

REMINDER_STEPS = [
    ("12 hours", timedelta(hours=12)),
    ("6 hours", timedelta(hours=6)),
    ("3 hours", timedelta(hours=3)),
    ("1 hour", timedelta(hours=1)),
    ("10 minutes", timedelta(minutes=10)),
]

def format_time(dt: datetime) -> str:
    return dt.strftime("%d %b %Y, %I:%M %p")

def parse_duration(text: str):
    text = text.lower().strip()
    num = int("".join(filter(str.isdigit, text)) or 0)
    if num <= 0:
        return None
    if "min" in text:
        return timedelta(minutes=num)
    if "hour" in text or "hr" in text:
        return timedelta(hours=num)
    if "day" in text:
        return timedelta(days=num)
    if "month" in text:
        return timedelta(days=30 * num)
    if "year" in text:
        return timedelta(days=365 * num)
    return None

def generate_invoice_id():
    return "PRM-" + secrets.token_hex(3).upper()

def build_invoice_text(inv: dict) -> str:
    return (
        "🧾 **PAYMENT INVOICE**\n\n"
        f"🆔 Invoice ID : `{inv['id']}`\n"
        f"💎 Plan       : {inv['plan']}\n"
        f"💰 Amount     : ₹{inv['amount']}\n"
        f"🕒 Activated  : {inv['activated']}\n"
        f"⏰ Valid Till : {inv['expire']}\n\n"
        "Thank you for your purchase 💙"
    )

def buy_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Buy / Renew Premium", callback_data="buy_premium")]
    ])

# ======================================================
# 👤 USER COMMANDS
# ======================================================

@Client.on_message(filters.command("plan") & filters.private)
async def plan_cmd(_, message):
    if not IS_PREMIUM:
        return await message.reply("⚠️ Premium system is disabled.")

    if message.from_user.id in ADMINS:
        return await message.reply(
            "👑 **Admin Access**\nLifetime Premium\nNo expiry 🚀"
        )

    prm = await is_premium(message.from_user.id, message._client)
    if prm:
        return await message.reply("✅ You already have Premium.\nUse /myplan")

    await message.reply(
        "💎 **Premium Benefits**\n\n"
        "🚀 Faster access\n"
        "🔓 No ads\n"
        "📩 PM Search\n",
        reply_markup=buy_button()
    )

@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(_, message):
    if message.from_user.id in ADMINS:
        return await message.reply("👑 Lifetime Premium")

    mp = db.get_plan(message.from_user.id)
    if not mp.get("premium"):
        return await message.reply("❌ No active premium.")

    await message.reply(
        "🎉 **Premium Active**\n\n"
        f"💎 Plan: {mp.get('plan')}\n"
        f"⏰ Valid Till: {format_time(mp['expire'])}"
    )

@Client.on_message(filters.command("invoice") & filters.private)
async def invoice_cmd(_, message):
    mp = db.get_plan(message.from_user.id)
    inv = mp.get("invoice")
    if not inv:
        return await message.reply("❌ No invoice found.")
    await message.reply(build_invoice_text(inv))

# ======================================================
# 🔔 PREMIUM REMINDER SCHEDULER
# ======================================================

async def premium_reminder_worker(bot: Client):
    while True:
        users = db.get_premium_users()
        now = datetime.utcnow()

        for u in users:
            uid = u["id"]
            if uid in ADMINS:
                continue

            mp = u["status"]
            if not mp.get("premium"):
                continue

            expire = mp.get("expire")
            if not expire:
                continue

            remaining = expire - now
            last_sent = mp.get("last_reminder")

            for label, delta in REMINDER_STEPS:
                if remaining <= delta and last_sent != label:
                    try:
                        # delete old reminder
                        if mp.get("last_msg_id"):
                            await bot.delete_messages(uid, mp["last_msg_id"])
                    except:
                        pass

                    msg = await bot.send_message(
                        uid,
                        f"⏳ **Premium Expiry Alert**\n\n"
                        f"Your premium will expire in **{label}**.\n\n"
                        f"⏰ Expiry: {format_time(expire)}",
                        reply_markup=buy_button()
                    )

                    mp.update({
                        "last_reminder": label,
                        "last_msg_id": msg.id
                    })
                    db.update_plan(uid, mp)
                    break

            if remaining.total_seconds() <= 0:
                try:
                    await bot.send_message(
                        uid,
                        "❌ **Premium Expired**\n\nRenew to continue premium access.",
                        reply_markup=buy_button()
                    )
                except:
                    pass
                mp.update({
                    "premium": False,
                    "plan": "",
                    "expire": "",
                    "last_reminder": None,
                    "last_msg_id": None
                })
                db.update_plan(uid, mp)

        await asyncio.sleep(300)  # every 5 minutes
