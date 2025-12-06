"""
Database operations using MongoDB
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from bson import ObjectId

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Handles all MongoDB operations"""
    
    def __init__(self, mongo_uri: str, db_name: str = "url_remover_bot"):
        """Initialize MongoDB connection"""
        self.client = None
        self.db = None
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.connect()
    
    def connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            self.db = self.client[self.db_name]
            
            # Initialize collections
            self._init_collections()
            self._create_indexes()
            
            logger.info(f"✅ Connected to MongoDB: {self.db_name}")
            
        except ConnectionFailure as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ MongoDB connection error: {e}")
            raise
    
    def _init_collections(self):
        """Initialize collections if they don't exist"""
        collections = ['users', 'files', 'stats', 'settings', 'logs']
        
        for collection_name in collections:
            if collection_name not in self.db.list_collection_names():
                self.db.create_collection(collection_name)
                logger.info(f"📁 Created collection: {collection_name}")
    
    def _create_indexes(self):
        """Create necessary database indexes"""
        
        # Users collection
        self.db.users.create_index([("user_id", ASCENDING)], unique=True)
        self.db.users.create_index([("username", ASCENDING)])
        self.db.users.create_index([("join_date", DESCENDING)])
        
        # Files collection
        self.db.files.create_index([("file_hash", ASCENDING)], unique=True)
        self.db.files.create_index([("user_id", ASCENDING)])
        self.db.files.create_index([("timestamp", DESCENDING)])
        self.db.files.create_index([("file_type", ASCENDING)])
        
        # TTL index for temporary files (auto-delete after 30 days)
        self.db.files.create_index(
            [("timestamp", ASCENDING)], 
            expireAfterSeconds=2592000  # 30 days
        )
        
        # Stats collection
        self.db.stats.create_index([("date", ASCENDING)], unique=True)
        self.db.stats.create_index([("user_id", ASCENDING)])
        
        # Logs collection (TTL for 90 days)
        self.db.logs.create_index([("timestamp", ASCENDING)], expireAfterSeconds=7776000)
        
        logger.info("✅ Created database indexes")
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("✅ Closed MongoDB connection")
    
    # User operations
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        return self.db.users.find_one({"user_id": user_id})
    
    async def create_user(self, user_data: Dict) -> Dict:
        """Create a new user"""
        try:
            user_doc = {
                "user_id": user_data.get('id'),
                "username": user_data.get('username'),
                "first_name": user_data.get('first_name'),
                "last_name": user_data.get('last_name'),
                "join_date": datetime.utcnow(),
                "last_active": datetime.utcnow(),
                "total_requests": 0,
                "files_processed": 0,
                "is_premium": False,
                "is_admin": user_data.get('id') in [],  # Will be set from config
                "settings": {
                    "auto_delete_duplicates": True,
                    "replace_url_with": "[LINK REMOVED]",
                    "language": "en",
                    "notifications": True
                },
                "subscription": {
                    "type": "free",
                    "expiry": None,
                    "max_file_size": 50 * 1024 * 1024  # 50MB
                }
            }
            
            result = self.db.users.insert_one(user_doc)
            user_doc['_id'] = result.inserted_id
            
            logger.info(f"👤 Created new user: {user_data.get('username')} ({user_data.get('id')})")
            return user_doc
            
        except DuplicateKeyError:
            # User already exists, update last active
            self.db.users.update_one(
                {"user_id": user_data.get('id')},
                {"$set": {"last_active": datetime.utcnow()}}
            )
            return await self.get_user(user_data.get('id'))
    
    async def update_user_stats(self, user_id: int, increment_requests: int = 1):
        """Update user statistics"""
        try:
            update_data = {
                "$inc": {
                    "total_requests": increment_requests,
                    "files_processed": increment_requests
                },
                "$set": {"last_active": datetime.utcnow()}
            }
            
            self.db.users.update_one({"user_id": user_id}, update_data)
        except Exception as e:
            logger.error(f"Error updating user stats: {e}")
    
    # File operations
    async def save_file_record(self, file_data: Dict) -> str:
        """Save file record to database"""
        try:
            result = self.db.files.insert_one(file_data)
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.warning(f"Duplicate file detected: {file_data.get('file_hash')}")
            return "duplicate"
        except Exception as e:
            logger.error(f"Error saving file record: {e}")
            return ""
    
    async def check_duplicate_file(self, file_hash: str, user_id: int) -> bool:
        """Check if file is duplicate for the user"""
        try:
            existing = self.db.files.find_one({
                "file_hash": file_hash,
                "user_id": user_id
            })
            return existing is not None
        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False
    
    async def get_user_files(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get recent files for a user"""
        try:
            cursor = self.db.files.find(
                {"user_id": user_id}
            ).sort("timestamp", DESCENDING).limit(limit)
            
            return list(cursor)
        except Exception as e:
            logger.error(f"Error getting user files: {e}")
            return []
    
    async def delete_user_files(self, user_id: int):
        """Delete all files for a user"""
        try:
            result = self.db.files.delete_many({"user_id": user_id})
            logger.info(f"Deleted {result.deleted_count} files for user {user_id}")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error deleting user files: {e}")
            return 0
    
    # Statistics operations
    async def update_daily_stats(self):
        """Update daily statistics"""
        try:
            today = datetime.utcnow().date().isoformat()
            
            stats_update = {
                "$inc": {
                    "total_requests": 1,
                    "active_users": 0  # Will be updated separately
                },
                "$set": {"last_updated": datetime.utcnow()}
            }
            
            self.db.stats.update_one(
                {"date": today},
                stats_update,
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating daily stats: {e}")
    
    async def get_system_stats(self) -> Dict:
        """Get system-wide statistics"""
        try:
            total_users = self.db.users.count_documents({})
            total_files = self.db.files.count_documents({})
            total_requests = sum(user.get('total_requests', 0) for user in self.db.users.find({}))
            
            # Get today's stats
            today = datetime.utcnow().date().isoformat()
            today_stats = self.db.stats.find_one({"date": today}) or {}
            
            return {
                "total_users": total_users,
                "total_files": total_files,
                "total_requests": total_requests,
                "today_requests": today_stats.get('total_requests', 0),
                "today_users": today_stats.get('active_users', 0)
            }
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return {}
    
    # Settings operations
    async def get_settings(self) -> Dict:
        """Get global settings"""
        try:
            settings = self.db.settings.find_one({"_id": "global_settings"})
            if not settings:
                # Create default settings
                default_settings = {
                    "_id": "global_settings",
                    "app_name": "Telegram URL Remover Bot",
                    "version": "1.0.0",
                    "maintenance_mode": False,
                    "max_file_size": 50 * 1024 * 1024,
                    "supported_formats": [".mp4", ".avi", ".mov", ".mkv"],
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                self.db.settings.insert_one(default_settings)
                return default_settings
            return settings
        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return {}
    
    async def update_settings(self, settings: Dict):
        """Update global settings"""
        try:
            settings['updated_at'] = datetime.utcnow()
            self.db.settings.update_one(
                {"_id": "global_settings"},
                {"$set": settings},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
    
    # Logging operations
    async def log_activity(self, log_data: Dict):
        """Log activity to database"""
        try:
            log_data['timestamp'] = datetime.utcnow()
            self.db.logs.insert_one(log_data)
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
    
    # Admin operations
    async def get_all_users(self, skip: int = 0, limit: int = 100) -> List[Dict]:
        """Get all users (admin only)"""
        try:
            cursor = self.db.users.find({}).skip(skip).limit(limit).sort("join_date", DESCENDING)
            return list(cursor)
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    async def delete_user(self, user_id: int) -> bool:
        """Delete a user (admin only)"""
        try:
            # Delete user and their files
            await self.delete_user_files(user_id)
            result = self.db.users.delete_one({"user_id": user_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False
    
    # Cleanup operations
    async def cleanup_old_data(self, days: int = 30):
        """Cleanup old data"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Delete old files (already handled by TTL index)
            # Delete old logs (already handled by TTL index)
            
            # Update stats
            self.db.stats.delete_many({"date": {"$lt": cutoff_date.date().isoformat()}})
            
            logger.info(f"🧹 Cleaned up data older than {days} days")
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
