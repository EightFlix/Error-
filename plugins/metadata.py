import re
from hydrogram import enums
from hydrogram.errors.exceptions.bad_request_400 import (
    MediaEmpty,
    PhotoInvalidDimensions,
    WebpageMediaEmpty
)

from utils import get_size, get_readable_time, temp
from info import DELETE_TIME


# ======================================================
# 🧠 CAPTION BUILDER (FAST & CLEAN)
# ======================================================

async def build_search_caption(search: str) -> str:
    return (
        "<b>💭 Hey!\n"
        "♻️ Here are the results for your search:</b>\n\n"
        f"<code>{search}</code>"
    )


# ======================================================
# 📂 FILE LIST BUILDER
# ======================================================

def get_file_list_string(files, chat_id, offset=1):
    """
    Builds file list with direct deep links.
    """
    text = ""
    for idx, file in enumerate(files, start=offset):
        clean_name = re.sub(r'^[a-zA-Z0-9]+>', '', file['file_name']).strip()
        size = get_size(file['file_size'])

        text += (
            f"\n\n<b>{idx}. "
            f"<a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{chat_id}_{file['_id']}'>"
            f"[{size}] {clean_name}</a></b>"
        )
    return text


# ======================================================
# ⏳ AUTO DELETE NOTE
# ======================================================

def get_auto_delete_str(settings):
    if settings.get("auto_delete"):
        return (
            "\n\n<b>⚠️ This message will be auto deleted after "
            f"<code>{get_readable_time(DELETE_TIME)}</code></b>"
        )
    return ""


# ======================================================
# 📤 SEND RESULT MESSAGE
# ======================================================

async def send_metadata_reply(
    message,
    search: str,
    files,
    reply_markup,
    settings
):
    """
    Sends search result message (text only).
    Ultra-fast, no external dependency.
    """

    caption = await build_search_caption(search)
    files_link = get_file_list_string(files, message.chat.id)
    delete_note = get_auto_delete_str(settings)

    # Telegram caption safety (HTML)
    final_text = (caption + files_link + delete_note)[:4096]

    return await message.reply_text(
        text=final_text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML,
        quote=True
    )
