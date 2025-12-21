from hydrogram import Client
from hydrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedDocument,
    InlineQuery
)

from database.ia_filterdb import get_search_results
from utils import (
    get_size,
    temp,
    get_verify_status,
    is_subscribed,
    is_premium
)
from info import CACHE_TIME, FILE_CAPTION, IS_VERIFY, MAX_BTN

cache_time = CACHE_TIME

FREE_INLINE_LIMIT = 5   # free users max results


# ======================================================
# 🚫 BAN CHECK
# ======================================================

def is_banned(query: InlineQuery):
    return query.from_user and query.from_user.id in temp.BANNED_USERS


# ======================================================
# 🔎 INLINE SEARCH
# ======================================================

@Client.on_inline_query()
async def inline_search(bot, query: InlineQuery):
    text = (query.query or "").strip()
    offset = int(query.offset or 0)
    user_id = query.from_user.id

    # ---------- Force Sub ----------
    if await is_subscribed(bot, query):
        return await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="🚫 Join required channels",
            switch_pm_parameter="inline_fsub"
        )

    # ---------- Banned ----------
    if is_banned(query):
        return await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="🚫 You are banned",
            switch_pm_parameter="start"
        )

    # ---------- Verify (Free only) ----------
    premium = await is_premium(user_id, bot)
    if IS_VERIFY and not premium:
        verify = await get_verify_status(user_id)
        if not verify.get("is_verified"):
            return await query.answer(
                results=[],
                cache_time=0,
                switch_pm_text="🔐 Daily verification required",
                switch_pm_parameter="inline_verify"
            )

    # ---------- Empty Query ----------
    if not text:
        return await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="⌨️ Type something to search",
            switch_pm_parameter="start"
        )

    # ---------- Search ----------
    limit = MAX_BTN if premium else FREE_INLINE_LIMIT
    files, next_offset, total = await get_search_results(
        text,
        offset=offset,
        max_results=limit
    )

    results = []

    for file in files:
        # 🔐 Premium-only file check
        if file.get("premium") and not premium:
            continue

        caption = FILE_CAPTION.format(
            file_name=file["file_name"],
            file_size=get_size(file["file_size"]),
            caption=file.get("caption", "")
        )

        title = file["file_name"]
        if file.get("premium"):
            title = "💎 " + title

        results.append(
            InlineQueryResultCachedDocument(
                title=title,
                document_file_id=file["_id"],
                caption=caption,
                description=f"Size: {get_size(file['file_size'])}",
                reply_markup=get_reply_markup(text, premium)
            )
        )

    # ---------- Response ----------
    if results:
        switch_text = (
            f"💎 Premium Results: {total}"
            if premium
            else f"🔓 Free Results (Limited): {len(results)}"
        )

        await query.answer(
            results=results,
            is_personal=True,
            cache_time=cache_time,
            next_offset=str(next_offset) if premium else "",
            switch_pm_text=switch_text,
            switch_pm_parameter="start"
        )
    else:
        await query.answer(
            results=[],
            is_personal=True,
            cache_time=cache_time,
            switch_pm_text=f"❌ No results for: {text}",
            switch_pm_parameter="start"
        )


# ======================================================
# 🎛 INLINE BUTTONS
# ======================================================

def get_reply_markup(query_text: str, premium: bool):
    buttons = [[
        InlineKeyboardButton(
            "🔎 Search Again",
            switch_inline_query_current_chat=query_text
        )
    ]]

    if not premium:
        buttons.append([
            InlineKeyboardButton(
                "💎 Upgrade to Premium",
                switch_inline_query_current_chat=""
            )
        ])

    return InlineKeyboardMarkup(buttons)
