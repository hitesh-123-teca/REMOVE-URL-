"""
MongoDB database operations
"""

import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId

from pymongo import MongoClient, IndexModel, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, ConnectionFailure

from config import Config

class MongoDB:
    """MongoDB database handler"""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.connect()
        
    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(
                Config.MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            self.db = self.client[Config.DATABASE_NAME]
            self._create_collections()
            self._create_indexes()
            
            print(f"✅ Connected to MongoDB: {Config.DATABASE_NAME}")
            
        except ConnectionFailure as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
            
    def _create_collections(self):
        """Create necessary collections"""
        collections = ["settings", "files", "stats", "users", "channels"]
        
        for collection in collections:
            if collection not in self.db.list_collection_names():
                self.db.create_collection(collection)
                print(f"📁 Created collection: {collection}")
                
    def _create_indexes(self):
        """Create database indexes"""
        # Files collection indexes
        files_indexes = [
            IndexModel([("file_id", ASCENDING)], unique=True),
            IndexModel([("file_hash", ASCENDING)]),
            IndexModel([("chat_id", ASCENDING)]),
            IndexModel([("timestamp", DESCENDING)]),
            IndexModel([("file_size", ASCENDING)])
        ]
        
        self.db.files.create_indexes(files_indexes)
        
        # Settings collection indexes
        settings_indexes = [
            IndexModel([("bot_id", ASCENDING)], unique=True),
            IndexModel([("key", ASCENDING)], unique=True)
        ]
        
        self.db.settings.create_indexes(settings_indexes)
        
        # Stats collection indexes
        stats_indexes = [
            IndexModel([("date", ASCENDING)], unique=True),
            IndexModel([("chat_id", ASCENDING)])
        ]
        
        self.db.stats.create_indexes(stats_indexes)
        
    # ========== SETTIONS OPERATIONS ==========
    
    def get_bot_settings(self, bot_id: int) -> Dict:
        """Get bot settings"""
        settings = self.db.settings.find_one({"bot_id": bot_id})
        return settings or {}
    
    def update_bot_settings(self, bot_id: int, updates: Dict):
        """Update bot settings"""
        self.db.settings.update_one(
            {"bot_id": bot_id},
            {"$set": updates},
            upsert=True
        )
        
    def get_setting(self, key: str, default=None):
        """Get a specific setting"""
        setting = self.db.settings.find_one({"key": key})
        return setting.get("value", default) if setting else default
        
    def set_setting(self, key: str, value: Any):
        """Set a specific setting"""
        self.db.settings.update_one(
            {"key": key},
            {"$set": {"value": value, "updated_at": datetime.now()}},
            upsert=True
        )
        
    # ========== FILE OPERATIONS ==========
    
    def save_file(self, file_data: Dict) -> bool:
        """Save file information"""
        try:
            self.db.files.insert_one(file_data)
            return True
        except DuplicateKeyError:
            # Update existing record
            self.db.files.update_one(
                {"file_id": file_data["file_id"]},
                {"$set": file_data}
            )
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            return False
            
    def find_file_by_hash(self, file_hash: str) -> Optional[Dict]:
        """Find file by hash"""
        return self.db.files.find_one({"file_hash": file_hash})
        
    def find_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Find file by Telegram file_id"""
        return self.db.files.find_one({"file_id": file_id})
        
    def delete_file(self, file_id: str) -> bool:
        """Delete file record"""
        result = self.db.files.delete_one({"file_id": file_id})
        return result.deleted_count > 0
        
    def get_file_count(self, chat_id: str = None) -> int:
        """Get total file count"""
        query = {}
        if chat_id:
            query["chat_id"] = chat_id
        return self.db.files.count_documents(query)
        
    # ========== STATISTICS ==========
    
    def update_stats(self, chat_id: str = None):
        """Update statistics"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Update daily stats
        self.db.stats.update_one(
            {"date": today, "chat_id": chat_id},
            {"$inc": {"file_count": 1}},
            upsert=True
        )
        
        # Update total stats
        self.db.stats.update_one(
            {"date": "total", "chat_id": chat_id},
            {"$inc": {"file_count": 1}},
            upsert=True
        )
        
    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        """Get statistics for last N days"""
        start_date = datetime.now() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"date": {"$gte": start_date}, "date": {"$ne": "total"}}},
            {"$group": {
                "_id": "$date",
                "total_files": {"$sum": "$file_count"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        return list(self.db.stats.aggregate(pipeline))
        
    def get_total_stats(self) -> Dict:
        """Get total statistics"""
        total = self.db.stats.find_one({"date": "total"})
        return {
            "total_files": total.get("file_count", 0) if total else 0,
            "total_chats": len(self.db.stats.distinct("chat_id", {"date": "total"}))
        }
        
    # ========== CHANNEL OPERATIONS ==========
    
    def save_channel(self, channel_data: Dict):
        """Save channel information"""
        self.db.channels.update_one(
            {"chat_id": channel_data["chat_id"]},
            {"$set": channel_data},
            upsert=True
        )
        
    def get_channel(self, chat_id: str) -> Optional[Dict]:
        """Get channel information"""
        return self.db.channels.find_one({"chat_id": chat_id})
        
    def get_all_channels(self) -> List[Dict]:
        """Get all channels"""
        return list(self.db.channels.find())
        
    # ========== USER OPERATIONS ==========
    
    def save_user(self, user_data: Dict):
        """Save user information"""
        self.db.users.update_one(
            {"user_id": user_data["user_id"]},
            {"$set": user_data},
            upsert=True
        )
        
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information"""
        return self.db.users.find_one({"user_id": user_id})
        
    # ========== UTILITY METHODS ==========
    
    def cleanup_old_files(self, days: int = 30):
        """Cleanup files older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        result = self.db.files.delete_many({
            "timestamp": {"$lt": cutoff_date}
        })
        
        return result.deleted_count
        
    def generate_file_hash(self, file_path: str) -> str:
        """Generate MD5 hash for file"""
        hash_md5 = hashlib.md5()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
                
        return hash_md5.hexdigest()
        
    def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
