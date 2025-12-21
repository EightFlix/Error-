import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logging.getLogger("hydrogram").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

import os
import time
import asyncio
import uvloop
from datetime import datetime
import pytz

from hydrogram import Client
from aiohttp import web

from web import web_app
from info import API_ID, API_HASH, BOT_TOKEN, PORT, LOG_CHANNEL, ADMINS
from utils import temp, check_premium
from database.users_chats_db import db


# ==========================
# 🕒 TIME UTILS
# ==========================
IST = pytz.timezone("Asia/Kolkata")

def ist_time():
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p")


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

        # ---- runtime info ----
        temp.START_TIME = time.time()
        temp.BOT = self

        # ---- restart notify ----
        if os.path.exists("restart.txt"):
            with open("restart.txt") as f:
                try:
                    cid, mid = map(int, f.read().split())
                    await self.edit_message_text(cid, mid, "✅ Bot Restarted Successfully!")
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
        await web.TCPSite(runner, "0.0.0.0", PORT).start()

        # ---- background safety task ----
        asyncio.create_task(check_premium(self))

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

        logger.info(f"Bot @{me.username} started")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped")


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
