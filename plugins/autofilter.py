import re
import math
import time
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from info import ADMINS, MAX_BTN, SPELL_CHECK, script, PROTECT_CONTENT
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import get_settings, get_size, is_premium, get_shortlink, get_readable_time, temp
from .metadata import get_imdb_metadata, get_file_list_string, send_metadata_reply

# इन-मेमोरी स्टोरेज
BUTTONS = {}

@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(client, message):
    if message.text.startswith("/"):
        return
    
    user_id = message.from_user.id
    is_prm = await is_premium(user_id, client)
    
    if message.chat.type == enums.ChatType.PRIVATE:
        if user_id not in ADMINS and not is_prm:
            pm_search_all = await db.get_config('PM_SEARCH_FOR_ALL')
            if not pm_search_all:
                return await message.reply_text("<b>❌ ᴘᴍ sᴇᴀʀᴄʜ ᴅɪsᴀʙʟᴇᴅ</b>\n\nप्रीमियम यूजर्स ही PM में सर्च कर सकते हैं।")

    search = re.sub(r"\s+", " ", re.sub(r"[-:\"';!]", " ", message.text)).strip()
    if not search: return

    reply_msg = await message.reply_text(f"<b><i>🔍 `{search}` सर्च किया जा रहा है...</i></b>")
    await auto_filter(client, message, reply_msg, search)

async def auto_filter(client, message, reply_msg, search, offset=0, is_edit=False):
    settings = await get_settings(message.chat.id)
    files, n_offset, total = await get_search_results(search, offset=offset)

    if not files:
        if settings["spell_check"]:
            return await suggest_spelling(message, reply_msg, search)
        else:
            if is_edit: return await reply_msg.answer("कोई और फाइल नहीं मिली।", show_alert=True)
            return await reply_msg.edit(f"क्षमा करें, `{search}` नहीं मिला।")

    req = message.from_user.id if message.from_user else 0
    is_prm = await is_premium(req, client)
    
    msg_id = message.id if not is_edit else message.reply_to_message.id
    key = f"{req}_{msg_id}"
    BUTTONS[key] = search

    btn = []
    files_link = ""

    if settings['links']:
        files_link = get_file_list_string(files, message.chat.id)
    
    if not settings['links']:
        for file in files:
            if is_prm:
                btn.append([InlineKeyboardButton(f"[{get_size(file['file_size'])}] {file['file_name']}", callback_data=f"file#{file['_id']}")])
            else:
                f_link = await get_shortlink(settings['url'], settings['api'], f"https://t.me/{temp.U_NAME}?start=file_{message.chat.id}_{file['_id']}")
                btn.append([InlineKeyboardButton(f"⚡ [{get_size(file['file_size'])}] {file['file_name']}", url=f_link)])

    pagination_row = []
    if offset != 0:
        pagination_row.append(InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{int(offset)-MAX_BTN}"))
    pagination_row.append(InlineKeyboardButton(f"{math.ceil(int(offset) / MAX_BTN) + 1}/{math.ceil(int(total) / MAX_BTN)}", callback_data="pages"))
    if n_offset != "":
        pagination_row.append(InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{n_offset}"))
    
    btn.append(pagination_row)
    btn.insert(0, [
        InlineKeyboardButton("🌐 ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}#{req}#{offset}"),
        InlineKeyboardButton("🔍 ǫᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}#{req}#{offset}")
    ])

    if not is_prm:
        btn.append([InlineKeyboardButton('🤑 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ (ɴᴏ ʟɪɴᴋs)', url=f"https://t.me/{temp.U_NAME}?start=premium")])

    cap, poster = await get_imdb_metadata(search, files, settings)
    
    if is_edit:
        try:
            if poster and poster != "https://telegra.ph/file/default_poster.jpg":
                await reply_msg.edit_media(media=InputMediaPhoto(poster, caption=cap), reply_markup=InlineKeyboardMarkup(btn))
            else:
                await reply_msg.edit_text(text=cap, reply_markup=InlineKeyboardMarkup(btn))
        except: pass
    else:
        await send_metadata_reply(message, cap, poster, InlineKeyboardMarkup(btn), settings, files_link)
        await reply_msg.delete()

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page_handler(bot, query: CallbackQuery):
    data = query.data.split("_")
    try:
        req = int(data[1])
        key = data[2]
        offset = int(data[3])
    except:
        return await query.answer("डेटा एरर!", show_alert=True)

    if req not in [query.from_user.id, 0]:
        return await query.answer("यह आपके लिए नहीं है!", show_alert=True)

    search = BUTTONS.get(key)
    if not search: 
        return await query.answer("पुरानी रिक्वेस्ट है, फिर से सर्च करें।", show_alert=True)

    await auto_filter(bot, query.message.reply_to_message, query.message, search, offset=offset, is_edit=True)
    await query.answer()

# --- सुधारा हुआ suggest_spelling फंक्शन ---
async def suggest_spelling(message, reply_msg, search):
    btn = [[
        InlineKeyboardButton("🔎 Search Google", url=f"https://www.google.com/search?q={search.replace(' ', '+')}")
    ],[
        InlineKeyboardButton("🚫 Close", callback_data="close_data")
    ]]
    await reply_msg.edit(
        f"👋 Hello {message.from_user.mention if message.from_user else 'User'},\n\nमुझे डेटाबेस में <b>'{search}'</b> नहीं मिला।",
        reply_markup=InlineKeyboardMarkup(btn)
    )

# --- एडमिन कमांड्स ---
@Client.on_message(filters.command('set_pm_search') & filters.user(ADMINS))
async def set_pm_search_config(client, message):
    choice = message.command[1].lower() if len(message.command) > 1 else ""
    if choice == "on":
        await db.set_config('PM_SEARCH_FOR_ALL', True)
        await message.reply("✅ अब नॉन-प्रीमियम यूजर्स भी PM में सर्च कर सकते हैं।")
    elif choice == "off":
        await db.set_config('PM_SEARCH_FOR_ALL', False)
        await message.reply("❌ अब PM सर्च केवल प्रीमियम यूजर्स के लिए है।")
    else:
        await message.reply("उपयोग: `/set_pm_search on/off`")
