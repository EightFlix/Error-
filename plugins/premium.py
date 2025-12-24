import qrcode
import secrets
import asyncio
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from hydrogram.errors import ListenerTimeout, FloodWait

from info import (
    ADMINS,
    IS_PREMIUM,
    PRE_DAY_AMOUNT,
    UPI_ID,
    UPI_NAME,
    RECEIPT_SEND_USERNAME,
)

from database.users_chats_db import db
from utils import is_premium


# ======================================================
# ⚙️ CONFIG
# ======================================================

LISTEN_SHORT = 180   # 3 min
LISTEN_LONG = 300    # 5 min

active_sessions = set()


# ======================================================
# 🧠 HELPERS
# ======================================================

def fmt(dt):
    """Format datetime to readable string"""
    if isinstance(dt, (int, float)):
        dt = datetime.utcfromtimestamp(dt)
    return dt.strftime("%d %b %Y, %I:%M %p")


def parse_duration(text: str):
    """Parse duration from text like '1 day', '7 days', '1 month'"""
    if not text:
        return None

    text = text.lower().strip()
    num = int("".join(filter(str.isdigit, text)) or 0)
    if num <= 0:
        return None

    if "day" in text:
        return timedelta(days=num)
    if "month" in text:
        return timedelta(days=30 * num)
    if "year" in text:
        return timedelta(days=365 * num)
    if "hour" in text:
        return timedelta(hours=num)

    return None


def gen_invoice_id():
    """Generate unique invoice ID"""
    return "PRM-" + secrets.token_hex(3).upper()


def buy_btn():
    """Buy premium button"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("💰 Buy / Renew Premium", callback_data="buy_premium")]]
    )


def cancel_btn():
    """Cancel button"""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")]]
    )


# ======================================================
# 👤 USER COMMANDS
# ======================================================

@Client.on_message(filters.command("plan") & filters.private)
async def plan_cmd(client, message):
    """Show premium plans and pricing"""
    if not IS_PREMIUM:
        return await message.reply("⚠️ Premium system disabled")

    uid = message.from_user.id

    if uid in ADMINS:
        return await message.reply("👑 You are Admin = Lifetime Premium Access")

    premium = await is_premium(uid, client)

    text = f"""
💎 **Premium Benefits**

🚀 Faster search & downloads
📩 PM Search access
🔕 No advertisements
⚡ Instant file delivery
🎯 Priority support
🌟 Exclusive features

💰 **Pricing:** ₹{PRE_DAY_AMOUNT}/day

📌 **Example Plans:**
• 7 days = ₹{7 * PRE_DAY_AMOUNT}
• 30 days = ₹{30 * PRE_DAY_AMOUNT}
• 365 days = ₹{365 * PRE_DAY_AMOUNT}
"""

    if premium:
        text += "\n✅ **You already have Premium!**\nYou can renew or extend your current plan."

    await message.reply(text, reply_markup=buy_btn())


@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(client, message):
    """Show user's current premium plan"""
    uid = message.from_user.id

    if uid in ADMINS:
        return await message.reply("👑 You are Admin = Lifetime Premium Access")

    plan = await db.get_plan(uid)

    if not plan or not plan.get("premium"):
        return await message.reply(
            "❌ You don't have any active premium plan",
            reply_markup=buy_btn()
        )

    expire = plan.get("expire")
    if isinstance(expire, (int, float)):
        exp_dt = datetime.utcfromtimestamp(expire)
    else:
        exp_dt = expire
    
    now = datetime.utcnow()
    remaining = exp_dt - now

    if remaining.total_seconds() <= 0:
        await db.update_plan(uid, {
            "premium": False,
            "plan": None,
            "expire": None
        })
        return await message.reply(
            "❌ Your premium plan has expired!",
            reply_markup=buy_btn()
        )

    await message.reply(
        f"""
🎉 **Premium Active**

💎 Plan     : {plan.get("plan")}
⏰ Expires  : {fmt(exp_dt)}
⏳ Remaining: {max(0, remaining.days)} days {remaining.seconds // 3600} hours
""",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("🔄 Renew", callback_data="buy_premium"),
                InlineKeyboardButton("🧾 Invoices", callback_data="show_invoices")
            ]]
        )
    )


@Client.on_message(filters.command("invoice") & filters.private)
async def invoice_cmd(client, message):
    """Show latest invoice"""
    plan = await db.get_plan(message.from_user.id)
    invoices = plan.get("invoices", []) if plan else []

    if not invoices:
        return await message.reply("❌ No invoices found")

    inv = invoices[-1]

    await message.reply(
        f"""
🧾 **Latest Invoice**

🆔 **ID:** `{inv.get('id')}`
💎 **Plan:** {inv.get('plan')}
💰 **Amount:** ₹{inv.get('amount')}
📅 **Activated:** {inv.get('activated')}
⏰ **Expires:** {inv.get('expire')}
""",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📜 View All Invoices", callback_data="show_invoices")]]
        )
    )


