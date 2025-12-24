import qrcode
import secrets
import asyncio
from io import BytesIO
from datetime import datetime, timedelta

from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import ADMINS, IS_PREMIUM, PRE_DAY_AMOUNT, UPI_ID, UPI_NAME, RECEIPT_SEND_USERNAME
from database.users_chats_db import db
from utils import is_premium


# ======================================================
# ⚙️ CONFIG
# ======================================================

LISTEN_SHORT = 180
LISTEN_LONG = 300
active_sessions = {}  # Changed to dict to store number


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
    
    # Extract number
    num_str = "".join(filter(str.isdigit, text))
    if not num_str:
        return None
    
    num = int(num_str)
    if num <= 0:
        return None
    
    # Convert to days (always return days-based timedelta)
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


def get_expiry_datetime(expire):
    """Convert expire timestamp/datetime to datetime object"""
    if isinstance(expire, (int, float)):
        return datetime.utcfromtimestamp(expire)
    return expire


async def get_plan_data(uid):
    """Get user plan with calculated remaining time"""
    if uid in ADMINS:
        return None, "admin"
    
    plan = await db.get_plan(uid)
    if not plan or not plan.get("premium"):
        return None, "none"
    
    expire = plan.get("expire")
    exp_dt = get_expiry_datetime(expire)
    now = datetime.utcnow()
    remaining = exp_dt - now
    
    if remaining.total_seconds() <= 0:
        await db.update_plan(uid, {"premium": False, "plan": None, "expire": None})
        return None, "expired"
    
    return {
        "plan": plan,
        "exp_dt": exp_dt,
        "remaining": remaining,
        "days": max(0, remaining.days),
        "hours": remaining.seconds // 3600
    }, "active"


# ======================================================
# 🎨 UI HELPERS
# ======================================================

def buy_btn():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💰 Buy / Renew Premium", callback_data="buy_premium")
    ]])


def cancel_btn():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")
    ]])


def duration_buttons(num):
    """Generate duration selection buttons based on number"""
    hours_price = max(1, (num // 24) or 1) * PRE_DAY_AMOUNT
    days_price = num * PRE_DAY_AMOUNT
    months_price = num * 30 * PRE_DAY_AMOUNT
    years_price = num * 365 * PRE_DAY_AMOUNT
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏰ {num} Hours (₹{hours_price})", callback_data=f"dur#{num}#hour")],
        [InlineKeyboardButton(f"📅 {num} Days (₹{days_price})", callback_data=f"dur#{num}#day")],
        [InlineKeyboardButton(f"📆 {num} Months (₹{months_price})", callback_data=f"dur#{num}#month")],
        [InlineKeyboardButton(f"🗓️ {num} Years (₹{years_price})", callback_data=f"dur#{num}#year")],
        [InlineKeyboardButton("🔄 Re-enter Number", callback_data="buy_premium")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")]
    ])


def myplan_buttons():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Renew", callback_data="buy_premium"),
        InlineKeyboardButton("🧾 Invoices", callback_data="show_invoices")
    ]])


def back_btn():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="back_to_myplan")
    ]])


def myplan_text(data):
    return f"""
🎉 **Premium Active**

💎 Plan     : {data['plan'].get("plan")}
⏰ Expires  : {fmt(data['exp_dt'])}
⏳ Remaining: {data['days']} days {data['hours']} hours
"""


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
    data, status = await get_plan_data(message.from_user.id)
    
    if status == "admin":
        return await message.reply("👑 You are Admin = Lifetime Premium Access")
    
    if status in ["none", "expired"]:
        msg = "❌ Your premium plan has expired!" if status == "expired" else "❌ You don't have any active premium plan"
        return await message.reply(msg, reply_markup=buy_btn())
    
    await message.reply(myplan_text(data), reply_markup=myplan_buttons())


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
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📜 View All Invoices", callback_data="show_invoices")
        ]])
    )


@Client.on_callback_query(filters.regex("^show_invoices$"))
async def show_invoice_cb(client, query: CallbackQuery):
    """Show all invoices"""
    plan = await db.get_plan(query.from_user.id)
    invoices = plan.get("invoices", []) if plan else []
    
    if not invoices:
        return await query.answer("❌ No invoices found", show_alert=True)
    
    text = "🧾 **Invoice History**\n\n"
    for inv in invoices[-10:][::-1]:
        text += f"• `{inv.get('id')}` | ₹{inv.get('amount')} | {inv.get('plan')}\n"
        text += f"  📅 {inv.get('activated')} → {inv.get('expire')}\n\n"
    
    await query.message.edit(text, reply_markup=back_btn())


