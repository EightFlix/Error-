import logging

# ==========================
# 🔥 LOGGING CONFIG (KOYEB FRIENDLY)
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logging.getLogger("hydrogram").setLevel(logging.ERROR)
logger = logging.getLogger("XFILER")


import os
import time
import asyncio
import uvloop
from datetime import datetime
import pytz

from hydrogram import Client, filters
from aiohttp import web

from web import web_app
from info import API_ID, API_HASH, BOT_TOKEN, PORT, LOG_CHANNEL, ADMINS

from utils import (
    temp,
    cleanup_files_memory,
    premium_expiry_reminder
)

from database.users_chats_db import db
from plugins.banned import auto_unban_worker


# ==========================
# 🕒 TIME UTILS
# ==========================
IST = pytz.timezone("Asia/Kolkata")

def ist_time():
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p")


# ==========================
# 🧪 GLOBAL DEBUG: /START LOGGER
# ==========================
@Client.on_message(filters.private & filters.command("start"))
async def debug_start_logger(client, message):
    logger.warning(
        f"/START HIT | user={message.from_user.id} | text='{message.text}'"
    )
    # ⚠️ DO NOT reply, DO NOT delete here
    # This is ONLY for logs


# ==========================
# 🤖 BOT CLASS
# ==========================
class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Auto_Filter_Bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins={"root": "plugins"}
        )

    async def start(self):
        await super().start()

        # ---- runtime globals ----
        temp.START_TIME = time.time()
        temp.BOT = self

        # ---- restart notify ----
        if os.path.exists("restart.txt"):
            try:
                with open("restart.txt") as f:
                    cid, mid = map(int, f.read().split())
                    await self.edit_message_text(
                        cid, mid, "✅ Bot Restarted Successfully!"
                    )
            except:
                pass
            os.remove("restart.txt")

        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name

        # ---- web server ----
        runner = web.AppRunner(web_app)
        await runner.setup()
        await web.TCPSite(
            runner,
            host="0.0.0.0",
            port=PORT
        ).start()

        # ==========================
        # 🔁 BACKGROUND TASKS
        # ==========================

        # 🔥 FILE MEMORY LEAK GUARD
        asyncio.create_task(cleanup_files_memory())

        # 🔔 PREMIUM EXPIRY REMINDER
        asyncio.create_task(premium_expiry_reminder(self))

        # 🚫 AUTO UNBAN WORKER
        asyncio.create_task(auto_unban_worker(self))

        # ---- admin notify ----
        for admin in ADMINS:
            try:
                await self.send_message(
                    admin,
                    "♻️ **Bot Restarted Successfully**\n\n"
                    f"🕒 Time: {ist_time()}\n"
                    "🤖 Status: Online & Stable"
                )
            except:
                pass

        # ---- log channel ----
        try:
            await self.send_message(
                LOG_CHANNEL,
                f"🤖 <b>@{me.username} started successfully</b>\n"
                f"🕒 {ist_time()}"
            )
        except:
            pass

        logger.info(f"Bot @{me.username} started successfully")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped cleanly")


# ==========================
# 🚀 ENTRYPOINT
# ==========================
async def main():
    uvloop.install()
    bot = Bot()
    try:
        await bot.start()
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
