from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils import temp, get_wish


@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    # -------- FILE DELIVERY --------
    if len(message.command) > 1 and message.command[1].startswith("file_"):
        return  # ⛔ file_deliver.py handle करेगा

    # -------- NORMAL START --------
    await message.reply(
        text=(
            f"👋 Hello {message.from_user.mention}\n\n"
            f"{get_wish()}\n\n"
            "🔍 Send me any movie / series name to search."
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "+ Add Me To Group +",
                        url=f"https://t.me/{temp.U_NAME}?startgroup=true"
                    )
                ]
            ]
        )
    )
