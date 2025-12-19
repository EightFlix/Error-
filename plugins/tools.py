import os
import aiohttp
import asyncio
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from utils import temp

# API URLs
CATBOX_URL = "https://catbox.moe/user/api.php"
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
UGUU_URL = "https://uguu.se/api.php?d=upload-tool"

@Client.on_message(filters.command(['graph', 'link']) & filters.private)
async def graph_org_handler(bot, message):
    if not message.reply_to_message or not (message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.animation):
        return await message.reply("<b>❌ कृपया 5MB से छोटी इमेज/वीडियो पर रिप्लाई करें।</b>")

    media = message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.animation
    file_size = media.file_size if not isinstance(media, list) else media[-1].file_size
    
    if file_size > 5 * 1024 * 1024:
        return await message.reply("<b>❌ Graph.org की सीमा 5MB है!</b>")

    msg = await message.reply("<b>📤 Graph.org पर अपलोड हो रहा है...</b>")
    path = await message.reply_to_message.download()
    
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('file', open(path, 'rb'))
            async with session.post('https://graph.org/upload', data=data) as response:
                res = await response.json()
                # यहाँ चेक करें कि क्या रिस्पॉन्स एक लिस्ट है (सफलता) या डिक्शनरी (एरर)
                if isinstance(res, list) and 'src' in res[0]:
                    link = "https://graph.org" + res[0]['src']
                    await msg.edit(f"<b>✅ ɢʀᴀᴘʜ.ᴏʀɢ ʟɪɴᴋ:\n\n<code>{link}</code></b>",
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🌐 ᴏᴘᴇɴ ʟɪɴᴋ", url=link)]]))
                else:
                    error_msg = res.get('error') if isinstance(res, dict) else "Unknown Error"
                    await msg.edit(f"<b>❌ API एरर: {error_msg}</b>")
    except Exception as e:
        await msg.edit(f"<b>❌ सिस्टम एरर: {e}</b>")
    finally:
        if os.path.exists(path): os.remove(path)

@Client.on_message(filters.command(['gofile', 'go']) & filters.private)
async def gofile_handler(bot, message):
    if not message.reply_to_message:
        return await message.reply("<b>❌ फाइल पर रिप्लाई करें।</b>")
    
    msg = await message.reply("<b>⚡ GoFile पर अपलोड हो रहा है...</b>")
    path = await message.reply_to_message.download()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.gofile.io/getServer') as r:
                server = (await r.json())['data']['server']
            
            data = aiohttp.FormData()
            data.add_field('file', open(path, 'rb'))
            async with session.post(f'https://{server}.gofile.io/uploadFile', data=data) as r:
                res = await r.json()
                link = res['data']['downloadPage']
                await msg.edit(f"<b>✅ ɢᴏғɪʟᴇ ʟɪɴᴋ:\n\n<code>{link}</code></b>")
    except Exception as e:
        await msg.edit(f"<b>❌ GoFile एरर: {e}</b>")
    finally:
        if os.path.exists(path): os.remove(path)

@Client.on_message(filters.command(['ct', 'catbox']) & filters.private)
async def catbox_handler(bot, message):
    if not message.reply_to_message:
        return await message.reply("<b>❌ फाइल पर रिप्लाई करें।</b>")
    
    msg = await message.reply("<b>⏳ Catbox पर अपलोड हो रहा है...</b>")
    path = await message.reply_to_message.download()
    
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('fileToUpload', open(path, 'rb'))
            async with session.post(CATBOX_URL, data=data) as r:
                link = await r.text()
                if "https" in link:
                    await msg.edit(f"<b>✅ ᴄᴀᴛʙᴏx ʟɪɴᴋ:\n\n<code>{link}</code></b>")
                else:
                    await msg.edit(f"<b>❌ Catbox एरर: {link}</b>")
    except Exception as e:
        await msg.edit(f"<b>❌ एरर: {e}</b>")
    finally:
        if os.path.exists(path): os.remove(path)

@Client.on_message(filters.command(['litter', 'lt']) & filters.private)
async def litter_handler(bot, message):
    if not message.reply_to_message: return
    msg = await message.reply("<b>📦 Litterbox (24h) अपलोड शुरू...</b>")
    path = await message.reply_to_message.download()
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('time', '24h')
            data.add_field('fileToUpload', open(path, 'rb'))
            async with session.post(LITTERBOX_URL, data=data) as r:
                link = await r.text()
                await msg.edit(f"<b>✅ ʟɪᴛᴛᴇʀʙᴏx ʟɪɴᴋ:\n\n<code>{link}</code></b>")
    except Exception as e:
        await msg.edit(f"<b>❌ एरर: {e}</b>")
    finally:
        if os.path.exists(path): os.remove(path)

