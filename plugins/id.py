import io
import zipfile
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from hydrogram.file_id import FileId
from info import ADMINS


# =====================================================
# 🆔 /id
# =====================================================
@Client.on_message(filters.command("id"))
async def id_handler(client, message):
    if message.reply_to_message:
        r = message.reply_to_message

        if r.from_user:
            return await message.reply(
                f"👤 <b>User ID</b>\n<code>{r.from_user.id}</code>"
            )

        if r.sticker:
            st = r.sticker
            fid = FileId.decode(st.file_id)

            text = (
                "🧩 <b>Sticker Info</b>\n\n"
                f"• File ID:\n<code>{st.file_id}</code>\n\n"
                f"• Unique ID: <code>{st.file_unique_id}</code>\n"
                f"• Emoji: {st.emoji or 'None'}\n"
                f"• Animated: {st.is_animated}\n"
                f"• Video: {st.is_video}\n"
                f"• DC: <code>{fid.dc_id}</code>"
            )

            btn = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬇️ Download",
                            callback_data=f"dl_sticker#{st.file_id}"
                        ),
                        InlineKeyboardButton(
                            "🖼 PNG",
                            callback_data=f"png_sticker#{st.file_id}"
                        )
                    ]
                ]
            )

            return await message.reply(text, reply_markup=btn)

    await message.reply(
        f"👤 <b>Your ID</b>\n<code>{message.from_user.id}</code>\n\n"
        f"💬 <b>Chat ID</b>\n<code>{message.chat.id}</code>"
    )


# =====================================================
# 🧩 /stickerid
# =====================================================
@Client.on_message(filters.command("stickerid") & filters.reply)
async def stickerid_handler(client, message):
    if not message.reply_to_message or not message.reply_to_message.sticker:
        return await message.reply("❌ Reply to a sticker.")

    st = message.reply_to_message.sticker
    fid = FileId.decode(st.file_id)

    await message.reply(
        f"🧩 <b>Sticker ID</b>\n\n"
        f"• File ID:\n<code>{st.file_id}</code>\n\n"
        f"• Unique ID: <code>{st.file_unique_id}</code>\n"
        f"• Emoji: {st.emoji}\n"
        f"• DC: <code>{fid.dc_id}</code>"
    )


# =====================================================
# 📦 /stickerset
# =====================================================
@Client.on_message(filters.command("stickerset") & filters.reply)
async def stickerset_handler(client, message):
    r = message.reply_to_message
    if not r or not r.sticker or not r.sticker.set_name:
        return await message.reply("❌ Reply to a sticker.")

    s = await client.get_sticker_set(r.sticker.set_name)

    btn = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📦 Download ZIP (Admin)",
                    callback_data=f"zip_set#{s.name}"
                )
            ]
        ]
    )

    await message.reply(
        f"📦 <b>Sticker Set</b>\n\n"
        f"• Title: <b>{s.title}</b>\n"
        f"• Name: <code>{s.name}</code>\n"
        f"• Stickers: <code>{len(s.stickers)}</code>\n"
        f"• Animated: {s.is_animated}\n"
        f"• Video: {s.is_video}",
        reply_markup=btn
    )


# =====================================================
# ⬇️ STICKER DOWNLOAD
# =====================================================
@Client.on_callback_query(filters.regex("^dl_sticker#"))
async def download_sticker(client, query):
    file_id = query.data.split("#", 1)[1]
    await query.answer("Downloading...")
    await client.send_cached_media(query.message.chat.id, file_id)


# =====================================================
# 🖼 STICKER → PNG
# =====================================================
@Client.on_callback_query(filters.regex("^png_sticker#"))
async def sticker_to_png(client, query):
    file_id = query.data.split("#", 1)[1]
    await query.answer("Converting to PNG...")

    msg = await client.send_cached_media(
        query.message.chat.id,
        file_id
    )

    if msg.sticker:
        await msg.reply_document(
            msg.sticker.file_id,
            file_name="sticker.png"
        )


# =====================================================
# 📦 STICKER PACK → ZIP (ADMIN ONLY)
# =====================================================
@Client.on_callback_query(filters.regex("^zip_set#"))
async def zip_sticker_set(client, query: CallbackQuery):
    if query.from_user.id not in ADMINS:
        return await query.answer("Admins only", show_alert=True)

    set_name = query.data.split("#", 1)[1]
    await query.answer("Creating ZIP...")

    s = await client.get_sticker_set(set_name)

    zip_io = io.BytesIO()
    zip_io.name = f"{set_name}.zip"

    with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zipf:
        for i, st in enumerate(s.stickers, start=1):
            file = await client.download_media(st.file_id, in_memory=True)
            ext = "webp"
            zipf.writestr(f"{i}_{st.file_unique_id}.{ext}", file.getvalue())

    zip_io.seek(0)

    await client.send_document(
        query.message.chat.id,
        zip_io,
        caption=f"📦 Sticker Pack ZIP\n\n<b>{s.title}</b>"
    )