@Client.on_callback_query(filters.regex("^back_to_myplan$"))
async def back_to_myplan_cb(client, query: CallbackQuery):
    """Go back to myplan view"""
    data, status = await get_plan_data(query.from_user.id)
    
    if status == "admin":
        return await query.message.edit("👑 You are Admin = Lifetime Premium Access")
    
    if status in ["none", "expired"]:
        msg = "❌ Your premium plan has expired!" if status == "expired" else "❌ You don't have any active premium plan"
        return await query.message.edit(msg, reply_markup=buy_btn())
    
    await query.message.edit(myplan_text(data), reply_markup=myplan_buttons())


# ======================================================
# 💰 BUY FLOW
# ======================================================

@Client.on_callback_query(filters.regex("^buy_premium$"))
async def buy_premium(client, query: CallbackQuery):
    """Start premium purchase flow"""
    uid = query.from_user.id
    
    if uid in active_sessions:
        return await query.answer("⚠️ You already have an active payment session", show_alert=True)
    
    active_sessions[uid] = {"step": "waiting_number"}
    
    await query.message.edit(
        """
🔢 **Enter a Number**

Just send a number (e.g., 7, 30, 365)

Then you can choose:
• Hours
• Days
• Months
• Years

💡 Example: `7` or `30` or `365`
""",
        reply_markup=cancel_btn()
    )
    
    try:
        msg = await client.listen(query.message.chat.id, filters=filters.user(uid), timeout=LISTEN_SHORT)
        
        if not msg.text:
            active_sessions.pop(uid, None)
            await query.message.edit(
                "❌ Please send a number\n\n💡 Example: `7` or `30`",
                reply_markup=buy_btn()
            )
            return
        
        # Extract number
        num_str = "".join(filter(str.isdigit, msg.text))
        if not num_str:
            active_sessions.pop(uid, None)
            await query.message.edit(
                "❌ Invalid number\n\nPlease send only numbers like: `7` or `30`",
                reply_markup=buy_btn()
            )
            return
        
        num = int(num_str)
        if num <= 0 or num > 9999:
            active_sessions.pop(uid, None)
            await query.message.edit(
                "❌ Invalid number (1-9999)\n\nPlease send a number between 1 and 9999",
                reply_markup=buy_btn()
            )
            return
        
        # Store number and show duration options
        active_sessions[uid] = {"step": "waiting_duration", "number": num}
        
        await query.message.edit(
            f"""
✅ Number: **{num}**

Now select your duration:
""",
            reply_markup=duration_buttons(num)
        )
    
    except asyncio.TimeoutError:
        active_sessions.pop(uid, None)
        return await query.message.edit("⏱️ Timeout! Payment cancelled.", reply_markup=buy_btn())
    except Exception as e:
        active_sessions.pop(uid, None)
        return await query.message.edit(
            f"❌ Error: {str(e)}\n\nPlease try again",
            reply_markup=buy_btn()
        )


@Client.on_callback_query(filters.regex("^dur#"))
async def duration_selected(client, query: CallbackQuery):
    """Handle duration selection"""
    uid = query.from_user.id
    
    if uid not in active_sessions:
        return await query.answer("⚠️ Session expired. Please start again.", show_alert=True)
    
    try:
        _, num_str, unit = query.data.split("#")
        num = int(num_str)
    except:
        return await query.answer("❌ Invalid data", show_alert=True)
    
    # Map units to display names
    unit_map = {
        "hour": "Hours",
        "day": "Days",
        "month": "Months",
        "year": "Years"
    }
    
    unit_display = unit_map.get(unit, unit)
    plan_text = f"{num} {unit_display}"
    
    # Calculate duration
    if unit == "hour":
        duration = timedelta(hours=num)
        days = max(1, (num // 24) or 1)
    elif unit == "day":
        duration = timedelta(days=num)
        days = num
    elif unit == "month":
        duration = timedelta(days=30 * num)
        days = 30 * num
    elif unit == "year":
        duration = timedelta(days=365 * num)
        days = 365 * num
    else:
        return await query.answer("❌ Invalid unit", show_alert=True)
    
    amount = days * PRE_DAY_AMOUNT
    
    # Update session
    active_sessions[uid] = {
        "step": "waiting_screenshot",
        "plan_text": plan_text,
        "amount": amount,
        "days": days
    }
    
    # Generate UPI QR code
    try:
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
        
        # Delete the duration selection message
        try:
            await query.message.delete()
        except:
            pass
        
    except Exception as e:
        active_sessions.pop(uid, None)
        return await query.answer(f"❌ Error: {str(e)}", show_alert=True)
    
    # Wait for screenshot
    try:
        receipt = await client.listen(
            query.message.chat.id, 
            filters=filters.user(uid) & filters.photo, 
            timeout=LISTEN_LONG
        )
        
        if not receipt.photo:
            active_sessions.pop(uid, None)
            await query.message.reply(
                "❌ Screenshot not received. Please send a photo.",
                reply_markup=buy_btn()
            )
            return
    
    except asyncio.TimeoutError:
        active_sessions.pop(uid, None)
        return await query.message.reply(
            "⏱️ Timeout! Screenshot not received. Payment cancelled.",
            reply_markup=buy_btn()
        )
    except Exception as e:
        active_sessions.pop(uid, None)
        return await query.message.reply(
            f"❌ Error: {str(e)}",
            reply_markup=buy_btn()
        )
    
    # Send to admin for approval
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok#{uid}#{plan_text}#{amount}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"pay_no#{uid}")
    ]])
    
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
        active_sessions.pop(uid, None)
        return await receipt.reply(
            f"❌ Error sending to admin: {str(e)}",
            reply_markup=buy_btn()
        )
    
    await receipt.reply("✅ **Screenshot received!**\n\n⏳ Your payment is being reviewed by admin.\nYou'll be notified once approved.")
    active_sessions.pop(uid, None)