@Client.on_callback_query(filters.regex("^show_invoices$"))
async def show_invoice_cb(client, query: CallbackQuery):
    """Show all invoices"""
    plan = await db.get_plan(query.from_user.id)
    invoices = plan.get("invoices", []) if plan else []

    if not invoices:
        return await query.answer("❌ No invoices found", show_alert=True)

    text = "🧾 **Invoice History**\n\n"
    for inv in invoices[-10:][::-1]:  # Last 10 invoices, newest first
        text += f"• `{inv.get('id')}` | ₹{inv.get('amount')} | {inv.get('plan')}\n"
        text += f"  📅 {inv.get('activated')} → {inv.get('expire')}\n\n"

    await query.message.edit(
        text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back", callback_data="back_to_myplan")]]
        )
    )


@Client.on_callback_query(filters.regex("^back_to_myplan$"))
async def back_to_myplan_cb(client, query: CallbackQuery):
    """Go back to myplan view"""
    uid = query.from_user.id
    
    if uid in ADMINS:
        return await query.message.edit("👑 You are Admin = Lifetime Premium Access")

    plan = await db.get_plan(uid)

    if not plan or not plan.get("premium"):
        return await query.message.edit(
            "❌ You don't have any active premium plan",
            reply_markup=buy_btn()
        )

    expire = plan.get("expire")
    if isinstance(expire, (int, float)):
        exp_dt = datetime.utcfromtimestamp(expire)
    else:
        exp_dt = expire
    
    now = datetime.utcnow()
    remaining = exp_dt - now

    if remaining.total_seconds() <= 0:
        await db.update_plan(uid, {
            "premium": False,
            "plan": None,
            "expire": None
        })
        return await query.message.edit(
            "❌ Your premium plan has expired!",
            reply_markup=buy_btn()
        )

    await query.message.edit(
        f"""
🎉 **Premium Active**

💎 Plan     : {plan.get("plan")}
⏰ Expires  : {fmt(exp_dt)}
⏳ Remaining: {max(0, remaining.days)} days {remaining.seconds // 3600} hours
""",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("🔄 Renew", callback_data="buy_premium"),
                InlineKeyboardButton("🧾 Invoices", callback_data="show_invoices")
            ]]
        )
    )


# ======================================================
# 💰 BUY FLOW
# ======================================================

@Client.on_callback_query(filters.regex("^buy_premium$"))
async def buy_premium(client, query: CallbackQuery):
    """Start premium purchase flow"""
    uid = query.from_user.id

    if uid in active_sessions:
        return await query.answer("⚠️ You already have an active payment session", show_alert=True)

    active_sessions.add(uid)

    await query.message.edit(
        """
🕒 **Enter Duration**

Send duration in this format:
• `1 day` or `7 days`
• `1 month` or `3 months`
• `1 year`

💡 Example: `30 days` or `1 month`
""",
        reply_markup=cancel_btn()
    )

    try:
        msg = await client.listen(query.message.chat.id, filters=filters.user(uid), timeout=LISTEN_SHORT)
        
        if not msg.text:
            raise ValueError("No text received")
            
        duration = parse_duration(msg.text)
        if not duration:
            raise ValueError("Invalid duration format")
            
    except asyncio.TimeoutError:
        active_sessions.discard(uid)
        return await query.message.edit("⏱️ Timeout! Payment cancelled.")
    except Exception as e:
        active_sessions.discard(uid)
        return await query.message.edit(f"❌ Invalid duration format\n\nPlease try again with: `7 days` or `1 month`")

    days = max(1, duration.days)
    amount = days * PRE_DAY_AMOUNT
    plan_text = msg.text.strip()

    # Generate UPI QR code
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
    qr = qrcode.make(upi_url)
    bio = BytesIO()
    qr.save(bio, "PNG")
    bio.seek(0)
    bio.name = "qr_code.png"

    await query.message.reply_photo(
        bio,
        caption=f"""
💰 **Payment Details**

📦 **Plan:** {plan_text}
💵 **Amount:** ₹{amount}
⏰ **Duration:** {days} days

📱 **UPI ID:** `{UPI_ID}`

📸 **Next Step:** Send payment screenshot after completing payment
""",
        reply_markup=cancel_btn()
    )

    try:
        receipt = await client.listen(query.message.chat.id, filters=filters.user(uid) & filters.photo, timeout=LISTEN_LONG)
        
        if not receipt.photo:
            raise ValueError("No photo received")
            
    except asyncio.TimeoutError:
        active_sessions.discard(uid)
        return await query.message.reply("⏱️ Timeout! Screenshot not received. Payment cancelled.")
    except Exception as e:
        active_sessions.discard(uid)
        return await query.message.reply("❌ Screenshot not received. Please try again.")

    # Send to admin for approval
    buttons = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok#{uid}#{plan_text}#{amount}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"pay_no#{uid}")
        ]]
    )

    try:
        await client.send_photo(
            RECEIPT_SEND_USERNAME,
            receipt.photo.file_id,
            caption=f"""
🔔 **#PremiumPayment**

👤 **User ID:** `{uid}`
👤 **Username:** @{receipt.from_user.username or 'N/A'}
👤 **Name:** {receipt.from_user.first_name}

📦 **Plan:** {plan_text}
💰 **Amount:** ₹{amount}
⏰ **Duration:** {days} days

⏰ **Time:** {datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC")}
""",
            reply_markup=buttons
        )
    except Exception as e:
        active_sessions.discard(uid)
        return await receipt.reply(f"❌ Error sending to admin: {e}")

    await receipt.reply(
        "✅ **Screenshot received!**\n\n⏳ Your payment is being reviewed by admin.\nYou'll be notified once approved."
    )
    active_sessions.discard(uid)


