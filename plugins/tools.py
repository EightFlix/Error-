import os
import aiohttp
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# API URLs
CATBOX_URL = "https://catbox.moe/user/api.php"
LITTERBOX_URL = "https://litterbox.catbox.moe/resources/internals/api.php"
UGUU_URL = "https://uguu.se/api.php?d=upload-tool"

@Client.on_message(filters.command(['graph', 'link']) & filters.private)
async def graph_org_handler(bot, message):
    """Graph.org: Permanent (Limit: 5MB)"""
    if not message.reply_to_message or not (message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.animation):
        return await message.reply("<b>कृपया किसी इमेज या 5MB से छोटी वीडियो पर रिप्लाई करें।</b>")

    media = message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.animation
    file_size = media.file_size if not isinstance(media, list) else media[-1].file_size
    
    if file_size > 5 * 1024 * 1024:
        return await message.reply("<b>❌ Graph.org की सीमा 5MB है! इससे बड़ी फाइल के लिए /ct इस्तेमाल करें।</b>")

    msg = await message.reply("<b>Graph.org पर अपलोड हो रहा है... 🚀</b>")
    path = await message.reply_to_message.download()
    
    try:
        async with aiohttp.ClientSession() as session:
            with open(path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f)
                async with session.post('https://graph.org/upload', data=data) as response:
                    res = await response.json()
                    link = "https://graph.org" + res[0]['src']
                    await msg.edit(f"<b>✅ Graph.org (Permanent Link):\n\n<code>{link}</code></b>")
    except Exception as e:
        await msg.edit(f"<b>❌ Graph.org एरर:</b> {e}")
    finally:
        if os.path.exists(path): os.remove(path)

@Client.on_message(filters.command(['litter', 'lt']) & filters.private)
async def litterbox_handler(bot, message):
    """Litterbox: 1GB (Expires in 24h)"""
    if not message.reply_to_message:
        return await message.reply("<b>फाइल पर रिप्लाई करके /lt लिखें।</b>")
    
    msg = await message.reply("<b>Litterbox पर अपलोड हो रहा है (24h)... 📦</b>")
    path = await message.reply_to_message.download()
    
    try:
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('reqtype', 'fileupload')
            data.add_field('time', '24h')
            data.add_field('fileToUpload', open(path, 'rb'))
            async with session.post(LITTERBOX_URL, data=data) as response:
                link = await response.text()
                await msg.edit(f"<b>📦 Litterbox (Delete in 24h):\n\n<code>{link}</code></b>")
    except Exception as e:
        await msg.edit(f"<b>❌ एरर:</b> {e}")
    finally:
        if os.path.exists(path): os.remove(path)

# नोट: बाकी कमांड्स (/ct, /go, /trans, /img_2_link) भी इसमें पहले की तरह शामिल रहेंगे।
