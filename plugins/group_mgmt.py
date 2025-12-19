from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from database.users_chats_db import db
from info import ADMINS, script, LOG_CHANNEL
from utils import get_settings

@Client.on_message(filters.command('settings') & filters.group)
async def settings_group(client, message):
    """ग्रुप में सेटिंग्स मेनू खोलता है (केवल एडमिन्स के लिए)"""
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("आप एक गुमनाम एडमिन हैं, कृपया अपने अकाउंट से मैसेज करें।")
    
    # चेक करें कि क्या यूजर एडमिन है
    chat_member = await client.get_chat_member(message.chat.id, userid)
    if chat_member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and userid not in ADMINS:
        return await message.reply("यह कमांड केवल ग्रुप एडमिन्स के लिए है।")

    settings = await db.get_settings(message.chat.id)
    if settings is not None:
        buttons = [
            [
                InlineKeyboardButton('IMDB', callback_data=f'setgs#imdb#{settings["imdb"]}#{message.chat.id}'),
                InlineKeyboardButton('✅ ᴏɴ' if settings["imdb"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#imdb#{settings["imdb"]}#{message.chat.id}')
            ],
            [
                InlineKeyboardButton('sᴘᴇʟʟ ᴄʜᴇᴄᴋ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{message.chat.id}'),
                InlineKeyboardButton('✅ ᴏɴ' if settings["spell_check"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{message.chat.id}')
            ],
            [
                InlineKeyboardButton('ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{message.chat.id}'),
                InlineKeyboardButton('✅ ᴏɴ' if settings["auto_delete"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{message.chat.id}')
            ],
            [
                InlineKeyboardButton('ᴡᴇʟᴄᴏᴍᴇ', callback_data=f'setgs#welcome#{settings["welcome"]}#{message.chat.id}'),
                InlineKeyboardButton('✅ ᴏɴ' if settings["welcome"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#welcome#{settings["welcome"]}#{message.chat.id}')
            ]
        ]
        await message.reply_text(
            text=f"<b>⚙️ {message.chat.title} की सेटिंग्स बदलें:</b>",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML
        )

@Client.on_message(filters.command('connect') & filters.private)
async def connect_pm(client, message):
    """ग्रुप को PM से कनेक्ट करने का निर्देश"""
    await message.reply_text(
        "किसी ग्रुप को कनेक्ट करने के लिए, मुझे उस ग्रुप में एडमिन बनाएँ और ग्रुप में <code>/connect</code> लिखें।"
    )

@Client.on_message(filters.command('connect') & filters.group)
async def connect_group(client, message):
    """ग्रुप में /connect कमांड चलाने पर PM कनेक्शन सेट करता है"""
    userid = message.from_user.id
    group_id = message.chat.id
    group_name = message.chat.title
    
    db.add_connect(group_id, userid)
    await message.reply_text(
        f"सफलतापूर्वक कनेक्टेड!\nअब आप अपनी PM में <b>{group_name}</b> की सेटिंग्स मैनेज कर सकते हैं।",
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.new_chat_members & filters.group)
async def welcome_members(client, message):
    """नए मेंबर्स का स्वागत करता है"""
    settings = await db.get_settings(message.chat.id)
    if not settings.get("welcome", True):
        return
    
    for member in message.new_chat_members:
        await message.reply_text(
            script.WELCOME_TEXT.format(mention=member.mention, title=message.chat.title)
        )

@Client.on_message(filters.command('id'))
async def get_id(client, message):
    """चैट या यूजर की ID बताता है"""
    if message.chat.type == enums.ChatType.PRIVATE:
        await message.reply_text(f"आपकी ID: <code>{message.from_user.id}</code>")
    else:
        await message.reply_text(f"ग्रुप ID: <code>{message.chat.id}</code>")

@Client.on_callback_query(filters.regex(r'^setgs#'))
async def update_settings_callback(client, query: CallbackQuery):
    """सेटिंग्स को टॉगल (On/Off) करने का कॉल-बैक"""
    _, field, current_status, chat_id = query.data.split('#')
    chat_id = int(chat_id)
    new_status = False if current_status == 'True' else True
    
    # चेक करें कि क्या यूजर एडमिन है
    user_id = query.from_user.id
    try:
        chat_member = await client.get_chat_member(chat_id, user_id)
        if chat_member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and user_id not in ADMINS:
            return await query.answer("आप एडमिन नहीं हैं!", show_alert=True)
    except:
        return await query.answer("कुछ गलत हुआ।", show_alert=True)

    settings = await db.get_settings(chat_id)
    settings[field] = new_status
    await db.update_settings(chat_id, settings)
    
    # बटन अपडेट करें
    buttons = [
        [
            InlineKeyboardButton('IMDB', callback_data=f'setgs#imdb#{settings["imdb"]}#{chat_id}'),
            InlineKeyboardButton('✅ ᴏɴ' if settings["imdb"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#imdb#{settings["imdb"]}#{chat_id}')
        ],
        [
            InlineKeyboardButton('sᴘᴇʟʟ ᴄʜᴇᴄᴋ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{chat_id}'),
            InlineKeyboardButton('✅ ᴏɴ' if settings["spell_check"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{chat_id}')
        ],
        [
            InlineKeyboardButton('ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{chat_id}'),
            InlineKeyboardButton('✅ ᴏɴ' if settings["auto_delete"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{chat_id}')
        ],
        [
            InlineKeyboardButton('ᴡᴇʟᴄᴏᴍᴇ', callback_data=f'setgs#welcome#{settings["welcome"]}#{chat_id}'),
            InlineKeyboardButton('✅ ᴏɴ' if settings["welcome"] else '❌ ᴏꜰꜰ', callback_data=f'setgs#welcome#{settings["welcome"]}#{chat_id}')
        ]
    ]
    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
    await query.answer("सेटिंग अपडेट हो गई है।")
