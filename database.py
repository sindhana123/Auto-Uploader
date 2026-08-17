from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

class Database:
    def __init__(self, uri, database_name):
        self._client = AsyncIOMotorClient(uri, tlsAllowInvalidCertificates=True)
        self.db = self._client[database_name]
        self.users = self.db.users
        self.channels = self.db.channels
        
    async def get_user_state(self, user_id):
        user = await self.users.find_one({"_id": user_id})
        if not user:
            return {"mode": "normal", "current_job": {}, "waiting_for": None}
        state = user.get("state", {"mode": "normal", "current_job": {}})
        if "waiting_for" not in state:
            state["waiting_for"] = None
        return state
        
    async def update_user_state(self, user_id, state_dict):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"state": state_dict}},
            upsert=True
        )

    async def set_current_job_audio(self, user_id, audio_msg_dict):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"state.current_job.audio_msg": audio_msg_dict}},
            upsert=True
        )

    async def push_current_job_video(self, user_id, video_msg_dict):
        await self.users.update_one(
            {"_id": user_id},
            {"$push": {"state.current_job.video_msgs": video_msg_dict}},
            upsert=True
        )

    async def get_user_settings(self, user_id):
        user = await self.users.find_one({"_id": user_id})
        default_settings = {
            "thumbnail": None,
            "rename_format": "{anime} - S{season:02d}E{episode:02d} [{language}] {quality} @Suffix.mkv",
            "caption_format": "<b>{filename}</b>",
            "prefix": "",
            "suffix": "",
            "upload_type": "document",
            "button_mode": "off",
            "filestore_username": "",
            "dump_channel_id": "",
            "auto_channel_match": "on",
            "process_mode": "merge",
            "button_post_format": "<b>{anime} | Tamil Dubbed #Official</b>\n\n<b>Season : {season} | Episode : {episode}</b>\n\n<b>‼️Note - Click The Below Button to Get Episodes 👇</b>"
        }
        if not user:
            return default_settings
        settings = user.get("settings", {})
        
        # Migrate legacy button upload type
        if settings.get("upload_type") == "button":
            settings["upload_type"] = "document"
            settings["button_mode"] = "on"
            
        for k, v in default_settings.items():
            if k not in settings:
                settings[k] = v
        return settings

    async def update_user_settings(self, user_id, key, value):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {f"settings.{key}": value}},
            upsert=True
        )
        
    async def update_full_settings(self, user_id, settings_dict):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"settings": settings_dict}},
            upsert=True
        )

    async def add_channel(self, user_id, channel_id, channel_title, link, hint):
        await self.channels.insert_one({
            "user_id": user_id, 
            "channel_id": channel_id, 
            "title": channel_title,
            "link": link, 
            "hint": hint.lower()
        })

    async def get_channels(self, user_id):
        return await self.channels.find({"user_id": user_id}).to_list(length=100)

    async def remove_channel(self, db_id):
        from bson.objectid import ObjectId
        await self.channels.delete_one({"_id": ObjectId(db_id)})

    async def match_channel(self, user_id, anime_name):
        channels = await self.get_channels(user_id)
        for ch in channels:
            if ch['hint'] in anime_name.lower():
                return ch
        return None

    async def is_user_authorized(self, user_id):
        if user_id in Config.OWNERS:
            return True
        user = await self.users.find_one({"_id": user_id})
        if user and user.get("authorized", False):
            return True
        return False

    async def authorize_user(self, user_id):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"authorized": True}},
            upsert=True
        )

    async def unauthorize_user(self, user_id):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"authorized": False}},
            upsert=True
        )

    async def is_user_admin(self, user_id):
        if user_id in Config.OWNERS:
            return True
        user = await self.users.find_one({"_id": user_id})
        if user and user.get("is_admin", False):
            return True
        return False

    async def add_admin(self, user_id):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"is_admin": True, "authorized": True}},
            upsert=True
        )

    async def remove_admin(self, user_id):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"is_admin": False}}
        )

db = Database(Config.MONGO_URI, "AnimeAutoUploader")
