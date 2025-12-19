import os
import sys
import time
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from info import ADMINS, LOG_CHANNEL, PICS, SECOND_FILES_DATABASE_URL, script, INDEX_CHANNELS
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents, second_db_count_documents, delete_files
from utils import get_size, get_readable_time, temp

@Client.on_message(filters.command('stats') & filters.user(ADMINS))
async def stats_cmd(bot, message):
    """बॉट और डेटाबेस के आंकड़े दिखाता है"""
    files = db_count_documents()
    users = await db.total_users_count()
    chats = await db.total_chat_count()
    prm = db.get_premium_count()
    
    used_files_db_size = get_size(await db.get_files_db_size())
    used_data_db_size = get_size(await db.get_data_db_size())

    if SECOND_FILES_DATABASE_URL:
        secnd_files_db_used_size = get_size(await db.get_second_files_db_size())
        secnd_files = second_db_count_documents()
    else:
        secnd_files_db_used_size = '-'
        secnd_files = '-'

    uptime = get_readable_time(time.time() - temp.START_TIME)
    
    await message.reply_text(script.STATUS_TXT.format(
        users, prm, chats, used_data_db_size, files, 
        used_files_db_size, secnd_files, secnd_files_db_used_size, uptime
    ))

@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete_files_cmd(bot, message):
    """सर्च क्वेरी के आधार पर फाइलों को डिलीट करता है"""
    try:
        query = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("उपयोग: /delete मूवी_का_नाम")
    
    btn = [[
        InlineKeyboardButton("हाँ, डिलीट करें", callback_data=f"delete_{query}")
    ],[
        InlineKeyboardButton("रद्द करें", callback_data="close_data")
    ]]
    await message.reply_text(
        f"क्या आप वाकई `{query}` से संबंधित सभी फाइलें डिलीट करना चाहते हैं?", 
        reply_markup=InlineKeyboardMarkup(btn)
    )

@Client.on_message(filters.command('restart') & filters.user(ADMINS))
async def restart_bot(bot, message):
    """बॉट को रीस्टार्ट करता है"""
    msg = await message.reply("बॉट रीस्टार्ट हो रहा है...")
    with open('restart.txt', 'w+') as file:
        file.write(f"{msg.chat.id}\n{msg.id}")
    os.execl(sys.executable, sys.executable, "bot.py")

@Client.on_message(filters.command('index_channels') & filters.user(ADMINS))
async def index_channels_info(bot, message):
    """इंडेक्स किए गए चैनलों की लिस्ट दिखाता है"""
    ids = INDEX_CHANNELS
    if not ids:
        return await message.reply("कोई चैनल सेट नहीं है।")
    
    text = '**Indexed Channels:**\n\n'
    for id in ids:
        try:
            chat = await bot.get_chat(id)
            text += f'• {chat.title} (`{id}`)\n'
        except:
            text += f'• Unknown (`{id}`)\n'
    await message.reply(text)

@Client.on_message(filters.command('leave') & filters.user(ADMINS))
async def leave_chat_cmd(bot, message):
    """बॉट को किसी ग्रुप से बाहर निकालता है"""
    if len(message.command) < 2:
        return await message.reply('Chat ID दें।')
    
    chat_id = message.command[1]
    reason = message.text.split(None, 2)[2] if len(message.command) > 2 else "No reason."
    
    try:
        await bot.send_message(chat_id, f"एडमिन के आदेश पर मैं यह ग्रुप छोड़ रहा हूँ।\nकारण: {reason}")
        await bot.leave_chat(chat_id)
        await message.reply(f"सफलतापूर्वक ग्रुप `{chat_id}` छोड़ दिया।")
    except Exception as e:
        await message.reply(f"एरर: {e}")

@Client.on_message(filters.command(['on_auto_filter', 'off_auto_filter']) & filters.user(ADMINS))
async def toggle_autofilter(bot, message):
    """पूरे बॉट के लिए ऑटो-फिल्टर ऑन/ऑफ करता है"""
    status = True if message.command[0] == 'on_auto_filter' else False
    db.update_bot_sttgs('AUTO_FILTER', status)
    await message.reply(f"ऑटो-फिल्टर अब {'ON' if status else 'OFF'} है।")

@Client.on_message(filters.command(['on_pm_search', 'off_pm_search']) & filters.user(ADMINS))
async def toggle_pmsearch(bot, message):
    """पूरे बॉट के लिए PM सर्च ऑन/ऑफ करता है"""
    status = True if message.command[0] == 'on_pm_search' else False
    db.update_bot_sttgs('PM_SEARCH', status)
    await message.reply(f"PM सर्च अब {'ON' if status else 'OFF'} है।")

# --- Broadcast Logic ---
@Client.on_message(filters.command('broadcast') & filters.user(ADMINS) & filters.reply)
async def broadcast_handler(bot, message):
    """सभी यूजर्स को मैसेज ब्रॉडकास्ट करता है"""
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    sts = await message.reply_text("ब्रॉडकास्ट शुरू हो रहा है...")
    
    success = 0
    failed = 0
    async for user in users:
        try:
            await b_msg.copy(chat_id=user['id'])
            success += 1
        except:
            failed += 1
            await db.delete_user(user['id'])
    
    await sts.edit(f"ब्रॉडकास्ट पूरा हुआ!\nसफलता: {success}\nविफलता: {failed}")

