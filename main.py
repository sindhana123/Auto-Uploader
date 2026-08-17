import pyromod.listen
from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
import logging
from database import db
import os
import asyncio
from utils.job_queue import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Bot(Client):
    def __init__(self):
        super().__init__(
            "AnimeAutoUploader",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="plugins")
        )

    async def start(self):
        await super().start()
        logger.info("Bot started!")
        # Create temp folder if not exists
        if not os.path.exists("temp"):
            os.makedirs("temp")
            
        if Config.LOG_CHANNEL:
            try:
                await self.send_message(Config.LOG_CHANNEL, "🟢 **Bot Started Successfully!**")
            except Exception as e:
                logger.error(f"Failed to send startup notification to log channel: {e}")
            
        self.worker_task = asyncio.create_task(worker(self))

    async def stop(self, *args):
        logger.info("Bot stopped!")
        if hasattr(self, 'worker_task'):
            self.worker_task.cancel()
        await super().stop()

if __name__ == "__main__":
    app = Bot()
    app.run()
