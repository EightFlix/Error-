from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS

# ======================================================
# 🔐 ADMIN FILTER
# ======================================================
async def admin_only(_, __, m):
    return m.from_user and m.from_user.id in ADMINS

admin_filter = filters.create(admin_only)

# ======================================================
# 🧠 RUNTIME STORAGE
# ======================================================
CONNECTED_CHAT = {}     # user_id -> chat_id
POST_DATA = {}          # user_id -> dict
WAITING_FOR = {}        # user_id -> state


# ======================================================
# 🔗 /connect <chat_id>
# ======================================================
@Client.on_message(filters.command("connect") & filters.private & admin_filter)
async def connect_chat(client, message):
    if len(message.command) != 2:
        return await message.reply(
            "❌ <b>Usage:</b>\n<code>/connect &lt;group_id / channel_id&gt;</code>"
        )

    try:
        chat_id = int(message.command[1])
        await client.get_chat(chat_id)
    except:
        return await message.reply("❌ Invalid Group / Channel ID")

    CONNECTED_CHAT[message.from_user.id] = chat_id
    await message.reply(f"✅ <b>Connected to:</b>\n<code>{chat_id}</code>")


# ======================================================
# 📮 /post PANEL
# ======================================================
@Client.on_message(filters.command("post") & filters.private & admin_filter)
async def post_panel(client, message):
    uid = message.from_user.id
    if uid not in CONNECTED_CHAT:
        return await message.reply(
            "❌ <b>No chat connected</b>\n\nUse:\n<code>/connect &lt;chat_id&gt;</code>"
        )

    buttons = [
        [InlineKeyboardButton("➕ Create New Post", callback_data="post_create")],
        [
            InlineKeyboardButton("✏️ Edit Post", callback_data="post_edit"),
            InlineKeyboardButton("📊 Channel Stats", callback_data="post_stats"),
        ],
        [InlineKeyboardButton("⚙️ Post Settings", callback_data="post_settings")],
    ]

    await message.reply(
        "📮 <b>Post Management Panel</b>\n"
        "Manage & publish posts to your connected group/channel.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ======================================================
# ➕ CREATE POST
# ======================================================
@Client.on_callback_query(filters.regex("^post_create$"))
async def post_create(client, query):
    uid = query.from_user.id
    POST_DATA[uid] = {
        "text": None,
        "buttons": [],
        "notify": True,
    }
    WAITING_FOR[uid] = "content"

    await query.message.edit(
        "✍️ <b>Send post content</b>\n"
        "• Text\n• Photo + caption\n• Video + caption"
    )


# ======================================================
# 📥 CAPTURE INPUT (CONTENT / URL BUTTONS)
# ======================================================
@Client.on_message(filters.private & admin_filter)
async def capture_input(client, message):
    uid = message.from_user.id
    if uid not in WAITING_FOR:
        return

    state = WAITING_FOR[uid]

    # -------- CONTENT --------
    if state == "content":
        POST_DATA[uid]["text"] = message.text or message.caption or ""
        WAITING_FOR.pop(uid, None)
        await show_post_options(message)

    # -------- URL BUTTONS --------
    elif state == "url_buttons":
        if message.text.lower() == "cancel":
            WAITING_FOR.pop(uid, None)
            await message.reply("❌ URL button creation cancelled.")
            return await show_post_options(message)

        buttons = parse_url_buttons_2_per_row(message.text)
        if not buttons:
            return await message.reply("❌ Invalid format. Please try again.")

        POST_DATA[uid]["buttons"] = buttons
        WAITING_FOR.pop(uid, None)

        await message.reply(
            "✅ <b>URL Buttons added</b>\nNow you can preview or send the post."
        )
        await show_post_options(message)


# ======================================================
# ⚙️ POST OPTIONS UI
# ======================================================
async def show_post_options(message):
    buttons = [
        [InlineKeyboardButton("🔗 Add URL Buttons", callback_data="post_add_url")],
        [
            InlineKeyboardButton("👀 Preview Post", callback_data="post_preview"),
            InlineKeyboardButton("📤 Send to Group/Channel", callback_data="post_send"),
        ],
        [InlineKeyboardButton("❌ Cancel Post", callback_data="post_cancel")],
    ]

    await message.reply(
        "⚙️ <b>Post Options</b>\nChoose what you want to do next.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ======================================================
# 🔗 ADD URL BUTTONS
# ======================================================
@Client.on_callback_query(filters.regex("^post_add_url$"))
async def post_add_url(client, query):
    uid = query.from_user.id
    WAITING_FOR[uid] = "url_buttons"

    await query.message.edit(
        "🔗 <b>Send URL buttons in this format:</b>\n\n"
        "<code>Button 1 - https://example.com</code>\n"
        "<code>| Button 2 - https://example2.com</code>\n"
        "<code>| Button 3 - https://example3.com</code>\n\n"
        "➡️ Buttons will appear <b>2 per row</b>\n"
        "❌ Type <b>Cancel</b> to abort."
    )


def parse_url_buttons_2_per_row(text):
    """
    Format:
    Button 1 - url
    | Button 2 - url
    | Button 3 - url
    """
    pairs = []
    for part in text.split("|"):
        if "-" not in part:
            continue
        name, url = part.split("-", 1)
        name, url = name.strip(), url.strip()
        if name and url:
            pairs.append(InlineKeyboardButton(name, url=url))

    # 2 buttons per row
    rows = []
    for i in range(0, len(pairs), 2):
        rows.append(pairs[i:i + 2])

    return rows


# ======================================================
# 👀 PREVIEW POST
# ======================================================
@Client.on_callback_query(filters.regex("^post_preview$"))
async def post_preview(client, query):
    uid = query.from_user.id
    data = POST_DATA.get(uid)
    if not data:
        return await query.answer("No post data", show_alert=True)

    await client.send_message(
        query.from_user.id,
        data["text"],
        reply_markup=InlineKeyboardMarkup(data["buttons"]) if data["buttons"] else None,
        disable_notification=not data["notify"],
    )


# ======================================================
# 📤 SEND POST
# ======================================================
@Client.on_callback_query(filters.regex("^post_send$"))
async def post_send(client, query):
    uid = query.from_user.id
    chat_id = CONNECTED_CHAT.get(uid)
    data = POST_DATA.get(uid)

    if not chat_id or not data:
        return await query.answer("❌ Missing data", show_alert=True)

    await client.send_message(
        chat_id,
        data["text"],
        reply_markup=InlineKeyboardMarkup(data["buttons"]) if data["buttons"] else None,
        disable_notification=not data["notify"],
    )

    POST_DATA.pop(uid, None)
    await query.message.edit("✅ <b>Post sent successfully!</b>")


# ======================================================
# ❌ CANCEL
# ======================================================
@Client.on_callback_query(filters.regex("^post_cancel$"))
async def post_cancel(client, query):
    uid = query.from_user.id
    POST_DATA.pop(uid, None)
    WAITING_FOR.pop(uid, None)
    await query.message.edit("❌ <b>Post creation cancelled.</b>")


# ======================================================
# 🚧 FUTURE PLACEHOLDERS
# ======================================================
@Client.on_callback_query(filters.regex("^post_edit$"))
async def post_edit(_, q):
    await q.answer("✏️ Edit feature coming soon")

@Client.on_callback_query(filters.regex("^post_stats$"))
async def post_stats(_, q):
    await q.answer("📊 Stats feature coming soon")

@Client.on_callback_query(filters.regex("^post_settings$"))
async def post_settings(_, q):
    await q.answer("⚙️ Settings feature coming soon")
