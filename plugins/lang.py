from hydrogram import Client, filters
from hydrogram.types import Message

from utils import temp
from database.users_chats_db import db


# =====================================================
# 🌍 LANGUAGE CONSTANTS
# =====================================================

LANGS = ("auto", "hi", "en")

LANG_LABEL = {
    "auto": "🌍 Auto",
    "hi": "🇮🇳 Hindi",
    "en": "🇬🇧 English"
}


# =====================================================
# 🧠 AUTO LANGUAGE DETECT (FAST)
# =====================================================

def detect_language(text: str) -> str:
    """
    Very fast Hindi / English detection
    No external lib, no slowdown
    """
    for ch in text:
        if "\u0900" <= ch <= "\u097F":
            return "hi"
    return "en"


# =====================================================
# 📌 GET FINAL LANGUAGE (PM / GROUP)
# =====================================================

async def get_lang(chat_id: int, user_id: int, text: str = "") -> str:
    """
    Language resolution priority:
    1. PM user override
    2. Group settings
    3. Auto detect
    """

    # ---------- PM OVERRIDE ----------
    if chat_id == user_id:
        user = await db.get_user(user_id)
        lang = user.get("lang") if user else None
        if lang in LANGS and lang != "auto":
            return lang

    # ---------- GROUP SETTING ----------
    if chat_id != user_id:
        stg = temp.SETTINGS.get(chat_id)
        if not stg:
            stg = await db.get_settings(chat_id)
            temp.SETTINGS[chat_id] = stg

        grp_lang = stg.get("lang", "auto")
        if grp_lang in LANGS and grp_lang != "auto":
            return grp_lang

    # ---------- AUTO ----------
    return detect_language(text)


# =====================================================
# 📩 /lang COMMAND (PM ONLY)
# =====================================================

@Client.on_message(filters.command("lang") & filters.private)
async def lang_cmd(client: Client, message: Message):
    args = message.text.split(maxsplit=1)

    if len(args) == 1:
        user = await db.get_user(message.from_user.id)
        cur = user.get("lang", "auto") if user else "auto"

        return await message.reply(
            "🌍 <b>Language Settings</b>\n\n"
            f"Current: <b>{LANG_LABEL.get(cur)}</b>\n\n"
            "Use:\n"
            "• <code>/lang hi</code> – हिंदी\n"
            "• <code>/lang en</code> – English\n"
            "• <code>/lang auto</code> – Auto detect",
            quote=True
        )

    lang = args[1].strip().lower()

    if lang not in LANGS:
        return await message.reply(
            "❌ Invalid language\n\n"
            "Available:\n"
            "• <code>hi</code>\n"
            "• <code>en</code>\n"
            "• <code>auto</code>"
        )

    await db.update_user(
        message.from_user.id,
        {"lang": lang}
    )

    await message.reply(
        f"✅ Language set to <b>{LANG_LABEL.get(lang)}</b>",
        quote=True
    )
