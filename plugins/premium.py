import os
import qrcode
import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from hydrogram.errors import ListenerTimeout

# temp को यहाँ से हटा दिया गया है
from info import (
    ADMINS, IS_PREMIUM, PRE_DAY_AMOUNT, UPI_ID, UPI_NAME, 
    RECEIPT_SEND_USERNAME, script
)
from database.users_chats_db import db
# temp को यहाँ utils से इम्पोर्ट किया गया है
from utils import is_premium, get_readable_time, temp

# --- Commands ---

@Client.on_message(filters.command('plan') & filters.private)
async def plan_cmd(client, message):
    if not IS_PREMIUM:
        return await message.reply('प्रीमियम फीचर अभी एडमिन द्वारा बंद किया गया है।')
    
    btn = [[
        InlineKeyboardButton('Activate Trial (1h)', callback_data='activate_trial')
    ],[
        InlineKeyboardButton('Activate Premium Plan', callback_data='activate_plan')
    ]]
    await message.reply_text(
        script.PLAN_TXT.format(PRE_DAY_AMOUNT, RECEIPT_SEND_USERNAME), 
        reply_markup=InlineKeyboardMarkup(btn)
    )

@Client.on_message(filters.command('myplan') & filters.private)
async def myplan_cmd(client, message):
    if not IS_PREMIUM:
        return await message.reply('प्रीमियम फीचर डिसेबल है।')
    
    if not await is_premium(message.from_user.id, client):
        btn = [[
            InlineKeyboardButton('Activate Trial', callback_data='activate_trial'),
            InlineKeyboardButton('Activate Plan', callback_data='activate_plan')
        ]]
        return await message.reply(
            'आपके पास कोई सक्रिय प्रीमियम प्लान नहीं है।', 
            reply_markup=InlineKeyboardMarkup(btn)
        )
    
    mp = db.get_plan(message.from_user.id)
    expiry = mp['expire'].strftime('%Y.%m.%d %H:%M:%S')
    await message.reply(f"आपका सक्रिय प्लान: {mp['plan']}\nसमाप्ति तिथि: {expiry}")

@Client.on_message(filters.command('add_prm') & filters.user(ADMINS))
async def add_premium_admin(bot, message):
    try:
        args = message.text.split(' ')
        user_id = int(args[1])
        duration = args[2]
        days = int(duration[:-1]) 
    except:
        return await message.reply('उपयोग: /add_prm user_id 7d')

    try:
        user = await bot.get_users(user_id)
    except Exception as e:
        return await message.reply(f'एरर: {e}')

    mp = db.get_plan(user.id)
    expiry = datetime.now() + timedelta(days=days)
    mp.update({'expire': expiry, 'plan': f'{days} Days', 'premium': True})
    
    db.update_plan(user.id, mp)
    await message.reply(f"प्रदान किया गया: {user.mention}\nसमाप्ति: {expiry.strftime('%Y.%m.%d %H:%M:%S')}")
    try:
        await bot.send_message(user.id, f"बधाई हो! आपका प्रीमियम सक्रिय हो गया है।\nसमाप्ति: {expiry.strftime('%Y.%m.%d %H:%M:%S')}")
    except: pass

@Client.on_message(filters.command('rm_prm') & filters.user(ADMINS))
async def remove_premium_admin(bot, message):
    try:
        user_id = int(message.text.split(' ')[1])
    except:
        return await message.reply('उपयोग: /rm_prm user_id')

    mp = db.get_plan(user_id)
    mp.update({'expire': '', 'plan': '', 'premium': False})
    db.update_plan(user_id, mp)
    await message.reply("यूजर को प्रीमियम लिस्ट से हटा दिया गया है।")

@Client.on_message(filters.command('prm_list') & filters.user(ADMINS))
async def premium_list_admin(bot, message):
    tx = await message.reply('लिस्ट निकाली जा रही है...')
    users = db.get_premium_users()
    text = 'प्रीमियम यूजर्स:\n\n'
    count = 0
    for u_data in users:
        if u_data.get('status', {}).get('premium'):
            text += f"ID: `{u_data['id']}` | प्लान: {u_data['status']['plan']}\n"
            count += 1
    if count == 0:
        await tx.edit_text("कोई प्रीमियम यूजर नहीं मिला।")
    else:
        await tx.edit_text(text)

# --- Callbacks ---

@Client.on_callback_query(filters.regex('^activate_trial'))
async def trial_callback(bot, query: CallbackQuery):
    mp = db.get_plan(query.from_user.id)
    if mp.get('trial'):
        return await query.answer('आपने पहले ही ट्रायल इस्तेमाल कर लिया है।', show_alert=True)
    
    ex = datetime.now() + timedelta(hours=1)
    mp.update({'expire': ex, 'trial': True, 'plan': '1 Hour Trial', 'premium': True})
    db.update_plan(query.from_user.id, mp)
    await query.message.edit(f"ट्रायल सक्रिय! 1 घंटे के लिए।\nसमाप्ति: {ex.strftime('%H:%M:%S')}")

@Client.on_callback_query(filters.regex('^activate_plan'))
async def plan_activation_callback(bot, query: CallbackQuery):
    await query.message.edit('कितने दिनों का प्रीमियम चाहिए? (केवल संख्या भेजें, जैसे: 7)')
    try:
        msg = await bot.listen(chat_id=query.message.chat.id, user_id=query.from_user.id, timeout=300)
        days = int(msg.text)
    except (ListenerTimeout, ValueError):
        return await query.message.reply('समय समाप्त या अमान्य संख्या। फिर से प्रयास करें।')

    amount = days * PRE_DAY_AMOUNT
    note = f"{days} days premium for {query.from_user.id}"
    upi_uri = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn={note}"
    
    qr = qrcode.make(upi_uri)
    path = f"qr_{query.from_user.id}.png"
    qr.save(path)
    
    await query.message.reply_photo(
        path, 
        caption=f"प्लान: {days} दिन\nराशि: ₹{amount}\n\nइस QR को स्कैन करके भुगतान करें और रसीद का फोटो यहाँ भेजें (10 मिनट में)।"
    )
    if os.path.exists(path):
        os.remove(path)

    try:
        receipt = await bot.listen(chat_id=query.message.chat.id, user_id=query.from_user.id, timeout=600)
        if receipt.photo:
            await receipt.reply('आपकी रसीद एडमिन को भेज दी गई है। कृपया सत्यापन का इंतज़ार करें।')
            await bot.send_photo(RECEIPT_SEND_USERNAME, receipt.photo.file_id, caption=f"#NewPayment\nUser: {query.from_user.mention}\nNote: {note}")
        else:
            await receipt.reply('कृपया फोटो भेजें। सहायता के लिए एडमिन से संपर्क करें।')
    except ListenerTimeout:
        await query.message.reply('भुगतान रसीद भेजने का समय समाप्त हो गया।')

