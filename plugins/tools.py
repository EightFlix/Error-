import os
import aiohttp
import asyncio
import time
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from info import ADMINS
from utils import temp, is_premium

# =========================
# GLOBAL STATE (LIGHT)
# =========================
UPLOAD_QUEUE = asyncio.Lock()
UPLOAD_PANEL = {}   # user_id -> state

GOFILE_API = "https://store1.gofile.io/contents/uploadfile"

# =========================
# HELPERS
# =========================

def panel_buttons(state):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"🔒 Private {'✅' if state['private'] else '❌'}",
                callback_data="up#private"
            ),
            InlineKeyboardButton(
                f"🔁 Mirror {'✅' if state['mirror'] else '❌'}",
                callback_data="up#mirror"
            )
        ],
        [
            InlineKeyboardButton("🗑 Auto Delete 10m", callback_data="up#del#600"),
            InlineKeyboardButton("🗑 Auto Delete 30m", callback_data="up#del#1800")
        ],
        [
            InlineKeyboardButton("🚀 Start Upload", callback_data="up#start"),
            InlineKeyboardButton("❌ Cancel", callback_data="up#cancel")
        ]
    ])

async def delete_after(bot, chat_id, msg_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, msg_id)
    except:
        pass

# =========================
# ADMIN UPLOAD PANEL
# =========================

@Client.on_message(filters.command("upload") & filters.private)
async def upload_panel(bot, message):
    uid = message.from_user.id

    if uid not in ADMINS and not await is_premium(uid, bot):
        return await message.reply("❌ Uploads are Premium-only.")

    UPLOAD_PANEL[uid] = {
        "private": False,
        "mirror": False,
        "delete": 0
    }

    await message.reply(
        "📤 **Admin Upload Panel**\n\n"
        "Reply to a file, configure options, then start upload.",
        reply_markup=panel_buttons(UPLOAD_PANEL[uid])
    )

@Client.on_callback_query(filters.regex("^up#"))
async def upload_panel_cb(bot, query: CallbackQuery):
    uid = query.from_user.id
    if uid not in UPLOAD_PANEL:
        return await query.answer("Session expired", show_alert=True)

    state = UPLOAD_PANEL[uid]
    data = query.data.split("#")

    if data[1] == "private":
        state["private"] = not state["private"]

    elif data[1] == "mirror":
        state["mirror"] = not state["mirror"]

    elif data[1] == "del":
        state["delete"] = int(data[2])

    elif data[1] == "cancel":
        UPLOAD_PANEL.pop(uid, None)
        return await query.message.edit("❌ Upload cancelled.")

    elif data[1] == "start":
        if not query.message.reply_to_message:
            return await query.answer("Reply to a file first", show_alert=True)

        await query.message.edit("⏳ Upload queued...")
        asyncio.create_task(start_upload(bot, query, state))
        return

    await query.message.edit_reply_markup(
        reply_markup=panel_buttons(state)
    )
    await query.answer()

# =========================
# UPLOAD LOGIC
# =========================

async def start_upload(bot, query: CallbackQuery, state):
    async with UPLOAD_QUEUE:
        msg = query.message
        reply = msg.reply_to_message
        path = await reply.download()

        status = await msg.edit("⚡ Uploading to GoFile...")

        try:
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field("file", open(path, "rb"))

                async with session.post(GOFILE_API, data=data) as r:
                    res = await r.json()

            if res.get("status") != "ok":
                return await status.edit("❌ Upload failed.")

            link = res["data"]["downloadPage"]

            # MIRROR (optional)
            if state["mirror"]:
                status = await status.edit("🔁 Mirroring to Transfer.sh...")
                async with aiohttp.ClientSession() as session:
                    with open(path, "rb") as f:
                        async with session.put(
                            f"https://transfer.sh/{os.path.basename(path)}",
                            data=f
                        ) as r:
                            if r.status == 200:
                                mirror = (await r.text()).strip()
                                link += f"\n\n🔁 Mirror:\n{mirror}"

            final = await status.edit(
                f"✅ **Upload Complete**\n\n<code>{link}</code>",
                disable_web_page_preview=True
            )

            # AUTO DELETE
            if state["delete"]:
                asyncio.create_task(
                    delete_after(bot, final.chat.id, final.id, state["delete"])
                )

        except Exception as e:
            await status.edit(f"❌ Error: {e}")

        finally:
            if os.path.exists(path):
                os.remove(path)
            UPLOAD_PANEL.pop(query.from_user.id, None)
