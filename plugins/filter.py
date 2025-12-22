import asyncio
from math import ceil

from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import get_size, is_premium, temp

RESULTS_PER_PAGE = 10
RESULT_EXPIRE_TIME = 300  # 5 minutes


# =====================================================
# 📩 MESSAGE HANDLER
# =====================================================
@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(client, message):
    if message.text.startswith("/"):
        return

    user_id = message.from_user.id
    search = message.text.strip().lower()

    if len(search) < 2:
        return

    # ---------- GROUP SEARCH ----------
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        stg = await db.get_settings(message.chat.id)
        if stg.get("search") is False:
            return

        source_chat_id = message.chat.id
        source_chat_title = message.chat.title

    # ---------- PM SEARCH ----------
    else:
        source_chat_id = 0
        source_chat_title = ""

        if user_id not in ADMINS:
            bot_stg = db.get_bot_sttgs()
            if not bot_stg.get("PM_SEARCH", True):
                if not await is_premium(user_id, client):
                    return

    await send_results(
        client=client,
        user_id=user_id,
        search=search,
        offset=0,
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title
    )


# =====================================================
# 🔎 SEND / EDIT RESULTS
# =====================================================
async def send_results(
    client,
    user_id,
    search,
    offset,
    source_chat_id,
    source_chat_title,
    message=None
):
    files, next_offset, total = await get_search_results(
        search,
        offset=offset,
        max_results=RESULTS_PER_PAGE
    )

    if not files:
        text = f"❌ <b>No results found for:</b>\n<code>{search}</code>"
        if message:
            return await message.edit_text(text, parse_mode=enums.ParseMode.HTML)
        return await client.send_message(user_id, text, parse_mode=enums.ParseMode.HTML)

    # -------- PAGE INFO --------
    page = (offset // RESULTS_PER_PAGE) + 1
    total_pages = ceil(total / RESULTS_PER_PAGE)

    start = offset + 1
    end = offset + len(files)

    # -------- HEADER --------
    text = (
        f"🔎 <b>Search :</b> <code>{search}</code>\n"
        f"🎬 <b>Total Files :</b> <code>{total}</code>\n"
        f"📄 <b>Page :</b> <code>{page} / {total_pages}</code>\n\n"
    )

    # -------- FILE LIST (LINE GAP FIX) --------
    for f in files:
        size = get_size(f["file_size"])
        link = f"https://t.me/{temp.U_NAME}?start=file_{source_chat_id}_{f['_id']}"
        text += f"📁 <a href='{link}'>[{size}] {f['file_name']}</a>\n\n"

    text += f"<b>Showing :</b> {start}-{end}"

    if source_chat_title:
        text += f"\n\n<b>Powered By :</b> {source_chat_title}"

    # -------- BUTTONS (OWNER BOUND) --------
    buttons = []
    nav = []

    owner = user_id

    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Prev",
                callback_data=f"page#{search}#{offset-RESULTS_PER_PAGE}#{source_chat_id}#{owner}"
            )
        )
    else:
        nav.append(InlineKeyboardButton("⛔ Prev", callback_data="pages"))

    if next_offset:
        nav.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"page#{search}#{offset+RESULTS_PER_PAGE}#{source_chat_id}#{owner}"
            )
        )
    else:
        nav.append(InlineKeyboardButton("Next ⛔", callback_data="pages"))

    buttons.append(nav)
    markup = InlineKeyboardMarkup(buttons)

    # -------- SEND / EDIT --------
    if message:
        await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        msg = await client.send_message(
            user_id,
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(auto_expire(msg))


# =====================================================
# 🔁 PAGINATION CALLBACK (OWNER VALIDATION)
# =====================================================
@Client.on_callback_query(filters.regex("^page#"))
async def pagination_handler(client, query):
    _, search, offset, source_chat_id, owner = query.data.split("#")

    offset = int(offset)
    source_chat_id = int(source_chat_id)
    owner = int(owner)

    # 🔐 OWNER CHECK
    if query.from_user.id != owner and query.from_user.id not in ADMINS:
        return await query.answer(
            "❌ This result is not for you",
            show_alert=True
        )

    if source_chat_id:
        try:
            chat = await client.get_chat(source_chat_id)
            source_chat_title = chat.title
        except:
            source_chat_title = ""
    else:
        source_chat_title = ""

    await query.answer()

    await send_results(
        client=client,
        user_id=owner,
        search=search,
        offset=offset,
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title,
        message=query.message
    )


# =====================================================
# ⏱ AUTO EXPIRE RESULTS
# =====================================================
async def auto_expire(message):
    await asyncio.sleep(RESULT_EXPIRE_TIME)
    try:
        await message.edit_reply_markup(None)
        await message.reply("⌛ <i>This result has expired.</i>")
    except:
        pass
