from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils import temp, get_wish
from database.users_chats_db import db


# ======================================================
# 🚀 NORMAL /START HANDLER (NO FILE DELIVERY)
# ======================================================

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user = message.from_user

    # ---- save user safely ----
    try:
        if not await db.is_user_exist(user.id):
            await db.add_user(user.id, user.first_name)
    except:
        pass

    text = (
        f"👋 <b>Hello {user.mention}</b>\n\n"
        f"{get_wish()}\n\n"
        "🔍 <b>Send Movie / Series name to search</b>\n"
        "📂 Files will be delivered in private\n\n"
        "➕ You can also add me to your group 👇"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Add Me To Group",
                    url=f"https://t.me/{temp.U_NAME}?startgroup=true"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Updates",
                    url="https://t.me/YourUpdatesChannel"  # optional
                )
            ]
        ]
    )

    await message.reply(
        text,
        reply_markup=buttons,
        disable_web_page_preview=True
    )
