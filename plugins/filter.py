import re
import time
from difflib import SequenceMatcher
from hydrogram import Client, filters, enums
from info import ADMINS
from database.users_chats_db import db
from database.ia_filterdb import get_search_results
from utils import get_size, is_premium, temp

# ================= CONFIG =================
CACHE_TTL = 45
FUZZY_THRESHOLD = 0.55
MAX_RESULTS = 15

SEARCH_CACHE = {}  # key -> (files, ts)

RE_CLEAN = re.compile(r"[.\-_:\"';!]")
RE_SPACE = re.compile(r"\s+")
RE_EXT = re.compile(r"\.(mkv|mp4|avi|webm|mov|flv|pdf)$", re.I)

# ================= HELPERS =================
def normalize(text: str) -> str:
    return RE_SPACE.sub(" ", RE_CLEAN.sub(" ", text.lower())).strip()

def clean_name(name: str) -> str:
    name = re.sub(r'^[a-zA-Z0-9]+>', '', name).strip()
    return RE_EXT.sub("", name)

def fuzzy(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ================= MESSAGE HANDLER =================
@Client.on_message(filters.text & filters.incoming & (filters.group | filters.private))
async def filter_handler(client, message):
    if message.text.startswith("/"):
        return

    user_id = message.from_user.id

    # -------- GROUP SEARCH HARD BLOCK --------
    if message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        stg = await db.get_settings(message.chat.id)
        if stg.get("search") is False:
            return

    # -------- PM SEARCH PREMIUM CHECK --------
    if message.chat.type == enums.ChatType.PRIVATE:
        if user_id not in ADMINS:
            bot_stg = db.get_bot_sttgs()
            if not bot_stg.get("PM_SEARCH", True):
                if not await is_premium(user_id, client):
                    return

    search = normalize(message.text)
    if len(search) < 2:
        return

    await smart_search(client, message, search)

# ================= SMART SEARCH =================
async def smart_search(client, message, search):
    cached = SEARCH_CACHE.get(search)
    if cached and time.time() - cached[1] < CACHE_TTL:
        files = cached[0]
    else:
        files, _, _ = await get_search_results(search)
        if files:
            SEARCH_CACHE[search] = (files, time.time())

    if not files:
        return await message.reply_text(
            f"❌ <b>No results found for:</b>\n<code>{search}</code>",
            parse_mode=enums.ParseMode.HTML
        )

    scored = []
    for f in files:
        score = fuzzy(search, normalize(f["file_name"]))
        if score >= FUZZY_THRESHOLD:
            scored.append((score, f))

    if not scored:
        return await message.reply_text(
            f"❌ <b>No close match found for:</b>\n<code>{search}</code>",
            parse_mode=enums.ParseMode.HTML
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:MAX_RESULTS]

    text = (
        f"<b>♻️ Smart Results</b>\n"
        f"<code>{search}</code>\n\n"
    )

    for _, f in scored:
        name = clean_name(f["file_name"])
        size = get_size(f["file_size"])
        link = f"https://t.me/{temp.U_NAME}?start=file_{message.chat.id}_{f['_id']}"
        text += f"📁 <a href='{link}'>[{size}] {name}</a>\n"

    await message.reply_text(
        text,
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML,
        quote=True
    )