@Client.on_callback_query(filters.regex("^cancel_payment$"))
async def cancel_payment(_, query: CallbackQuery):
    """Cancel payment flow"""
    uid = query.from_user.id
    active_sessions.discard(uid)
    await query.message.edit("❌ Payment process cancelled")
    await query.answer("Cancelled", show_alert=False)


# ======================================================
# 🛂 ADMIN APPROVAL
# ======================================================

@Client.on_callback_query(filters.regex("^pay_ok#"))
async def approve_payment(client, query: CallbackQuery):
    """Admin approves payment"""
    if query.from_user.id not in ADMINS:
        return await query.answer("⛔ Not authorized", show_alert=True)

    try:
        _, uid, plan_txt, amount = query.data.split("#", 3)
        uid = int(uid)
        amount = int(amount)
    except Exception as e:
        return await query.answer(f"❌ Invalid data: {e}", show_alert=True)

    duration = parse_duration(plan_txt)
    if not duration:
        return await query.message.edit("❌ Invalid plan duration")

    now = datetime.utcnow()
    old = await db.get_plan(uid) or {}

    # Calculate expiry date
    expire = old.get("expire")
    if expire:
        if isinstance(expire, (int, float)):
            expire_dt = datetime.utcfromtimestamp(expire)
        else:
            expire_dt = expire
        
        # Extend from expiry if still active, otherwise from now
        expire_dt = expire_dt + duration if expire_dt > now else now + duration
    else:
        expire_dt = now + duration

    # Create invoice
    invoice = {
        "id": gen_invoice_id(),
        "plan": plan_txt,
        "amount": amount,
        "activated": fmt(now),
        "expire": fmt(expire_dt),
        "created_at": now.timestamp()
    }

    invoices = old.get("invoices", [])
    invoices.append(invoice)

    # Update database
    await db.update_plan(uid, {
        "premium": True,
        "plan": plan_txt,
        "expire": expire_dt.timestamp(),
        "activated_at": now.timestamp(),
        "invoices": invoices
    })

    # Notify user
    try:
        await client.send_message(
            uid,
            f"""
🎉 **Premium Activated Successfully!**

💎 **Plan:** {plan_txt}
⏰ **Valid Till:** {fmt(expire_dt)}
🧾 **Invoice ID:** `{invoice['id']}`

Thank you for your purchase! 🙏
Enjoy your premium benefits! ✨
"""
        )
    except Exception as e:
        print(f"Failed to notify user {uid}: {e}")

    # Update admin message
    await query.message.edit_caption(
        query.message.caption + f"\n\n✅ **APPROVED** by @{query.from_user.username}\n⏰ {fmt(now)}"
    )
    await query.answer("✅ Payment Approved Successfully!", show_alert=True)


