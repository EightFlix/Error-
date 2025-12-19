import re
import math
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
    
    # --- PM सर्च कंट्रोल लॉजिक ---
    if message.chat.type == enums.ChatType.PRIVATE:
        # अगर यूजर एडमिन नहीं है और प्रीमियम भी नहीं है, तो कॉन्फ़िगरेशन चेक करें
        if user_id not in ADMINS and not is_prm:
            # डेटाबेस से चेक करें कि क्या एडमिन ने 'PM_SEARCH_FOR_ALL' ऑन किया है
            pm_search_all = await db.get_config('PM_SEARCH_FOR_ALL')
            if not pm_search_all:
                return await message.reply_text(
                    "<b>❌ ᴘᴍ sᴇᴀʀᴄʜ ᴅɪsᴀʙʟᴇᴅ</b>\n\nप्रीमियम यूजर्स ही PM में सर्च कर सकते हैं। आप हमारे ग्रुप में सर्च करें या प्रीमियम प्लान लें।"
                )

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
    is_prm = await is_premium(req, client) # प्रीमियम स्टेटस चेक
    key = f"{message.chat.id}-{message.id}"
    temp.FILES[key] = files
    BUTTONS[key] = search

    btn = []
    
    # --- फ़ाइल बटन और शॉर्टलिंक लॉजिक ---
    for file in files:
        if is_prm:
            # प्रीमियम यूजर को सीधा बटन (callback_data) मिलेगा
            btn.append([InlineKeyboardButton(f"[{get_size(file['file_size'])}] {file['file_name']}", callback_data=f"file#{file['_id']}")])
        else:
            # नॉन-प्रीमियम को शॉर्टलिंक वाला URL बटन मिलेगा
            f_link = await get_shortlink(settings['url'], settings['api'], f"https://t.me/{temp.U_NAME}?start=file_{message.chat.id}_{file['_id']}")
            btn.append([InlineKeyboardButton(f"⚡ [{get_size(file['file_size'])}] {file['file_name']}", url=f_link)])

    # पेजिनेशन बटन लॉजिक
    pagination_row = [InlineKeyboardButton(f"{math.ceil(int(offset) / MAX_BTN) + 1}/{math.ceil(int(total) / MAX_BTN)}", callback_data="pages")]
    if n_offset != "":
        pagination_row.append(InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{n_offset}"))
    if offset != 0:
        pagination_row.insert(0, InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{int(offset)-MAX_BTN}"))
    
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
        await send_metadata_reply(message, cap, poster, InlineKeyboardMarkup(btn), settings, "")
        await reply_msg.delete()

# --- एडमिन के लिए PM सर्च कंट्रोल कमांड ---
@Client.on_message(filters.command('set_pm_search') & filters.user(ADMINS))
async def set_pm_search_config(client, message):
    if len(message.command) < 2:
        return await message.reply("उपयोग: `/set_pm_search on` या `/set_pm_search off`")
    
    choice = message.command[1].lower()
    if choice == "on":
        await db.set_config('PM_SEARCH_FOR_ALL', True)
        await message.reply("✅ अब नॉन-प्रीमियम यूजर्स भी PM में सर्च कर सकते हैं।")
    else:
        await db.set_config('PM_SEARCH_FOR_ALL', False)
        await message.reply("❌ अब PM सर्च केवल प्रीमियम यूजर्स के लिए है।")

