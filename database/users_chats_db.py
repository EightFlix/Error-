from pymongo import MongoClient
from datetime import datetime
import time

from info import (
    BOT_ID,
    ADMINS,
    DATABASE_NAME,
    DATA_DATABASE_URL,
    VERIFY_EXPIRE
)

# =========================
# 🔗 MongoDB
# =========================
client = MongoClient(DATA_DATABASE_URL)
dbase = client[DATABASE_NAME]


class Database:

    # =========================
    # ⚙️ DEFAULT STRUCTURES
    # =========================
    default_settings = {
        "pm_search": True,
        "group_search": True,
    }

    default_verify = {
        "is_verified": False,
        "verified_time": 0,
        "verify_token": "",
        "expire_time": 0,
    }

    default_plan = {
        "premium": False,
        "plan": "free",
        "expire": None,
        "invoice": [],
        "last_reminder": None,
        "last_msg_id": None,
    }

    # =========================
    # 🧠 INIT COLLECTIONS
    # =========================
    def __init__(self):
        self.users = dbase.users
        self.groups = dbase.groups
        self.premium = dbase.premium
        self.reminders = dbase.reminders
        self.bans = dbase.bans

    # =========================
    # 👤 USERS
    # =========================
    async def is_user_exist(self, user_id: int):
        return self.users.find_one({"id": user_id}) is not None

    async def add_user(self, user_id, name):
        if not self.users.find_one({"id": user_id}):
            self.users.insert_one({
                "id": user_id,
                "name": name,
                "created_at": time.time(),
                "verify": self.default_verify.copy(),
            })

    async def total_users_count(self):
        return self.users.count_documents({})

    # =========================
    # 🚫 BANS
    # =========================
    async def get_banned_users(self):
        return self.bans.find({
            "until": {"$gt": time.time()}
        })

    async def ban_user(self, user_id, until, reason=""):
        self.bans.update_one(
            {"id": user_id},
            {"$set": {"until": until, "reason": reason}},
            upsert=True
        )

    async def unban_user(self, user_id):
        self.bans.delete_one({"id": user_id})

    # =========================
    # 👥 GROUPS
    # =========================
    async def add_group(self, chat_id, title):
        if not self.groups.find_one({"id": chat_id}):
            self.groups.insert_one({
                "id": chat_id,
                "title": title,
                "settings": self.default_settings.copy(),
            })

    async def get_settings(self, chat_id):
        g = self.groups.find_one({"id": chat_id})
        return g.get("settings", self.default_settings) if g else self.default_settings

    async def update_settings(self, chat_id, settings):
        self.groups.update_one(
            {"id": chat_id},
            {"$set": {"settings": settings}},
            upsert=True
        )

    # =========================
    # 💎 PREMIUM
    # =========================
    def get_plan(self, user_id):
        p = self.premium.find_one({"id": user_id}) or {}
        return p.get("plan", self.default_plan)

    def update_plan(self, user_id, plan):
        self.premium.update_one(
            {"id": user_id},
            {"$set": {"plan": plan}},
            upsert=True
        )

    def get_premium_users(self):
        return self.premium.find({"plan.premium": True})

    # =========================
    # ⏰ REMINDERS
    # =========================
    def get_due_reminders(self):
        return self.reminders.find({
            "sent": False,
            "remind_at": {"$lte": datetime.utcnow()}
        })

    def mark_reminder_sent(self, _id):
        self.reminders.update_one(
            {"_id": _id},
            {"$set": {"sent": True}}
        )

    # =========================
    # 📊 DB SIZE
    # =========================
    async def get_data_db_size(self):
        return dbase.command("dbstats")["dataSize"]


# =========================
# ✅ EXPORT
# =========================
db = Database()
