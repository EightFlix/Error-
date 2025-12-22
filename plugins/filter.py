import asyncio
from math import ceil

from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, UPI_ID, UPI_NAME
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import (
    get_size,
    is_premium,
    temp,
    learn_keywords,
    suggest_query,
    get_lang
)

RESULTS_PER_PAGE = 10
RESULT_EXPIRE_TIME = 300     # 5 minutes
EXPIRE_DELETE_DELAY = 60     # delete expired message after 1 min


# =====================================================
# 📩 MESSAGE HANDLER
# =====================================================
@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(client, message):
    if message.text.startswith("/"):
        return

    user_id = message.from_user.id
    raw_search = message.text.strip().lower()

    if len(raw_search) < 2:
        return

    # 🔥 auto-learn keywords (RAM only, ultra fast)
    learn_keywords(raw_search)

    # ==============================
    # 🌍 LANGUAGE DETECT
    # ==============================
    lang = get_lang(
        user_id=user_id,
        group_id=message.chat.id if message.chat.type != enums.ChatType.PRIVATE else None
    )

    # ==============================
    # 🚫 GROUP SEARCH (STRICT)
    # ==============================
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        stg = await db.get_settings(message.chat.id)
        if not stg or stg.get("search") is False:
            return

        chat_id = message.chat.id
        source_chat_id = message.chat.id
        source_chat_title = message.chat.title

    # ==============================
    # 📩 PM SEARCH (PREMIUM ONLY)
    # ==============================
    else:
        chat_id = user_id
        source_chat_id = 0
        source_chat_title = ""

        if user_id not in ADMINS:
            if not await is_premium(user_id, client):
                text = (
                    "🔒 <b>Premium Required</b>\n\n"
                    "This feature is for premium users only.\n"
                    "Upgrade now to unlock unlimited search."
                    if lang == "en"
                    else
                    "🔒 <b>प्रीमियम आवश्यक है</b>\n\n"
                    "यह सुविधा केवल प्रीमियम यूज़र्स के लिए है।\n"
                    "अनलिमिटेड सर्च के लिए अभी अपग्रेड करें।"
                )

                btn = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton(
                            "💳 Renew via UPI",
                            url=f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&cu=INR"
                        )
                    ]]
                )
                return await client.send_message(chat_id, text, reply_markup=btn)

    # 🔥 smart normalize (multi-word safe)
    search = " ".join(raw_search.split())

    await send_results(
        client=client,
        chat_id=chat_id,
        owner=user_id,
        search=search,
        offset=0,
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title,
        lang=lang
    )


# =====================================================
# 🔎 SEND / EDIT RESULTS
# =====================================================
async def send_results(
    client,
    chat_id,
    owner,
    search,
    offset,
    source_chat_id,
    source_chat_title,
    lang,
    message=None,
    tried_fallback=False
):
    files, next_offset, total = await get_search_results(
        search,
        offset=offset,
        max_results=RESULTS_PER_PAGE
    )

    # ==============================
    # 🧠 SMART FALLBACK (AI-LIKE)
    # ==============================
    if not files and not tried_fallback:
        alt = suggest_query(search)
        if alt and alt != search:
            return await send_results(
                client,
                chat_id,
                owner,
                alt,
                0,
                source_chat_id,
                source_chat_title,
                lang,
                message,
                True
            )

    if not files:
        text = (
            f"❌ <b>No results found for:</b>\n<code>{search}</code>"
            if lang == "en"
            else
            f"❌ <b>कोई रिज़ल्ट नहीं मिला:</b>\n<code>{search}</code>"
        )
        if message:
            return await message.edit_text(text, parse_mode=enums.ParseMode.HTML)
        return await client.send_message(chat_id, text, parse_mode=enums.ParseMode.HTML)

    # ==============================
    # 📄 PAGE INFO
    # ==============================
    page = (offset // RESULTS_PER_PAGE) + 1
    total_pages = ceil(total / RESULTS_PER_PAGE)

    crown = "👑 " if await is_premium(owner, client) else ""

    text = (
        f"{crown}🔎 <b>Search :</b> <code>{search}</code>\n"
        f"🎬 <b>Total Files :</b> <code>{total}</code>\n"
        f"📄 <b>Page :</b> <code>{page} / {total_pages}</code>\n\n"
        if lang == "en"
        else
        f"{crown}🔎 <b>खोज :</b> <code>{search}</code>\n"
        f"🎬 <b>कुल फ़ाइलें :</b> <code>{total}</code>\n"
        f"📄 <b>पेज :</b> <code>{page} / {total_pages}</code>\n\n"
    )

    # -------- FILE LIST --------
    for f in files:
        size = get_size(f["file_size"])
        link = f"https://t.me/{temp.U_NAME}?start=file_{source_chat_id}_{f['_id']}"
        text += f"📁 <a href='{link}'>[{size}] {f['file_name']}</a>\n\n"

    if source_chat_title:
        text += (
            f"<b>Powered By :</b> {source_chat_title}"
            if lang == "en"
            else
            f"<b>प्रस्तुतकर्ता :</b> {source_chat_title}"
        )

    # -------- PAGINATION --------
    nav = []

    if offset > 0:
        nav.append(
            InlineKeyboardButton(
                "◀️ Prev" if lang == "en" else "◀️ पिछला",
                callback_data=f"page#{search}#{offset-RESULTS_PER_PAGE}#{source_chat_id}#{owner}"
            )
        )

    if next_offset:
        nav.append(
            InlineKeyboardButton(
                "Next ▶️" if lang == "en" else "अगला ▶️",
                callback_data=f"page#{search}#{offset+RESULTS_PER_PAGE}#{source_chat_id}#{owner}"
            )
        )

    markup = InlineKeyboardMarkup([nav]) if nav else None

    if message:
        await message.edit_text(
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    else:
        msg = await client.send_message(
            chat_id,
            text,
            reply_markup=markup,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
        asyncio.create_task(auto_expire(msg))


# =====================================================
# 🔁 PAGINATION CALLBACK (OWNER ONLY)
# =====================================================
@Client.on_callback_query(filters.regex("^page#"))
async def pagination_handler(client, query):
    _, search, offset, source_chat_id, owner = query.data.split("#")

    offset = int(offset)
    source_chat_id = int(source_chat_id)
    owner = int(owner)

    if query.from_user.id != owner and query.from_user.id not in ADMINS:
        return await query.answer("❌ Not your result", show_alert=True)

    lang = get_lang(query.from_user.id, query.message.chat.id)

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
        client,
        query.message.chat.id,
        owner,
        search,
        offset,
        source_chat_id,
        source_chat_title,
        lang,
        query.message
    )


# =====================================================
# ⏱ AUTO EXPIRE (HARD DELETE)
# =====================================================
async def auto_expire(message):
    await asyncio.sleep(RESULT_EXPIRE_TIME)

    try:
        await message.edit_reply_markup(None)
        await message.edit_text("⌛ <i>This result has expired.</i>")
    except:
        return

    await asyncio.sleep(EXPIRE_DELETE_DELAY)
    try:
        await message.delete()
    except:
        pass
