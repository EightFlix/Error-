import logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logging.getLogger('hydrogram').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

import os
import time
import asyncio
import uvloop
import sys
from hydrogram import types
from hydrogram import Client
from hydrogram.errors import FloodWait
from aiohttp import web
from typing import Union, Optional, AsyncGenerator
from web import web_app
from info import INDEX_CHANNELS, SUPPORT_GROUP, LOG_CHANNEL, API_ID, DATA_DATABASE_URL, API_HASH, BOT_TOKEN, PORT, BIN_CHANNEL, ADMINS, SECOND_FILES_DATABASE_URL, FILES_DATABASE_URL
from utils import temp, get_readable_time, check_premium
from database.users_chats_db import db

class Bot(Client):
    def __init__(self):
        super().__init__(
            name='Auto_Filter_Bot',
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins={"root": "plugins"}
        )

    async def start(self):
        await super().start()
        temp.START_TIME = time.time()
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats

        if os.path.exists('restart.txt'):
            with open("restart.txt") as file:
                try:
                    chat_id, msg_id = map(int, file.read().split())
                    await self.edit_message_text(chat_id=chat_id, message_id=msg_id, text='Restarted Successfully!')
                except Exception as e:
                    logger.error(f"Restart file error: {e}")
            os.remove('restart.txt')

        temp.BOT = self
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        
        # Web Server Setup
        app = web.AppRunner(web_app)
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()

        asyncio.create_task(check_premium(self))
        try:
            await self.send_message(chat_id=LOG_CHANNEL, text=f"<b>{me.mention} Restarted! 🤖</b>")
        except:
            logger.error("Make sure bot admin in LOG_CHANNEL")
            
        logger.info(f"@{me.username} is started now ✓")

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot Stopped! Bye...")

    async def iter_messages(self: Client, chat_id: Union[int, str], limit: int, offset: int = 0) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            messages = await self.get_messages(chat_id, list(range(current, current+new_diff+1)))
            for message in messages:
                yield message
                current += 1

async def main():
    # Koyeb/Linux सर्वर्स के लिए uvloop को यहाँ इनिशियलाइज करें
    uvloop.install()
    bot = Bot()
    try:
        await bot.start()
        # बॉट को चालू रखने के लिए (Idle mode)
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        await bot.stop()

if __name__ == "__main__":
    try:
        # asyncio.run() इवेंट लूप को सही से हैंडल करता है
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

