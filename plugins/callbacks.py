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
        if not msg or not media:
            return
        await msg.edit_media(media=media, reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except:
        pass


async def safe_edit_caption(msg, caption, reply_markup=None):
    try:
        if msg.caption == caption:
            return
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
# 🔘 UI HELPERS
# ======================================================

def start_buttons():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "+ Add Me To Your Group +",
                    url=f"https://t.me/{temp.U_NAME}?startgroup=start"
                )
            ],
            [
                InlineKeyboardButton("👨‍🚒 Help", callback_data="help"),
                InlineKeyboardButton("📚 About", callback_data="about")
            ]
        ]
    )


def back_btn(cb="start"):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("« Back", callback_data=cb)]]
    )


# ======================================================
# 🔁 CALLBACK HANDLER
# ======================================================

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    data = query.data
    uid = query.from_user.id

    # --------------------------------------------------
    # ❗ IGNORE PAGINATION (handled in filter.py)
    # --------------------------------------------------
    if data.startswith("page#") or data == "pages":
        return await query.answer()

    # ==================================================
    # ❌ CLOSE (OWNER ONLY)
    # ==================================================
    if data == "close_data":
        await query.answer("Closed")

        mem = temp.FILES.get(uid)

        # ---- ownership validation ----
        if mem and mem.get("owner") != uid:
            return await query.answer(
                "❌ This file is not for you",
                show_alert=True
            )

        # ---- PM FILE CLEANUP ----
        mem = temp.FILES.pop(uid, None)
        if mem:
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

        # ---- UI CLEANUP ----
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
        mem = temp.FILES.get(uid)

        # ---- ownership validation ----
        if mem and mem.get("owner") != uid:
            return await query.answer(
                "❌ This file is not for you",
                show_alert=True
            )

        if not await is_premium(uid, client):
            return await query.answer(
                "🔒 Premium only feature.\nUse /plan to upgrade.",
                show_alert=True
            )

        file_id = data.split("#", 1)[1]

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
    # 🆘 HELP
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
                    [InlineKeyboardButton("« Back", callback_data="start")]
                ]
            )
        )
        return

    if data == "user_cmds":
        await safe_edit_caption(
            query.message,
            script.USER_COMMAND_TXT,
            reply_markup=back_btn("help")
        )
        return

    if data == "admin_cmds":
        if uid not in ADMINS:
            return await query.answer("Admins only", show_alert=True)

        await safe_edit_caption(
            query.message,
            script.ADMIN_COMMAND_TXT,
            reply_markup=back_btn("help")
        )
        return

    # ==================================================
    # 📚 ABOUT
    # ==================================================
    if data == "about":
        await safe_edit_media(
            query.message,
            InputMediaPhoto(
                random.choice(PICS),
                caption=script.MY_ABOUT_TXT
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("📊 Stats", callback_data="stats_callback"),
                        InlineKeyboardButton("👤 Owner", callback_data="owner_info")
                    ],
                    [InlineKeyboardButton("« Back", callback_data="start")]
                ]
            )
        )
        return

    if data == "owner_info":
        await safe_edit_caption(
            query.message,
            script.MY_OWNER_TXT,
            reply_markup=back_btn("about")
        )
        return

    # ==================================================
    # 🔙 BACK TO START
    # ==================================================
    if data == "start":
        await safe_edit_media(
            query.message,
            InputMediaPhoto(
                random.choice(PICS),
                caption=script.START_TXT.format(
                    query.from_user.mention,
                    get_wish()
                )
            ),
            reply_markup=start_buttons()
        )
        return

    # ==================================================
    # 🎞 QUALITY GROUPING
    # ==================================================
    if data.startswith("group_quality#"):
        _, search, req = data.split("#")
        if int(req) != uid:
            return await query.answer("Not for you", show_alert=True)

        btn = []
        for i in range(0, len(QUALITY), 2):
            row = [
                InlineKeyboardButton(
                    QUALITY[i].upper(),
                    callback_data=f"apply_quality#{QUALITY[i]}#{search}#{req}"
                )
            ]
            if i + 1 < len(QUALITY):
                row.append(
                    InlineKeyboardButton(
                        QUALITY[i + 1].upper(),
                        callback_data=f"apply_quality#{QUALITY[i + 1]}#{search}#{req}"
                    )
                )
            btn.append(row)

        btn.append([InlineKeyboardButton("❌ Close", callback_data="close_data")])

        try:
            if query.message.text != "<b>Select Quality 👇</b>":
                await query.message.edit_text(
                    "<b>Select Quality 👇</b>",
                    reply_markup=InlineKeyboardMarkup(btn)
                )
        except MessageNotModified:
            pass
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

    # ---------------- FALLBACK ----------------
    await query.answer("Unknown action")
