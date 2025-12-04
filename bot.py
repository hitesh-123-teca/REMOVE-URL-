#!/usr/bin/env python3
"""
🤖 TELEGRAM AUTO FORWARD BOT
✅ Features: Video Forwarding + URL Removal + MongoDB + Health Check
🚀 Version: 3.0
"""

import os
import re
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Third-party imports
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message
from telethon.errors import FloodWaitError, ChannelPrivateError, ChatAdminRequiredError
import motor.motor_asyncio
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
import aiohttp
from aiohttp import web

# Load environment
load_dotenv()

# ==================== CONFIGURATION ====================

class Config:
    # Required
    API_ID = int(os.getenv('API_ID', 0))
    API_HASH = os.getenv('API_HASH', '')
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    SOURCE_CHANNEL = os.getenv('SOURCE_CHANNEL', '')
    DESTINATION_CHANNEL = os.getenv('DESTINATION_CHANNEL', '')
    
    # MongoDB
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'telegram_bot')
    
    # Optional
    BOT_NAME = os.getenv('BOT_NAME', 'AutoForwardBot')
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
    SESSION_STRING = os.getenv('SESSION_STRING', '')
    REMOVE_URLS = os.getenv('REMOVE_URLS', 'true').lower() == 'true'
    ADD_WATERMARK = os.getenv('ADD_WATERMARK', 'false').lower() == 'true'
    WATERMARK_TEXT = os.getenv('WATERMARK_TEXT', '📤 Forwarded via Bot')
    
    # Performance
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 524288000))  # 500MB
    DELAY_BETWEEN_FORWARDS = float(os.getenv('DELAY_BETWEEN_FORWARDS', 2.0))
    RATE_LIMIT = int(os.getenv('RATE_LIMIT', 20))
    
    # Web Server
    WEB_SERVER_PORT = int(os.getenv('WEB_SERVER_PORT', 8080))
    WEB_SERVER_HOST = os.getenv('WEB_SERVER_HOST', '0.0.0.0')

config = Config()

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)

# ==================== UTILITIES ====================

class TextUtils:
    """Text processing utilities"""
    
    @staticmethod
    def remove_urls(text: str) -> str:
        """Remove all URLs and mentions"""
        if not text:
            return ""
        
        patterns = [
            r'https?://\S+',
            r't\.me/\S+',
            r'@\w+',
            r'bit\.ly/\S+',
            r'tinyurl\.com/\S+',
            r'wa\.me/\S+',
            r'goo\.gl/\S+',
            r'ow\.ly/\S+',
            r'is\.gd/\S+',
            r'buff\.ly/\S+',
            r'youtu\.be/\S+',
            r'instagram\.com/\S+',
            r'facebook\.com/\S+',
            r'twitter\.com/\S+',
            r'linkedin\.com/\S+',
            r'pinterest\.com/\S+',
            r'tiktok\.com/\S+',
            r'snapchat\.com/\S+',
            r'reddit\.com/\S+',
            r'discord\.gg/\S+',
        ]
        
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Convert bytes to readable format"""
        if size_bytes == 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        while size_bytes >= 1024 and i < len(units) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {units[i]}"
    
    @staticmethod
    def format_duration(seconds: int) -> str:
        """Convert seconds to readable format"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            return f"{hours}h {minutes}m {seconds}s"

class MediaUtils:
    """Media processing utilities"""
    
    @staticmethod
    def get_video_info(message: Message) -> Dict:
        """Extract video information"""
        if not message.video:
            return {}
        
        try:
            video = message.video
            return {
                'file_size': video.size,
                'duration': video.duration,
                'width': video.w if hasattr(video, 'w') else 0,
                'height': video.h if hasattr(video, 'h') else 0,
                'mime_type': 'video/mp4'
            }
        except:
            return {}

# ==================== DATABASE ====================

