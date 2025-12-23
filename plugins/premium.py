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
# 🔧 CONFIG (Koyeb Optimized)  
# ======================================================  
  
REMINDER_STEPS = [  
    ("12h", timedelta(hours=12)),  
    ("6h", timedelta(hours=6)),  
    ("3h", timedelta(hours=3)),  
    ("1h", timedelta(hours=1)),  
    ("10m", timedelta(minutes=10)),  
]  
  
# Timeout settings for Koyeb  
LISTEN_TIMEOUT_SHORT = 180  # 3 min  
LISTEN_TIMEOUT_LONG = 300   # 5 min  
  
# Active payment sessions tracking  
active_sessions = {}  
  
  
# ======================================================  
# 🧠 HELPERS  
# ======================================================  
  
def fmt(dt) -> str:  
    """Format datetime to readable string"""  
    try:  
        if isinstance(dt, (int, float)):  
            dt = datetime.utcfromtimestamp(dt)  
        return dt.strftime("%d %b %Y, %I:%M %p")  
    except Exception as e:  
        print(f"[KOYEB] Date format error: {e}")  
        return "N/A"  
  
  
def parse_duration(text: str):  
    """Parse duration text to timedelta"""  
    try:  
        if not text:  
            return None  
  
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
    except Exception as e:  
        print(f"[KOYEB] Duration parse error: {e}")  
        return None  
  
  
def gen_invoice_id():  
    """Generate unique invoice ID"""  
    try:  
        return "PRM-" + secrets.token_hex(3).upper()  
    except:  
        # Fallback if secrets fails  
        import random  
        import string  
        return "PRM-" + "".join(random.choices(string.hexdigits.upper(), k=6))  
  
  
def buy_button():  
    """Generate buy premium button"""  
    return InlineKeyboardMarkup(  
        [[InlineKeyboardButton("💰 Buy / Renew Premium", callback_data="buy_premium")]]  
    )  
  
  
def cancel_button():  
    """Generate cancel button"""  
    return InlineKeyboardMarkup(  
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")]]  
    )  
  
  
# ======================================================  
# 👤 USER COMMANDS (Koyeb Optimized)  
# ======================================================  
  
@Client.on_message(filters.command("plan") & filters.private)  
async def plan_cmd(client, message):  
    """Show premium plan details"""  
    try:  
        if not IS_PREMIUM:  
            return await message.reply("⚠️ Premium system is disabled.")  
  
        user_id = message.from_user.id  
          
        if user_id in ADMINS:  
            return await message.reply("👑 Admin = Lifetime Premium")  
  
        # Check if already premium  
        if await is_premium(user_id, client):  
            return await message.reply(  
                "✅ Premium already active.\nUse /myplan to see details",  
                reply_markup=InlineKeyboardMarkup([[  
                    InlineKeyboardButton("🔄 Renew Premium", callback_data="buy_premium")  
                ]])  
            )  
  
        await message.reply(  
            "💎 **Premium Benefits**\n\n"  
            "🚀 Faster search results\n"  
            "📩 PM Search access\n"  
            "🔕 No advertisements\n"  
            "⚡ Instant file access\n"  
            "🎯 Priority support\n"  
            "🔥 Unlimited searches\n\n"  
            f"💰 **Price:** ₹{PRE_DAY_AMOUNT}/day\n",  
            reply_markup=buy_button()  
        )  
    except Exception as e:  
        print(f"[KOYEB] Plan command error: {e}")  
        await message.reply("❌ Error loading plan. Try again.")  
  
  