@Client.on_callback_query(filters.regex("^pay_no#"))
async def reject_payment(client, query: CallbackQuery):
    """Admin rejects payment"""
    if query.from_user.id not in ADMINS:
        return await query.answer("⛔ Not authorized", show_alert=True)

    try:
        uid = int(query.data.split("#")[1])
    except Exception as e:
        return await query.answer(f"❌ Invalid data: {e}", show_alert=True)

    now = datetime.utcnow()

    # Notify user
    try:
        await client.send_message(
            uid,
            """
❌ **Payment Rejected**

Your payment screenshot was rejected by admin.

Possible reasons:
• Invalid/unclear screenshot
• Payment not received
• Wrong amount

Please contact support or try again with correct details.
"""
        )
    except Exception as e:
        print(f"Failed to notify user {uid}: {e}")

    # Update admin message
    await query.message.edit_caption(
        query.message.caption + f"\n\n❌ **REJECTED** by @{query.from_user.username}\n⏰ {fmt(now)}"
    )
    await query.answer("❌ Payment Rejected", show_alert=True)


# ======================================================
# 📊 ADMIN PREMIUM STATS
# ======================================================

@Client.on_message(filters.command("premstats") & filters.user(ADMINS))
async def premium_stats(_, message):
    """Show premium statistics for admin"""
    users = await db.get_premium_users()
    now = datetime.utcnow()

    total = len(users)
    active = 0
    expired = 0
    total_revenue = 0

    active_users = []
    expiring_soon = []  # Expiring in 7 days

    for u in users:
        plan = u.get("plan", {})
        expire = plan.get("expire")
        
        if not expire:
            continue
        
        if isinstance(expire, (int, float)):
            exp_dt = datetime.utcfromtimestamp(expire)
        else:
            exp_dt = expire
        
        if exp_dt > now:
            active += 1
            active_users.append(u)
            
            # Check if expiring soon
            days_left = (exp_dt - now).days
            if days_left <= 7:
                uid = u.get("_id") or u.get("id")
                expiring_soon.append(f"• User {uid}: {days_left} days left")
        else:
            expired += 1
        
        # Calculate revenue
        invoices = plan.get("invoices", [])
        for inv in invoices:
            total_revenue += inv.get("amount", 0)

    expiring_text = "\n".join(expiring_soon[:10]) if expiring_soon else "None"

    await message.reply(
        f"""
📊 **Premium Statistics**

👥 **Total Users:** {total}
✅ **Active:** {active}
❌ **Expired:** {expired}
💰 **Total Revenue:** ₹{total_revenue}

⚠️ **Expiring Soon (7 days):**
{expiring_text}

📅 **Report Generated:** {fmt(now)}
"""
    )


# ======================================================
# 🔧 ADMIN TOOLS
# ======================================================

@Client.on_message(filters.command("givepremium") & filters.user(ADMINS))
async def give_premium_cmd(client, message):
    """Admin manually gives premium to a user"""
    try:
        # Format: /givepremium user_id duration
        # Example: /givepremium 123456789 30 days
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return await message.reply("Usage: `/givepremium user_id duration`\nExample: `/givepremium 123456789 30 days`")
        
        uid = int(parts[1])
        duration_text = parts[2]
        
        duration = parse_duration(duration_text)
        if not duration:
            return await message.reply("❌ Invalid duration format")
        
        now = datetime.utcnow()
        old = await db.get_plan(uid) or {}
        
        expire = old.get("expire")
        if expire:
            if isinstance(expire, (int, float)):
                expire_dt = datetime.utcfromtimestamp(expire)
            else:
                expire_dt = expire
            expire_dt = expire_dt + duration if expire_dt > now else now + duration
        else:
            expire_dt = now + duration
        
        invoice = {
            "id": gen_invoice_id(),
            "plan": f"{duration_text} (Admin Gift)",
            "amount": 0,
            "activated": fmt(now),
            "expire": fmt(expire_dt),
            "created_at": now.timestamp()
        }
        
        invoices = old.get("invoices", [])
        invoices.append(invoice)
        
        await db.update_plan(uid, {
            "premium": True,
            "plan": duration_text,
            "expire": expire_dt.timestamp(),
            "activated_at": now.timestamp(),
            "invoices": invoices
        })
        
        await message.reply(f"✅ Premium given to user {uid} till {fmt(expire_dt)}")
        
        try:
            await client.send_message(
                uid,
                f"🎁 **Free Premium Gift!**\n\n💎 Duration: {duration_text}\n⏰ Valid Till: {fmt(expire_dt)}"
            )
        except:
            pass
            
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@Client.on_message(filters.command("removepremium") & filters.user(ADMINS))
async def remove_premium_cmd(client, message):
    """Admin removes premium from a user"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply("Usage: `/removepremium user_id`")
        
        uid = int(parts[1])
        
        await db.update_plan(uid, {
            "premium": False,
            "plan": None,
            "expire": None
        })
        
        await message.reply(f"✅ Premium removed from user {uid}")
        
        try:
            await client.send_message(
                uid,
                "⚠️ Your premium access has been revoked by admin."
            )
        except:
            pass
            
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
