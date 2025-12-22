from pymongo import MongoClient
from pymongo.errors import PyMongoError
from datetime import datetime
import time
import asyncio
from functools import wraps

from info import (
    BOT_ID,
    ADMINS,
    DATABASE_NAME,
    DATA_DATABASE_URL,
    VERIFY_EXPIRE
)

# =========================
# 🔗 MongoDB Connection
# =========================
try:
    client = MongoClient(
        DATA_DATABASE_URL,
        serverSelectionTimeoutMS=5000,  # 5 sec timeout
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
        maxPoolSize=50,
        retryWrites=True
    )
    # Test connection
    client.server_info()
    dbase = client[DATABASE_NAME]
    print("✅ Database connected successfully")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    dbase = None


# =========================
# 🛡️ Async Wrapper for Sync Operations
# =========================
def run_sync(func):
    """Wrapper to run sync MongoDB operations in executor"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper


class Database:

    # =========================
    # ⚙️ DEFAULT STRUCTURES
    # =========================
    default_settings = {
        "pm_search": True,
        "group_search": True,
        "auto_delete": False,
        "anti_link": False,
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

    default_warn = {
        "count": 0,
        "last_warn": 0,
    }

    # =========================
    # 🧠 INIT COLLECTIONS
    # =========================
    def __init__(self):
        if not dbase:
            raise Exception("Database not initialized")
        
        self.users = dbase.users
        self.groups = dbase.groups
        self.premium = dbase.premium
        self.reminders = dbase.reminders
        self.bans = dbase.bans
        self.warns = dbase.warns
        
        # Create indexes for better performance
        self._create_indexes()

    def _create_indexes(self):
        """Create indexes for faster queries"""
        try:
            self.users.create_index("id", unique=True)
            self.groups.create_index("id", unique=True)
            self.bans.create_index("id")
            self.bans.create_index("until")
            self.warns.create_index([("user_id", 1), ("chat_id", 1)])
            self.premium.create_index("id")
            self.reminders.create_index([("sent", 1), ("remind_at", 1)])
        except:
            pass

    # =========================
    # 👤 USERS
    # =========================
    async def is_user_exist(self, user_id: int):
        """Check if user exists"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self.users.find_one({"id": user_id})
            )
            return result is not None
        except Exception as e:
            print(f"Error checking user: {e}")
            return False

    async def add_user(self, user_id: int, name: str):
        """Add new user to database"""
        try:
            if await self.is_user_exist(user_id):
                return False
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.users.insert_one({
                    "id": user_id,
                    "name": name,
                    "created_at": time.time(),
                    "verify": self.default_verify.copy(),
                })
            )
            return True
        except Exception as e:
            print(f"Error adding user: {e}")
            return False

    async def total_users_count(self):
        """Get total users count"""
        try:
            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(
                None,
                self.users.count_documents,
                {}
            )
            return count
        except Exception as e:
            print(f"Error counting users: {e}")
            return 0

    async def get_all_users(self):
        """Get all users (for broadcast)"""
        try:
            loop = asyncio.get_event_loop()
            users = await loop.run_in_executor(
                None,
                lambda: list(self.users.find({}))
            )
            return users
        except Exception as e:
            print(f"Error getting users: {e}")
            return []

    # =========================
    # 🚫 BANS
    # =========================
    async def get_banned_users(self):
        """Get all currently banned users"""
        try:
            loop = asyncio.get_event_loop()
            bans = await loop.run_in_executor(
                None,
                lambda: list(self.bans.find({"until": {"$gt": time.time()}}))
            )
            return bans
        except Exception as e:
            print(f"Error getting bans: {e}")
            return []

    async def ban_user(self, user_id: int, until: float, reason: str = ""):
        """Ban a user"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.bans.update_one(
                    {"id": user_id},
                    {"$set": {
                        "until": until,
                        "reason": reason,
                        "banned_at": time.time()
                    }},
                    upsert=True
                )
            )
            return True
        except Exception as e:
            print(f"Error banning user: {e}")
            return False

    async def unban_user(self, user_id: int):
        """Unban a user"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.bans.delete_one({"id": user_id})
            )
            return True
        except Exception as e:
            print(f"Error unbanning user: {e}")
            return False

    async def get_ban_status(self, user_id: int):
        """Check if user is banned"""
        try:
            loop = asyncio.get_event_loop()
            ban = await loop.run_in_executor(
                None,
                lambda: self.bans.find_one({"id": user_id})
            )
            
            if not ban:
                return {"status": False, "reason": ""}

            # Auto remove expired ban
            if ban.get("until", 0) <= time.time():
                await self.unban_user(user_id)
                return {"status": False, "reason": ""}

            return {
                "status": True,
                "reason": ban.get("reason", ""),
                "until": ban.get("until")
            }
        except Exception as e:
            print(f"Error checking ban status: {e}")
            return {"status": False, "reason": ""}

    # =========================
    # 👥 GROUPS
    # =========================
    async def add_group(self, chat_id: int, title: str):
        """Add new group to database"""
        try:
            loop = asyncio.get_event_loop()
            exists = await loop.run_in_executor(
                None,
                lambda: self.groups.find_one({"id": chat_id})
            )
            
            if exists:
                return False
            
            await loop.run_in_executor(
                None,
                lambda: self.groups.insert_one({
                    "id": chat_id,
                    "title": title,
                    "settings": self.default_settings.copy(),
                    "joined_at": time.time()
                })
            )
            return True
        except Exception as e:
            print(f"Error adding group: {e}")
            return False

    async def get_settings(self, chat_id: int):
        """Get group settings"""
        try:
            loop = asyncio.get_event_loop()
            group = await loop.run_in_executor(
                None,
                lambda: self.groups.find_one({"id": chat_id})
            )
            
            if group and "settings" in group:
                # Merge with defaults to ensure all keys exist
                settings = self.default_settings.copy()
                settings.update(group["settings"])
                return settings
            
            return self.default_settings.copy()
        except Exception as e:
            print(f"Error getting settings: {e}")
            return self.default_settings.copy()

    async def update_settings(self, chat_id: int, settings: dict):
        """Update group settings"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.groups.update_one(
                    {"id": chat_id},
                    {"$set": {"settings": settings}},
                    upsert=True
                )
            )
            return True
        except Exception as e:
            print(f"Error updating settings: {e}")
            return False

    async def total_groups_count(self):
        """Get total groups count"""
        try:
            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(
                None,
                self.groups.count_documents,
                {}
            )
            return count
        except Exception as e:
            print(f"Error counting groups: {e}")
            return 0

    # =========================
    # ⚠️ WARNS (NEW)
    # =========================
    async def get_warn(self, user_id: int, chat_id: int):
        """Get user warning data"""
        try:
            loop = asyncio.get_event_loop()
            warn = await loop.run_in_executor(
                None,
                lambda: self.warns.find_one({
                    "user_id": user_id,
                    "chat_id": chat_id
                })
            )
            
            if warn:
                return {
                    "count": warn.get("count", 0),
                    "last_warn": warn.get("last_warn", 0)
                }
            return None
        except Exception as e:
            print(f"Error getting warn: {e}")
            return None

    async def set_warn(self, user_id: int, chat_id: int, data: dict):
        """Set user warning data"""
        try:
            data["last_warn"] = time.time()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.warns.update_one(
                    {"user_id": user_id, "chat_id": chat_id},
                    {"$set": data},
                    upsert=True
                )
            )
            return True
        except Exception as e:
            print(f"Error setting warn: {e}")
            return False

    async def clear_warn(self, user_id: int, chat_id: int):
        """Clear user warnings"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.warns.delete_one({
                    "user_id": user_id,
                    "chat_id": chat_id
                })
            )
            return True
        except Exception as e:
            print(f"Error clearing warn: {e}")
            return False

    async def get_user_warns_count(self, user_id: int, chat_id: int):
        """Get warning count for user"""
        try:
            warn_data = await self.get_warn(user_id, chat_id)
            return warn_data["count"] if warn_data else 0
        except:
            return 0

    # =========================
    # 💎 PREMIUM
    # =========================
    async def get_plan(self, user_id: int):
        """Get user premium plan"""
        try:
            loop = asyncio.get_event_loop()
            premium = await loop.run_in_executor(
                None,
                lambda: self.premium.find_one({"id": user_id})
            )
            
            if premium and "plan" in premium:
                return premium["plan"]
            
            return self.default_plan.copy()
        except Exception as e:
            print(f"Error getting plan: {e}")
            return self.default_plan.copy()

    async def update_plan(self, user_id: int, plan: dict):
        """Update user premium plan"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.premium.update_one(
                    {"id": user_id},
                    {"$set": {"plan": plan}},
                    upsert=True
                )
            )
            return True
        except Exception as e:
            print(f"Error updating plan: {e}")
            return False

    async def get_premium_users(self):
        """Get all premium users"""
        try:
            loop = asyncio.get_event_loop()
            users = await loop.run_in_executor(
                None,
                lambda: list(self.premium.find({"plan.premium": True}))
            )
            return users
        except Exception as e:
            print(f"Error getting premium users: {e}")
            return []

    # =========================
    # ⏰ REMINDERS
    # =========================
    async def get_due_reminders(self):
        """Get reminders that are due"""
        try:
            loop = asyncio.get_event_loop()
            reminders = await loop.run_in_executor(
                None,
                lambda: list(self.reminders.find({
                    "sent": False,
                    "remind_at": {"$lte": datetime.utcnow()}
                }))
            )
            return reminders
        except Exception as e:
            print(f"Error getting reminders: {e}")
            return []

    async def mark_reminder_sent(self, reminder_id):
        """Mark reminder as sent"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.reminders.update_one(
                    {"_id": reminder_id},
                    {"$set": {"sent": True, "sent_at": datetime.utcnow()}}
                )
            )
            return True
        except Exception as e:
            print(f"Error marking reminder: {e}")
            return False

    # =========================
    # 📊 DB STATS
    # =========================
    async def get_data_db_size(self):
        """Get database size"""
        try:
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(
                None,
                lambda: dbase.command("dbstats")
            )
            return stats.get("dataSize", 0)
        except Exception as e:
            print(f"Error getting db size: {e}")
            return 0

    async def get_db_stats(self):
        """Get comprehensive database stats"""
        try:
            users = await self.total_users_count()
            groups = await self.total_groups_count()
            size = await self.get_data_db_size()
            
            return {
                "users": users,
                "groups": groups,
                "size": size,
                "size_mb": round(size / (1024 * 1024), 2)
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {
                "users": 0,
                "groups": 0,
                "size": 0,
                "size_mb": 0
            }

    # =========================
    # 🧹 CLEANUP
    # =========================
    async def cleanup_expired_bans(self):
        """Remove expired bans"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.bans.delete_many({
                    "until": {"$lte": time.time()}
                })
            )
            return result.deleted_count
        except Exception as e:
            print(f"Error cleaning bans: {e}")
            return 0

    async def cleanup_old_warns(self, days: int = 30):
        """Remove warnings older than specified days"""
        try:
            cutoff = time.time() - (days * 86400)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.warns.delete_many({
                    "last_warn": {"$lt": cutoff}
                })
            )
            return result.deleted_count
        except Exception as e:
            print(f"Error cleaning warns: {e}")
            return 0


# =========================
# ✅ EXPORT
# =========================
db = Database()