@Client.on_callback_query(filters.regex("^cancel_payment$"))
async def cancel_payment(_, query: CallbackQuery):
    """Cancel payment flow"""
    active_sessions.pop(query.from_user.id, None)
    await query.message.edit("❌ Payment process cancelled", reply_markup=buy_btn())
    await query.answer("Cancelled", show_alert=False)


# ======================================================
# 🛂 ADMIN APPROVAL
# ======================================================

async def update_user_premium(uid, plan_txt, amount):
    """Helper to update user premium status"""
    duration = parse_duration(plan_txt)
    if not duration:
        return False
    
    now = datetime.utcnow()
    old = await db.get_plan(uid) or {}
    
    # Calculate days
    if duration.days == 0 and duration.seconds > 0:
        days = max(1, (duration.seconds // 3600) // 24 + 1)
        duration = timedelta(days=days)
    
    # Calculate expiry date
    expire = old.get("expire")
    if expire:
        expire_dt = get_expiry_datetime(expire)
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
    
    return expire_dt, invoice


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
    
    result = await update_user_premium(uid, plan_txt, amount)
    if not result:
        return await query.message.edit_caption(
            query.message.caption + "\n\n❌ **FAILED** - Invalid plan duration"
        )
    
    expire_dt, invoice = result
    
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
        query.message.caption + f"\n\n✅ **APPROVED** by @{query.from_user.username}\n⏰ {fmt(datetime.utcnow())}"
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
        query.message.caption + f"\n\n❌ **REJECTED** by @{query.from_user.username}\n⏰ {fmt(datetime.utcnow())}"
    )
    await query.answer("❌ Payment Rejected", show_alert=True)


# ======================================================
# 📊 ADMIN COMMANDS
# ======================================================

@Client.on_message(filters.command("premstats") & filters.user(ADMINS))
async def premium_stats(_, message):
    """Show premium statistics for admin"""
    users = await db.get_premium_users()
    now = datetime.utcnow()
    
    total = len(users)
    active = expired = total_revenue = 0
    expiring_soon = []
    
    for u in users:
        plan = u.get("plan", {})
        expire = plan.get("expire")
        
        if not expire:
            continue
        
        exp_dt = get_expiry_datetime(expire)
        
        if exp_dt > now:
            active += 1
            days_left = (exp_dt - now).days
            if days_left <= 7:
                uid = u.get("_id") or u.get("id")
                expiring_soon.append(f"• User {uid}: {days_left} days left")
        else:
            expired += 1
        
        # Calculate revenue
        for inv in plan.get("invoices", []):
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


@Client.on_message(filters.command("givepremium") & filters.user(ADMINS))
async def give_premium_cmd(client, message):
    """Admin manually gives premium to a user"""
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return await message.reply("Usage: `/givepremium user_id duration`\nExample: `/givepremium 123456789 30 days`")
        
        uid = int(parts[1])
        duration_text = parts[2]
        
        result = await update_user_premium(uid, f"{duration_text} (Admin Gift)", 0)
        if not result:
            return await message.reply("❌ Invalid duration format")
        
        expire_dt, _ = result
        
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
        
        await db.update_plan(uid, {"premium": False, "plan": None, "expire": None})
        
        await message.reply(f"✅ Premium removed from user {uid}")
        
        try:
            await client.send_message(uid, "⚠️ Your premium access has been revoked by admin.")
        except:
            pass
    
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
