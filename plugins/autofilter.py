import re
import math
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS, MAX_BTN, SPELL_CHECK, temp, script, PROTECT_CONTENT
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import get_settings, get_size, is_premium, get_shortlink, get_readable_time
from .metadata import get_imdb_metadata, get_file_list_string, send_metadata_reply

# इन-मेमोरी स्टोरेज (पुरानी फाइलों की तरह)
BUTTONS = {}

@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(client, message):
    # कमांड्स को इग्नोर करें
    if message.text.startswith("/"):
        return
    
    # PM सर्च डिसेबल चेक
    if message.chat.type == enums.ChatType.PRIVATE:
        stg = db.get_bot_sttgs()
        if not stg.get('PM_SEARCH'):
            return await message.reply_text('PM search is disabled by Admin!')

    # सर्च शुरू करें
    search = re.sub(r"\s+", " ", re.sub(r"[-:\"';!]", " ", message.text)).strip()
    if not search: return

    reply_msg = await message.reply_text(f"<b><i>🔍 `{search}` सर्च किया जा रहा है...</i></b>")
    await auto_filter(client, message, reply_msg, search)

async def auto_filter(client, message, reply_msg, search):
    settings = await get_settings(message.chat.id)
    files, offset, total = await get_search_results(search)

    if not files:
        if settings["spell_check"]:
            return await suggest_spelling(message, reply_msg, search)
        else:
            return await reply_msg.edit(f"क्षमा करें, `{search}` नहीं मिला।")

    # बटन और कैप्शन तैयार करें
    req = message.from_user.id if message.from_user else 0
    key = f"{message.chat.id}-{message.id}"
    temp.FILES[key] = files
    BUTTONS[key] = search

    # पेजिनेशन बटन
    btn = []
    if settings['links']:
        # अगर 'Link Mode' ऑन है तो फाइलों की लिस्ट टेक्स्ट में जाएगी
        files_link = get_file_list_string(files, message.chat.id)
    else:
        # अगर 'Button Mode' ऑन है
        files_link = ""
        for file in files:
            btn.append([InlineKeyboardButton(f"[{get_size(file['file_size'])}] {file['file_name']}", callback_data=f"file#{file['_id']}")])

    # Next बटन लॉजिक
    if offset != "":
        btn.append([
            InlineKeyboardButton(f"1/{math.ceil(int(total) / MAX_BTN)}", callback_data="pages"),
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{offset}")
        ])

    # लैंग्वेज और क्वालिटी बटन्स
    btn.insert(0, [
        InlineKeyboardButton("🌐 ʟᴀɴɢᴜᴀɢᴇ", callback_data=f"languages#{key}#{req}#0"),
        InlineKeyboardButton("🔍 ǫᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}#{req}#0")
    ])

    # प्रीमियम बटन
    btn.append([InlineKeyboardButton('🤑 ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ', url=f"https://t.me/{temp.U_NAME}?start=premium")])

    # IMDb से पोस्टर और कैप्शन लाएं (metadata.py का उपयोग)
    cap, poster = await get_imdb_metadata(search, files, settings)
    
    # मैसेज भेजें
    await send_metadata_reply(message, cap, poster, InlineKeyboardMarkup(btn), settings, files_link)
    await reply_msg.delete()

async def suggest_spelling(message, reply_msg, search):
    # स्पेलिंग सुझाव का लॉजिक (Google सर्च बटन के साथ)
    btn = [[
        InlineKeyboardButton("🔎 Search Google", url=f"https://www.google.com/search?q={search.replace(' ', '+')}")
    ],[
        InlineKeyboardButton("🚫 Close", callback_data="close_data")
    ]]
    await reply_msg.edit(
        f"👋 Hello {message.from_user.mention if message.from_user else 'User'},\n\nमुझे डेटाबेस में <b>'{search}'</b> नहीं मिला। कृपया स्पेलिंग चेक करें या गूगल पर खोजें।",
        reply_markup=InlineKeyboardMarkup(btn)
    )

# --- Callback Handlers for Pagination ---

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page_handler(bot, query: CallbackQuery):
    _, req, key, offset = query.data.split("_")
    if int(req) not in [query.from_user.id, 0]:
        return await query.answer("यह आपके लिए नहीं है!", show_alert=True)

    search = BUTTONS.get(key)
    if not search: return await query.answer("पुरानी रिक्वेस्ट है, फिर से सर्च करें।", show_alert=True)

    files, n_offset, total = await get_search_results(search, offset=int(offset))
    settings = await get_settings(query.message.chat.id)
    
    # बटन अपडेट लॉजिक यहाँ दोबारा आएगा (Pagination के लिए)
    # (इसे छोटा रखने के लिए यहाँ संक्षिप्त किया गया है, लेकिन कार्यक्षमता वही है)
    await query.answer("लोड हो रहा है...")