@Client.on_message(filters.command("myplan") & filters.private)  
async def myplan_cmd(client, message):  
    """Show user's current plan"""  
    try:  
        user_id = message.from_user.id  
          
        if user_id in ADMINS:  
            return await message.reply(  
                "👑 **Admin Status**\n\n"  
                "Plan: Lifetime Premium\n"  
                "Expiry: Never"  
            )  
  
        plan = db.get_plan(user_id)  
        if not plan or not plan.get("premium"):  
            return await message.reply(  
                "❌ No active premium plan.\n\n"  
                "Get premium now!",  
                reply_markup=buy_button()  
            )  
  
        expire = plan.get('expire')  
        if expire:  
            if isinstance(expire, (int, float)):  
                expire_dt = datetime.utcfromtimestamp(expire)  
            else:  
                expire_dt = expire  
              
            remaining = expire_dt - datetime.utcnow()  
            days_left = max(0, remaining.days)  
            hours_left = max(0, remaining.seconds // 3600)  
              
            time_left = f"{days_left} days, {hours_left} hours" if days_left > 0 else f"{hours_left} hours"  
        else:  
            time_left = "Unknown"  
  
        await message.reply(  
            "🎉 **Premium Active**\n\n"  
            f"💎 Plan: {plan.get('plan', 'N/A')}\n"  
            f"⏰ Valid Till: {fmt(expire)}\n"  
            f"⏳ Time Left: {time_left}\n",  
            reply_markup=InlineKeyboardMarkup([[  
                InlineKeyboardButton("🔄 Renew", callback_data="buy_premium"),  
                InlineKeyboardButton("🧾 Invoices", callback_data="show_invoices")  
            ]])  
        )  
    except Exception as e:  
        print(f"[KOYEB] MyPlan error: {e}")  
        await message.reply("❌ Error loading plan details.")  
  
  
# ======================================================  
# 🧾 INVOICE / HISTORY (Koyeb Optimized)  
# ======================================================  
  
@Client.on_message(filters.command("invoice") & filters.private)  
async def invoice_cmd(client, message):  
    """Show invoice history"""  
    try:  
        plan = db.get_plan(message.from_user.id) or {}  
        invoices = plan.get("invoices", [])  
  
        if not invoices:  
            return await message.reply("❌ No invoices found.")  
  
        # Check if history requested  
        show_all = len(message.command) > 1 and message.command[1] == "history"  
  
        if show_all:  
            text = "🧾 **Invoice History**\n\n"  
            for inv in invoices[-10:][::-1]:  # Last 10 invoices  
                text += (  
                    f"• `{inv.get('id', 'N/A')}` | "  
                    f"₹{inv.get('amount', 0)} | "  
                    f"{inv.get('plan', 'N/A')}\n"  
                )  
            return await message.reply(text)  
  
        # Show latest invoice  
        inv = invoices[-1]  
        await message.reply(  
            "🧾 **Latest Invoice**\n\n"  
            f"🆔 ID: `{inv.get('id', 'N/A')}`\n"  
            f"💎 Plan: {inv.get('plan', 'N/A')}\n"  
            f"💰 Amount: ₹{inv.get('amount', 0)}\n"  
            f"📅 Activated: {inv.get('activated', 'N/A')}\n"  
            f"⏰ Expires: {inv.get('expire', 'N/A')}"  
        )  
    except Exception as e:  
        print(f"[KOYEB] Invoice error: {e}")  
        await message.reply("❌ Error loading invoices.")  
  
  
@Client.on_callback_query(filters.regex("^show_invoices$"))  
async def show_invoices_cb(client, query: CallbackQuery):  
    """Show invoice history via callback"""  
    try:  
        plan = db.get_plan(query.from_user.id) or {}  
        invoices = plan.get("invoices", [])  
  
        if not invoices:  
            return await query.answer("No invoices found", show_alert=True)  
  
        text = "🧾 **Invoice History**\n\n"  
        for inv in invoices[-10:][::-1]:  
            text += (  
                f"• `{inv.get('id', 'N/A')}` | "  
                f"₹{inv.get('amount', 0)} | "  
                f"{inv.get('plan', 'N/A')}\n"  
            )  
          
        await query.message.edit(text)  
    except Exception as e:  
        print(f"[KOYEB] Show invoices error: {e}")  
        await query.answer("Error loading invoices", show_alert=True)  
  
  
# ======================================================  
# 💰 BUY / RENEW FLOW (Koyeb Optimized)  
# ======================================================  
  
@Client.on_callback_query(filters.regex("^buy_premium$"))  
async def buy_premium(client, query: CallbackQuery):  
    """Start premium purchase flow"""  
    try:  
        user_id = query.from_user.id  
        chat_id = query.message.chat.id  
          
        # Check if already in a session  
        if user_id in active_sessions:  
            return await query.answer(  
                "⚠️ Already in payment process. Complete or cancel first.",  
                show_alert=True  
            )  
          
        # Mark session as active  
        active_sessions[user_id] = True  
          
        await query.message.edit(  
            "⏳ **Select Duration**\n\n"  
            "Send duration like:\n"  
            "`1 day`\n"  
            "`7 days`\n"  
            "`1 month`\n"  
            "`3 months`\n"  
            "`6 months`\n"  
            "`1 year`\n\n"  
            "⏰ You have 3 minutes to respond.",  
            reply_markup=cancel_button()  
        )  
  
        try:  
            msg = await client.listen(  
                chat_id=chat_id,  
                user_id=user_id,  
                timeout=LISTEN_TIMEOUT_SHORT  
            )  
              
            if not msg or not msg.text:  
                raise ValueError("Invalid input")  
              
            duration = parse_duration(msg.text)  
            if not duration:  
                raise ValueError("Invalid duration")  
                  
        except ListenerTimeout:  
            active_sessions.pop(user_id, None)  
            return await query.message.reply("❌ Timeout. Use /plan to try again.")  
        except Exception as e:  
            active_sessions.pop(user_id, None)  
            print(f"[KOYEB] Duration input error: {e}")  
            return await query.message.reply("❌ Invalid duration. Use /plan to try again.")  
  
        # Calculate amount  
        days = max(1, duration.days)  
        amount = days * PRE_DAY_AMOUNT  
  
        # Generate QR code  
        try:  
            upi = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"  
            qr = qrcode.QRCode(box_size=10, border=4)  
            qr.add_data(upi)  
            qr.make(fit=True)  
              
            img = qr.make_image(fill_color="black", back_color="white")  
            bio = BytesIO()  
            bio.name = "qr.png"  
            img.save(bio, "PNG")  
            bio.seek(0)  
        except Exception as e:  
            active_sessions.pop(user_id, None)  
            print(f"[KOYEB] QR generation error: {e}")  
            return await query.message.reply("❌ Error generating QR. Try again.")  
  
        await query.message.reply_photo(  
            bio,  
            caption=(  
                "💰 **Payment Details**\n\n"  
                f"📦 Plan: {msg.text}\n"  
                f"💵 Amount: ₹{amount}\n"  
                f"💳 UPI ID: `{UPI_ID}`\n\n"  
                "📸 Send payment screenshot after paying.\n"  
                "⏰ You have 5 minutes.\n\n"  
                "⚠️ Send only photo/screenshot!"  
            ),  
            reply_markup=cancel_button()  
        )  
  
        # Wait for screenshot  
        try:  
            receipt = await client.listen(  
                chat_id=chat_id,  
                user_id=user_id,  
                timeout=LISTEN_TIMEOUT_LONG  
            )  
              
            if not receipt.photo:  
                raise ValueError("No photo received")  
                  
        except ListenerTimeout:  
            active_sessions.pop(user_id, None)  
            return await query.message.reply(  
                "❌ Screenshot not received in time.\n"  
                "Use /plan to try again."  
            )  
        except Exception as e:  
            active_sessions.pop(user_id, None)  
            print(f"[KOYEB] Receipt error: {e}")  
            return await query.message.reply(  
                "❌ Invalid screenshot.\n"  
                "Use /plan to try again."  
            )  
  
        # Send to admin for approval  
        try:  
            buttons = InlineKeyboardMarkup([  
                [  
                    InlineKeyboardButton(  
                        "✅ Approve",  
                        callback_data=f"pay_ok#{user_id}#{msg.text}#{amount}"  
                    ),  
                    InlineKeyboardButton(  
                        "❌ Reject",  
                        callback_data=f"pay_no#{user_id}"  
                    )  
                ]  
            ])  
  
            await client.send_photo(  
                RECEIPT_SEND_USERNAME,  
                receipt.photo.file_id,  
                caption=(  
                    "#PremiumPayment\n\n"  
                    f"👤 User ID: `{user_id}`\n"  
                    f"👤 Name: {query.from_user.first_name}\n"  
                    f"📦 Plan: {msg.text}\n"  
                    f"💰 Amount: ₹{amount}\n"  
                    f"📅 Date: {datetime.utcnow().strftime('%d-%m-%Y %H:%M')}"  
                ),  
                reply_markup=buttons  
            )  
  
            await receipt.reply(  
                "✅ **Screenshot Received**\n\n"  
                "Your payment is under review.\n"  
                "You'll be notified once approved.\n\n"  
                "⏰ Usually takes 5-30 minutes."  
            )  
              
        except FloodWait as e:  
            await asyncio.sleep(e.value)  
        except Exception as e:  
            print(f"[KOYEB] Admin send error: {e}")  
            await query.message.reply(  
                "⚠️ Error sending to admin. Please contact support."  
            )  
        finally:  
            active_sessions.pop(user_id, None)  
              
    except Exception as e:  
        active_sessions.pop(user_id, None)  
        print(f"[KOYEB] Buy premium error: {e}")  
        await query.message.reply("❌ Error processing payment. Try again.")  
  
  
@Client.on_callback_query(filters.regex("^cancel_payment$"))  
async def cancel_payment(client, query: CallbackQuery):  
    """Cancel active payment session"""  
    try:  
        user_id = query.from_user.id  
        active_sessions.pop(user_id, None)  
          
        await query.message.edit(  
            "❌ Payment cancelled.\n\n"  
            "Use /plan to start again."  
        )  
    except Exception as e:  
        print(f"[KOYEB] Cancel error: {e}")  
  
  
# ======================================================  
# 🛂 ADMIN APPROVAL (Koyeb Optimized)  
# ======================================================  
  
@Client.on_callback_query(filters.regex("^pay_ok#"))  
async def admin_approve(client, query: CallbackQuery):  
    """Admin approves payment"""  
    try:  
        if query.from_user.id not in ADMINS:  
            return await query.answer("⛔ Not authorized", show_alert=True)  
  
        parts = query.data.split("#")  
        if len(parts) != 4:  
            return await query.message.edit("❌ Invalid callback data.")  
          
        _, uid, plan_txt, amount = parts  
        uid = int(uid)  
        amount = int(amount)  
  
        duration = parse_duration(plan_txt)  
        if not duration:  
            return await query.message.edit("❌ Invalid plan duration.")  
  
        now = datetime.utcnow()  
          
        # Check existing plan for renewal  
        old_plan = db.get_plan(uid) or {}  
        current_expire = old_plan.get("expire")  
          
        if current_expire:  
            if isinstance(current_expire, (int, float)):  
                current_expire = datetime.utcfromtimestamp(current_expire)  
              
            # If still active, extend from current expiry  
            if current_expire > now:  
                expire = current_expire + duration  
            else:  
                expire = now + duration  
        else:  
            expire = now + duration  
  
        # Generate invoice  
        invoice = {  
            "id": gen_invoice_id(),  
            "plan": plan_txt,  
            "amount": amount,  
            "activated": fmt(now),  
            "expire": fmt(expire),  
            "created_at": now.timestamp()  
        }  
  
        invoices = old_plan.get("invoices", [])  
        invoices.append(invoice)  
  
        # Update plan  
        db.update_plan(uid, {  
            "premium": True,  
            "plan": plan_txt,  
            "expire": expire,  
            "activated_at": now.timestamp(),  
            "invoices": invoices,  
            "last_reminder": None  
        })  
  
        # Notify user  
        try:  
            await client.send_message(  
                uid,  
                "🎉 **Premium Activated!**\n\n"  
                f"💎 Plan: {plan_txt}\n"  
                f"💰 Amount: ₹{amount}\n"  
                f"📅 Activated: {fmt(now)}\n"  
                f"⏰ Valid Till: {fmt(expire)}\n\n"  
                "Thank you for your purchase! 🙏"  
            )  
        except FloodWait as e:  
            await asyncio.sleep(e.value)  
        except Exception as e:  
            print(f"[KOYEB] User notify error: {e}")  
  
        await query.message.edit(  
            f"✅ **Premium Approved**\n\n"  
            f"User: `{uid}`\n"  
            f"Plan: {plan_txt}\n"  
            f"Amount: ₹{amount}"  
        )  
        await query.answer("✅ Premium activated!", show_alert=True)  
          
    except Exception as e:  
        print(f"[KOYEB] Approve error: {e}")  
        await query.answer("❌ Error approving payment", show_alert=True)  
  
  
@Client.on_callback_query(filters.regex("^pay_no#"))  
async def admin_reject(client, query: CallbackQuery):  
    """Admin rejects payment"""  
    try:  
        if query.from_user.id not in ADMINS:  
            return await query.answer("⛔ Not authorized", show_alert=True)  
  
        parts = query.data.split("#")  
        if len(parts) < 2:  
            return await query.message.edit("❌ Invalid callback data.")  
          
        uid = int(parts[1])  
  
        # Notify user  
        try:  
            await client.send_message(  
                uid,  
                "❌ **Payment Rejected**\n\n"  
                "Your payment screenshot was not approved.\n"  
                "Possible reasons:\n"  
                "• Invalid screenshot\n"  
                "• Amount mismatch\n"  
                "• Duplicate payment\n\n"  
                "If you have paid, please contact admin with:\n"  
                "• Transaction ID\n"  
                "• Payment time\n"  
                "• Amount"  
            )  
        except FloodWait as e:  
            await asyncio.sleep(e.value)  
        except Exception as e:  
            print(f"[KOYEB] Reject notify error: {e}")  
  
        await query.message.edit(  
            f"❌ **Payment Rejected**\n\n"  
            f"User: `{uid}`"  
        )  
        await query.answer("Payment rejected", show_alert=True)  
          
    except Exception as e:  
        print(f"[KOYEB] Reject error: {e}")  
        await query.answer("❌ Error rejecting payment", show_alert=True)  
  
  
# ======================================================  
# 🔧 ADMIN TOOLS (Koyeb Optimized)  
# ======================================================  
  
@Client.on_message(filters.command("addpremium") & filters.user(ADMINS) & filters.private)  
async def add_premium_manual(client, message):  
    """Manually add premium to user"""  
    try:  
        if len(message.command) < 3:  
            return await message.reply(  
                "**Usage:**\n"  
                "`/addpremium <user_id> <duration>`\n\n"  
                "Example: `/addpremium 123456789 30 days`"  
            )  
          
        uid = int(message.command[1])  
        duration_text = " ".join(message.command[2:])  
          
        duration = parse_duration(duration_text)  
        if not duration:  
            return await message.reply("❌ Invalid duration format.")  
          
        now = datetime.utcnow()  
        expire = now + duration  
          
        invoice = {  
            "id": gen_invoice_id(),  
            "plan": duration_text,  
            "amount": 0,  
            "activated": fmt(now),  
            "expire": fmt(expire),  
            "created_at": now.timestamp(),  
            "note": "Manual activation by admin"  
        }  
          
        old_plan = db.get_plan(uid) or {}  
        invoices = old_plan.get("invoices", [])  
        invoices.append(invoice)  
          
        db.update_plan(uid, {  
            "premium": True,  
            "plan": duration_text,  
            "expire": expire,  
            "activated_at": now.timestamp(),  
            "invoices": invoices,  
            "last_reminder": None  
        })  
          
        try:  
            await client.send_message(  
                uid,  
                "🎁 **Premium Gifted!**\n\n"  
                f"You've been given premium access!\n"  
                f"💎 Plan: {duration_text}\n"  
                f"⏰ Valid Till: {fmt(expire)}\n\n"  
                "Enjoy premium features! 🎉"  
            )  
        except:  
            pass  
          
        await message.reply(  
            f"✅ **Premium Added**\n\n"  
            f"User: `{uid}`\n"  
            f"Duration: {duration_text}\n"  
            f"Expires: {fmt(expire)}"  
        )  
          
    except Exception as e:  
        print(f"[KOYEB] Manual premium error: {e}")  
        await message.reply(f"❌ Error: {str(e)}")
