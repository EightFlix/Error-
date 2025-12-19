import re
import time
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.errors import FloodWait
from info import ADMINS, INDEX_EXTENSIONS
from database.ia_filterdb import save_file
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# temp को यहाँ utils से सही तरीके से इम्पोर्ट किया गया है
from utils import temp, get_readable_time

# एक समय में एक ही इंडेक्सिंग सुनिश्चित करने के लिए
lock = asyncio.Lock()

@Client.on_message(filters.command('index') & filters.private & filters.user(ADMINS))
async def index_start_cmd(bot, message):
    """इंडेक्सिंग शुरू करने की मुख्य कमांड (सिर्फ एडमिन्स)"""
    if lock.locked():
        return await message.reply('पिछला इंडेक्सिंग प्रोसेस अभी चल रहा है, कृपया उसके खत्म होने का इंतज़ार करें।')
    
    prompt = await message.reply("अंतिम मैसेज फॉरवर्ड करें या उस चैनल के अंतिम मैसेज का लिंक भेजें जहाँ से इंडेक्सिंग शुरू करनी है।")
    
    try:
        # यूजर के रिप्लाई का इंतज़ार करें
        msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=300)
    except:
        return await prompt.edit("समय समाप्त! फिर से /index कमांड चलाएं।")

    await prompt.delete()

    # लिंक या फॉरवर्डेड मैसेज से डेटा निकालें
    if msg.text and msg.text.startswith("https://t.me"):
        try:
            msg_link = msg.text.split("/")
            last_msg_id = int(msg_link[-1])
            chat_id = msg_link[-2]
            if chat_id.isnumeric():
                chat_id = int(("-100" + chat_id))
        except:
            return await message.reply('अमान्य लिंक!')
    elif msg.forward_from_chat and msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = msg.forward_from_message_id
        chat_id = msg.forward_from_chat.username or msg.forward_from_chat.id
    else:
        return await message.reply('यह न तो फॉरवर्डेड मैसेज है और न ही वैध लिंक।')

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f'चैनल एक्सेस करने में एरर: {e}')

    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply("मैं केवल चैनलों को इंडेक्स कर सकता हूँ।")

    s_prompt = await message.reply("कितने मैसेज स्किप करने हैं? (संख्या भेजें, जैसे: 0)")
    try:
        skip_msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=120)
        skip = int(skip_msg.text)
    except:
        return await message.reply("अमान्य संख्या। प्रोसेस रद्द।")

    await s_prompt.delete()

    buttons = [[
        InlineKeyboardButton('हाँ, शुरू करें', callback_data=f'idx#yes#{chat_id}#{last_msg_id}#{skip}')
    ],[
        InlineKeyboardButton('रद्द करें', callback_data='close_data'),
    ]]
    await message.reply(
        f'<b>चैनल:</b> {chat.title}\n<b>कुल मैसेज:</b> <code>{last_msg_id}</code>\n<b>स्किप:</b> <code>{skip}</code>\n\nक्या आप इंडेक्सिंग शुरू करना चाहते हैं?',
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r'^idx'))
async def index_callback_handler(bot, query):
    data = query.data.split("#")
    ident = data[1]

    if ident == 'yes':
        chat_id = data[2]
        last_msg_id = int(data[3])
        skip = int(data[4])
        
        msg = query.message
        await msg.edit("इंडेक्सिंग शुरू हो रही है... 🚀")
        await run_indexing(int(last_msg_id), chat_id, msg, bot, skip)
    
    elif ident == 'cancel':
        temp.CANCEL = True
        await query.answer("इंडेक्सिंग रोकने का प्रयास किया जा रहा है...", show_alert=True)

async def run_indexing(lst_msg_id, chat, msg, bot, skip):
    start_time = time.time()
    total_files = 0
    duplicate = 0
    errors = 0
    current = skip
    
    async with lock:
        try:
            # यहाँ bot (Client) का सही इस्तेमाल हो रहा है
            async for message in bot.iter_messages(chat, lst_msg_id, skip):
                if temp.CANCEL:
                    temp.CANCEL = False
                    break
                
                current += 1
                if current % 30 == 0:
                    btn = [[InlineKeyboardButton('रद्द करें (STOP)', callback_data=f'idx#cancel#0#0#0')]]
                    try:
                        await msg.edit_text(
                            text=f"प्रगति: <code>{current}/{lst_msg_id}</code>\nसेव की गई फाइलें: <code>{total_files}</code>\nडुप्लीकेट: <code>{duplicate}</code>\nसमय: {get_readable_time(time.time()-start_time)}",
                            reply_markup=InlineKeyboardMarkup(btn)
                        )
                    except FloodWait as e:
                        await asyncio.sleep(e.value)

                if message.empty or not message.media: continue
                if message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT]: continue
                
                media = getattr(message, message.media.value, None)
                if not media: continue
                
                if not (str(media.file_name).lower()).endswith(tuple(INDEX_EXTENSIONS)): continue
                
                media.caption = message.caption
                sts = await save_file(media)
                if sts == 'suc': total_files += 1
                elif sts == 'dup': duplicate += 1
                elif sts == 'err': errors += 1

        except Exception as e:
            await msg.reply(f'इंडेक्सिंग में खराबी: {e}')
        
        finally:
            time_taken = get_readable_time(time.time()-start_time)
            await msg.edit(f'<b>इंडेक्सिंग पूरी हुई! ✅</b>\n\nकुल सेव: <code>{total_files}</code>\nडुप्लीकेट: <code>{duplicate}</code>\nसमय लगा: {time_taken}')

