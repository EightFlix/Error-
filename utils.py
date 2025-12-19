from hydrogram.errors import UserNotParticipant, FloodWait
from info import LONG_IMDB_DESCRIPTION, ADMINS, IS_PREMIUM, TIME_ZONE
import asyncio
from hydrogram.types import InlineKeyboardButton
from hydrogram import enums
import re
from datetime import datetime
from database.users_chats_db import db
from shortzy import Shortzy
import requests, pytz

class temp(object):
    START_TIME = 0
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CANCEL = False
    U_NAME = None
    B_NAME = None
    SETTINGS = {}
    VERIFICATIONS = {}
    FILES = {}
    USERS_CANCEL = False
    GROUPS_CANCEL = False
    BOT = None
    PREMIUM = {}

# --- प्रीमियम और सब्स्क्रिप्शन फंक्शन्स ---

async def is_subscribed(bot, query):
    btn = []
    if await is_premium(query.from_user.id, bot):
        return btn
    stg = db.get_bot_sttgs()
    if not stg or not stg.get('FORCE_SUB_CHANNELS'):
        return btn
    for id in stg.get('FORCE_SUB_CHANNELS').split(' '):
        try:
            chat = await bot.get_chat(int(id))
            await bot.get_chat_member(int(id), query.from_user.id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join : {chat.title}', url=chat.invite_link)])
        except: pass
    return btn

async def is_premium(user_id, bot):
    if not IS_PREMIUM or user_id in ADMINS:
        return True
    mp = db.get_plan(user_id)
    if mp['premium']:
        if mp['expire'] < datetime.now():
            await bot.send_message(user_id, "Your premium plan is expired.")
            mp.update({'expire': '', 'plan': '', 'premium': False})
            db.update_plan(user_id, mp)
            return False
        return True
    return False

async def check_premium(bot):
    """ प्रीमियम यूजर्स का स्टेटस ऑटो-चेक करने के लिए """
    while True:
        pr = [i for i in db.get_premium_users() if i['status']['premium']]
        for p in pr:
            mp = p['status']
            if mp['expire'] < datetime.now():
                try:
                    await bot.send_message(p['id'], "Your premium plan has expired.")
                except: pass
                mp.update({'expire': '', 'plan': '', 'premium': False})
                db.update_plan(p['id'], mp)
        await asyncio.sleep(1200)

# --- ब्रॉडकास्ट फंक्शन्स ---

async def broadcast_messages(user_id, message, pin):
    try:
        m = await message.copy(chat_id=user_id)
        if pin: await m.pin(both_sides=True)
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message, pin)
    except:
        await db.delete_user(int(user_id))
        return "Error"

async def groups_broadcast_messages(chat_id, message, pin):
    try:
        k = await message.copy(chat_id=chat_id)
        if pin: 
            try: await k.pin()
            except: pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except:
        await db.delete_chat(chat_id)
        return "Error"

# --- अन्य उपयोगिता फंक्शन्स ---

async def get_poster(query, bulk=False, id=False, file=None):
    return None # IMDb हटा दिया गया है

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units)-1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

async def get_shortlink(url, api, link):
    shortzy = Shortzy(api_key=api, base_site=url)
    return await shortzy.convert(link)

def get_readable_time(seconds):
    periods = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
    result = ''
    for n, s in periods:
        if seconds >= s:
            v, seconds = divmod(seconds, s)
            result += f'{int(v)}{n}'
    return result or "0s"

async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS[group_id] = settings
    return settings

def get_wish():
    now = datetime.now(pytz.timezone(TIME_ZONE)).strftime("%H")
    if now < "12": return "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ 🌞"
    if now < "18": return "ɢᴏᴏᴅ ᴀꜰᴛᴇʀɴᴏᴏɴ 🌗"
    return "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ 🌘"