class DatabaseManager:
    """MongoDB Database Manager"""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                config.MONGODB_URI,
                serverSelectionTimeoutMS=5000
            )
            
            await self.client.admin.command('ping')
            self.db = self.client[config.DATABASE_NAME]
            
            await self._initialize_db()
            self.connected = True
            logger.info("✅ MongoDB connected")
            return True
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            return False
    
    async def _initialize_db(self):
        """Initialize database collections and indexes"""
        try:
            # Messages collection
            messages = self.db.messages
            await messages.create_index(
                [("source_message_id", 1), ("source_channel", 1)],
                unique=True
            )
            await messages.create_index([("forwarded_at", -1)])
            await messages.create_index([("media_type", 1)])
            
            # Stats collection
            stats = self.db.stats
            await stats.create_index([("date", 1)], unique=True)
            
            logger.info("✅ Database initialized")
            
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
    
    async def save_message(self, data: Dict) -> Optional[str]:
        """Save forwarded message to database"""
        try:
            messages = self.db.messages
            result = await messages.insert_one(data)
            return str(result.inserted_id)
        except DuplicateKeyError:
            logger.warning("⚠️ Duplicate message detected")
            return None
        except Exception as e:
            logger.error(f"❌ Error saving message: {e}")
            return None
    
    async def is_message_forwarded(self, source_message_id: int, source_channel: str) -> bool:
        """Check if message already forwarded"""
        try:
            messages = self.db.messages
            existing = await messages.find_one({
                "source_message_id": source_message_id,
                "source_channel": source_channel
            })
            return existing is not None
        except Exception as e:
            logger.error(f"❌ Error checking message: {e}")
            return False
    
    async def update_stats(self):
        """Update daily statistics"""
        try:
            stats = self.db.stats
            today = datetime.now().strftime("%Y-%m-%d")
            
            await stats.update_one(
                {"date": today},
                {
                    "$inc": {"total_forwarded": 1, "videos_forwarded": 1},
                    "$setOnInsert": {"created_at": datetime.now()}
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"❌ Error updating stats: {e}")
    
    async def get_statistics(self) -> Dict:
        """Get all statistics"""
        try:
            stats = self.db.stats
            today = datetime.now().strftime("%Y-%m-%d")
            daily_stats = await stats.find_one({"date": today})
            
            messages = self.db.messages
            total = await messages.count_documents({})
            
            # Get today's count
            start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_count = await messages.count_documents({
                "forwarded_at": {"$gte": start_of_day}
            })
            
            # Get media type breakdown
            pipeline = [
                {"$group": {
                    "_id": "$media_type",
                    "count": {"$sum": 1},
                    "total_size": {"$sum": "$file_size"}
                }}
            ]
            media_stats = await messages.aggregate(pipeline).to_list(None)
            
            return {
                "total": total,
                "today": today_count,
                "daily": daily_stats or {},
                "media_stats": media_stats,
                "connected": self.connected
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {}
    
    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("✅ Database connection closed")

# ==================== BOT CORE ====================

class TelegramForwardBot:
    """Main Telegram Bot Class"""
    
    def __init__(self):
        self.client = None
        self.bot_info = None
        self.db = DatabaseManager()
        self.running = False
        self.start_time = None
        self.stats = {
            'forwarded': 0,
            'errors': 0,
            'started': datetime.now()
        }
    
    async def initialize(self):
        """Initialize bot and database"""
        logger.info("🚀 Initializing Telegram Bot...")
        
        # Validate configuration
        if not self._validate_config():
            return False
        
        # Connect to database
        await self.db.connect()
        
        # Initialize Telegram client
        try:
            if config.SESSION_STRING:
                session = StringSession(config.SESSION_STRING)
                self.client = TelegramClient(session, config.API_ID, config.API_HASH)
            else:
                self.client = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
            
            await self.client.start(bot_token=config.BOT_TOKEN)
            self.bot_info = await self.client.get_me()
            
            # Save session string for future use
            if not config.SESSION_STRING:
                session_str = self.client.session.save()
                logger.info(f"💾 Session String (save in SESSION_STRING):\n{session_str}")
            
            logger.info(f"✅ Bot started as @{self.bot_info.username}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Bot initialization failed: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """Validate required configuration"""
        required = {
            'API_ID': config.API_ID,
            'API_HASH': config.API_HASH,
            'BOT_TOKEN': config.BOT_TOKEN,
            'SOURCE_CHANNEL': config.SOURCE_CHANNEL,
            'DESTINATION_CHANNEL': config.DESTINATION_CHANNEL,
        }
        
        missing = [k for k, v in required.items() if not v]
        if missing:
            logger.error(f"❌ Missing required config: {', '.join(missing)}")
            return False
        
        return True
    
    async def start_handlers(self):
        """Start all event handlers"""
        
        # ========== COMMAND HANDLERS ==========
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            """Handle /start command"""
            if event.is_private:
                welcome = f"""
🤖 **{config.BOT_NAME}**
_Auto Forward Bot with URL Removal_

📋 **Available Commands:**
/start - Show this message
/stats - View statistics  
/health - Health check
/help - Help guide
/status - Bot status

⚙️ **Configuration:**
• Source: `{config.SOURCE_CHANNEL}`
• Destination: `{config.DESTINATION_CHANNEL}`
• URL Removal: {'✅ ON' if config.REMOVE_URLS else '❌ OFF'}
• Watermark: {'✅ ON' if config.ADD_WATERMARK else '❌ OFF'}

📊 **Status:** {'🟢 RUNNING' if self.running else '🔴 STOPPED'}
⏰ **Uptime:** {self._get_uptime()}
                """
                await event.reply(welcome)
        
        @self.client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            """Handle /stats command"""
            if event.is_private:
                stats = await self.db.get_statistics()
                
                # Format media statistics
                media_text = ""
                for stat in stats.get('media_stats', []):
                    media_type = stat['_id'] or 'unknown'
                    count = stat['count']
                    total_size = stat.get('total_size', 0)
                    size_str = TextUtils.format_size(total_size)
                    media_text += f"  • {media_type.title()}: {count} ({size_str})\n"
                
                stats_text = f"""
📊 **Bot Statistics**
━━━━━━━━━━━━━━━━━━━
✅ **Total Forwarded:** {stats.get('total', 0)}
📅 **Today:** {stats.get('today', 0)}
❌ **Errors:** {self.stats['errors']}
⏰ **Uptime:** {self._get_uptime()}
🕐 **Started:** {self.stats['started'].strftime('%Y-%m-%d %H:%M:%S')}

📁 **Media Breakdown:**
{media_text if media_text else '  • No data yet'}

🗄️ **Database:** {'✅ Connected' if stats.get('connected') else '❌ Disconnected'}
━━━━━━━━━━━━━━━━━━━
                """
                await event.reply(stats_text)
        
        @self.client.on(events.NewMessage(pattern='/health'))
        async def health_handler(event):
            """Handle /health command"""
            if event.is_private:
                health_text = f"""
🏥 **System Health Check**
━━━━━━━━━━━━━━━━━━━
🤖 **Bot Status:** {'🟢 Connected' if self.client and self.client.is_connected() else '🔴 Disconnected'}
🗄️ **Database:** {'🟢 Connected' if self.db.connected else '🔴 Disconnected'}
📡 **Source Channel:** {config.SOURCE_CHANNEL}
🎯 **Destination Channel:** {config.DESTINATION_CHANNEL}
🔄 **Processed:** {self.stats['forwarded']} videos
❌ **Errors:** {self.stats['errors']}
⏰ **Uptime:** {self._get_uptime()}

⚙️ **Features Active:**
• URL Removal: {'✅' if config.REMOVE_URLS else '❌'}
• Watermark: {'✅' if config.ADD_WATERMARK else '❌'}
• Rate Limit: {config.RATE_LIMIT}/min
• Max File Size: {TextUtils.format_size(config.MAX_FILE_SIZE)}
━━━━━━━━━━━━━━━━━━━
                """
                await event.reply(health_text)
        
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            """Handle /help command"""
            if event.is_private:
                help_text = f"""
🆘 **{config.BOT_NAME} - Help Guide**
━━━━━━━━━━━━━━━━━━━

**📌 How it works:**
1. Bot monitors {config.SOURCE_CHANNEL} for new videos
2. Automatically forwards to {config.DESTINATION_CHANNEL}
3. Removes URLs from captions
4. Logs everything to MongoDB

**⚙️ Setup Instructions:**
1. Add bot as ADMIN in both channels
2. Get channel IDs (must start with -100)
3. Set environment variables:
