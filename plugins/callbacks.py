import random
import time
from datetime import timedelta

from hydrogram import Client, filters
from hydrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)
from hydrogram.errors import MessageNotModified

from info import (
    ADMINS,
    PICS,
    URL,
    BIN_CHANNEL,
    QUALITY,
    script
)

from utils import is_premium, get_wish, temp
from database.users_chats_db import db
from database.ia_filterdb import db_count_documents


# ======================================================
# 🛡 SAFE EDIT HELPERS
# ======================================================

async def safe_edit_media(msg, media, reply_markup=None):
    try:
        await msg.edit_media(media=media, reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except:
        pass


async def safe_edit_caption(msg, caption, reply_markup=None):
    try:
        await msg.edit_caption(caption, reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except:
        pass


async def safe_edit_markup(msg, reply_markup):
    try:
        await msg.edit_reply_markup(reply_markup)
    except MessageNotModified:
        pass
    except:
        pass


# ======================================================
# 🔁 CALLBACK HANDLER
# ======================================================

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    data = query.data
    uid = query.from_user.id

    # --------------------------------------------------
    # ❗ PAGINATION (filter.py handles)
    # --------------------------------------------------
    if data.startswith("page#") or data == "pages":
        return await query.answer()

    # ==================================================
    # ❌ CLOSE FILE (OWNER ONLY)
    # ==================================================
    if data == "close_data":
        await query.answer("Closed")

        target_key = None
        for k, v in temp.FILES.items():
            if v.get("owner") == uid:
                target_key = k
                break

        if target_key:
            mem = temp.FILES.pop(target_key, None)

            try:
                mem["task"].cancel()
            except:
                pass

            try:
                await mem["file"].delete()
            except:
                pass

            try:
                await mem["notice"].delete()
            except:
                pass

        try:
            await query.message.delete()
            if query.message.reply_to_message:
                await query.message.reply_to_message.delete()
        except:
            pass
        return

    # ==================================================
    # ▶️ STREAM (OWNER + PREMIUM)
    # ==================================================
    if data.startswith("stream#"):
        file_id = data.split("#", 1)[1]

        owned = False
        for v in temp.FILES.values():
            if v.get("owner") == uid and v.get("file_id") == file_id:
                owned = True
                break

        if not owned:
            return await query.answer(
                "❌ This file is not for you",
                show_alert=True
            )

        if not await is_premium(uid, client):
            return await query.answer(
                "🔒 Premium only feature.\nUse /plan to upgrade.",
                show_alert=True
            )

        msg = await client.send_cached_media(
            chat_id=BIN_CHANNEL,
            file_id=file_id
        )

        watch = f"{URL}watch/{msg.id}"
        download = f"{URL}download/{msg.id}"

        await safe_edit_markup(
            query.message,
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("▶️ Watch Online", url=watch),
                        InlineKeyboardButton("⬇️ Fast Download", url=download)
                    ],
                    [InlineKeyboardButton("❌ Close", callback_data="close_data")]
                ]
            )
        )
        return await query.answer("Links ready")

    # ==================================================
    # 🆘 HELP (ONLY USER / ADMIN CMDS)
    # ==================================================
    if data == "help":
        await safe_edit_media(
            query.message,
            InputMediaPhoto(
                random.choice(PICS),
                caption=script.HELP_TXT.format(query.from_user.mention)
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("👤 User Commands", callback_data="user_cmds"),
                        InlineKeyboardButton("🛡️ Admin Commands", callback_data="admin_cmds")
                    ],
                    [InlineKeyboardButton("❌ Close", callback_data="close_data")]
                ]
            )
        )
        return

    if data == "user_cmds":
        await safe_edit_caption(
            query.message,
            script.USER_COMMAND_TXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Close", callback_data="close_data")]]
            )
        )
        return

    if data == "admin_cmds":
        if uid not in ADMINS:
            return await query.answer("Admins only", show_alert=True)

        await safe_edit_caption(
            query.message,
            script.ADMIN_COMMAND_TXT,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Close", callback_data="close_data")]]
            )
        )
        return

    # ==================================================
    # 📊 ADMIN STATS
    # ==================================================
    if data == "stats_callback":
        if uid not in ADMINS:
            return await query.answer("Admins only", show_alert=True)

        files = db_count_documents()
        users = await db.total_users_count()
        uptime = str(
            timedelta(seconds=int(time.time() - temp.START_TIME))
        )

        return await query.answer(
            f"📊 Files: {files}\n"
            f"👥 Users: {users}\n"
            f"⏱ Uptime: {uptime}",
            show_alert=True
        )

    # --------------------------------------------------
    await query.answer("Unknown action")
