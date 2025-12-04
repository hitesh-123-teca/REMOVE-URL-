#!/usr/bin/env python3
"""
Telegram Auto Forward Bot with MongoDB
Version: 2.0
Author: Your Name
Description: Automatically forwards videos from source channel to destination channel,
             removes URLs from captions, and stores data in MongoDB.
"""

import os
import re
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

# Third-party imports
try:
    from telethon import TelegramClient, events, Button
    from telethon.sessions import StringSession
    from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument
    from telethon.tl.functions.messages import ImportChatInviteRequest
    from telethon.errors import (
        FloodWaitError, 
        ChannelPrivateError, 
        ChatAdminRequiredError,
        MessageIdInvalidError
    )
    import motor.motor_asyncio
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, DuplicateKeyError
    from dotenv import load_dotenv
    import aiohttp
    from aiohttp import web
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("📦 Please install requirements: pip install telethon pymongo motor python-dotenv aiohttp")
    sys.exit(1)

# ==================== CONFIGURATION ====================

# Load environment variables
load_dotenv()

# Bot Configuration
class Config:
    # Telegram API Credentials (Required)
    API_ID = int(os.getenv('API_ID', 0))
    API_HASH = os.getenv('API_HASH', '')
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    
    # Channels (Required)
    SOURCE_CHANNEL = os.getenv('SOURCE_CHANNEL', '')
    DESTINATION_CHANNEL = os.getenv('DESTINATION_CHANNEL', '')
    
    # MongoDB (Required)
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'telegram_bot')
    
    # Optional Settings
    BOT_NAME = os.getenv('BOT_NAME', 'AutoForwardBot')
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
    SESSION_STRING = os.getenv('SESSION_STRING', '')
    
    # Bot Behavior
    REMOVE_URLS = os.getenv('REMOVE_URLS', 'true').lower() == 'true'
    REMOVE_MENTIONS = os.getenv('REMOVE_MENTIONS', 'true').lower() == 'true'
    ADD_WATERMARK = os.getenv('ADD_WATERMARK', 'false').lower() == 'true'
    WATERMARK_TEXT = os.getenv('WATERMARK_TEXT', 'Shared via Bot')
    
    # Performance
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 524288000))  # 500MB in bytes
    RATE_LIMIT = int(os.getenv('RATE_LIMIT', 20))  # Messages per minute
    DELAY_BETWEEN_FORWARDS = float(os.getenv('DELAY_BETWEEN_FORWARDS', 2.0))  # Seconds
    
    # Web Server (for health checks)
    WEB_SERVER_PORT = int(os.getenv('WEB_SERVER_PORT', 8080))
    WEB_SERVER_HOST = os.getenv('WEB_SERVER_HOST', '0.0.0.0')

config = Config()

# ==================== LOGGING SETUP ====================

def setup_logger():
    """Setup logging configuration"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Create logs directory if not exists
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from some libraries
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('motor').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

logger = setup_logger()

# ==================== DATABASE MANAGER ====================

class DatabaseManager:
    """MongoDB Database Manager"""
    
    def __init__(self, uri: str, db_name: str):
        self.uri = uri
        self.db_name = db_name
        self.client = None
        self.db = None
        self.is_connected = False
        
    async def connect(self):
        """Connect to MongoDB"""
        try:
            logger.info(f"🔗 Connecting to MongoDB: {self.uri}")
            
            # Async MongoDB client
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                self.uri,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=10,
                minPoolSize=1
            )
            
            # Test connection
            await self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            
            # Initialize database
            await self._initialize_collections()
            
            self.is_connected = True
            logger.info("✅ MongoDB connected successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            self.is_connected = False
            return False
    
    async def _initialize_collections(self):
        """Create collections and indexes"""
        try:
            # Messages collection
            messages = self.db.messages
            
            # Create indexes
            await messages.create_index(
                [("source_message_id", 1), ("source_channel", 1)], 
                unique=True,
                name="unique_message"
            )
            await messages.create_index(
                [("forwarded_at", -1)],
                name="forward_time_desc"
            )
            await messages.create_index(
                [("media_type", 1)],
                name="media_type"
            )
            await messages.create_index(
                [("status", 1)],
                name="status"
            )
            
            # Stats collection
            stats = self.db.stats
            await stats.create_index(
                [("date", 1)],
                unique=True,
                name="unique_date"
            )
            await stats.create_index(
                [("stat_type", 1)],
                name="stat_type"
            )
            
            # Users collection (for future multi-user support)
            users = self.db.users
            await users.create_index(
                [("user_id", 1)],
                unique=True,
                name="unique_user"
            )
            
            # Settings collection
            settings = self.db.settings
            await settings.create_index(
                [("key", 1)],
                unique=True,
                name="unique_key"
            )
            
            # Insert default settings if not exists
            default_settings = [
                {"key": "bot_started", "value": datetime.now().isoformat()},
                {"key": "total_forwarded", "value": 0},
                {"key": "last_forwarded", "value": None},
                {"key": "is_active", "value": True}
            ]
            
            for setting in default_settings:
                await settings.update_one(
                    {"key": setting["key"]},
                    {"$setOnInsert": setting},
                    upsert=True
                )
            
            logger.info("✅ Database initialized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
    
    async def save_message(self, message_data: Dict) -> Optional[str]:
        """Save forwarded message to database"""
        try:
            messages = self.db.messages
            result = await messages.insert_one(message_data)
            message_id = str(result.inserted_id)
            logger.debug(f"✅ Message saved to DB: {message_id}")
            return message_id
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
    
    async def update_stats(self, stat_type: str = "forward"):
        """Update statistics"""
        try:
            stats = self.db.stats
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Update daily stats
            await stats.update_one(
                {"date": today, "stat_type": "daily"},
                {
                    "$inc": {
                        "total_forwarded": 1,
                        f"{stat_type}_count": 1
                    },
                    "$set": {
                        "last_updated": datetime.now(),
                        "date": today,
                        "stat_type": "daily"
                    }
                },
                upsert=True
            )
            
            # Update hourly stats
            hour = datetime.now().strftime("%Y-%m-%d-%H")
            await stats.update_one(
                {"date": f"hourly_{hour}", "stat_type": "hourly"},
                {
                    "$inc": {"count": 1},
                    "$set": {
                        "hour": hour,
                        "last_updated": datetime.now(),
                        "stat_type": "hourly"
                    }
                },
                upsert=True
            )
            
            # Update global counter in settings
            settings = self.db.settings
            await settings.update_one(
                {"key": "total_forwarded"},
                {"$inc": {"value": 1}},
                upsert=True
            )
            
            await settings.update_one(
                {"key": "last_forwarded"},
                {"$set": {"value": datetime.now().isoformat()}},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"❌ Error updating stats: {e}")
    
    async def get_statistics(self) -> Dict:
        """Get all statistics"""
        try:
            stats = self.db.stats
            settings = self.db.settings
            
            # Get today's stats
            today = datetime.now().strftime("%Y-%m-%d")
            daily_stats = await stats.find_one(
                {"date": today, "stat_type": "daily"}
            )
            
            # Get hourly stats for last 24 hours
            last_24_hours = []
            for i in range(24):
                hour_time = datetime.now() - timedelta(hours=i)
                hour_str = hour_time.strftime("%Y-%m-%d-%H")
                hour_stat = await stats.find_one(
                    {"date": f"hourly_{hour_str}", "stat_type": "hourly"}
                )
                if hour_stat:
                    last_24_hours.append(hour_stat)
            
            # Get total from settings
            total_forwarded_doc = await settings.find_one({"key": "total_forwarded"})
            total_forwarded = total_forwarded_doc.get("value", 0) if total_forwarded_doc else 0
            
            # Get last forwarded time
            last_forwarded_doc = await settings.find_one({"key": "last_forwarded"})
            last_forwarded = last_forwarded_doc.get("value") if last_forwarded_doc else None
            
            # Get messages by media type
            messages = self.db.messages
            media_stats = await messages.aggregate([
                {"$group": {
                    "_id": "$media_type",
                    "count": {"$sum": 1},
                    "total_size": {"$sum": "$file_size"}
                }}
            ]).to_list(length=10)
            
            return {
                "daily": daily_stats or {},
                "hourly_last_24": last_24_hours,
                "total_forwarded": total_forwarded,
                "last_forwarded": last_forwarded,
                "media_stats": media_stats,
                "db_connected": self.is_connected
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting statistics: {e}")
            return {}
    
    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("✅ Database connection closed")

# ==================== UTILITY FUNCTIONS ====================

class TextProcessor:
    """Text processing utilities"""
    
    @staticmethod
    def remove_urls(text: str) -> str:
        """Remove all URLs and links from text"""
        if not text or not isinstance(text, str):
            return ""
        
        # Comprehensive URL patterns
        url_patterns = [
            r'https?://\S+',                      # HTTP/HTTPS
            r't\.me/\S+',                         # Telegram links
            r'@\w+',                              # Mentions
            r'bit\.ly/\S+',                       # Bitly
            r'tinyurl\.com/\S+',                  # TinyURL
            r'ow\.ly/\S+',                        # Hootsuite
            r'is\.gd/\S+',                        # is.gd
            r'buff\.ly/\S+',                      # Buffer
            r'goo\.gl/\S+',                       # Google URL shortener
            r'wa\.me/\S+',                        # WhatsApp
            r'fb\.me/\S+',                        # Facebook
            r'twitter\.com/\S+',                  # Twitter
            r'instagram\.com/\S+',                # Instagram
            r'youtu\.be/\S+',                     # YouTube short
            r'youtube\.com/\S+',                  # YouTube
            r'linkedin\.com/\S+',                 # LinkedIn
            r'pinterest\.com/\S+',                # Pinterest
            r'tiktok\.com/\S+',                   # TikTok
            r'snapchat\.com/\S+',                 # Snapchat
            r'reddit\.com/\S+',                   # Reddit
            r'discord\.gg/\S+',                   # Discord
            r'zoom\.us/\S+',                      # Zoom
            r'vimeo\.com/\S+',                    # Vimeo
            r'dailymotion\.com/\S+',              # Dailymotion
            r'twitch\.tv/\S+',                    # Twitch
        ]
        
        cleaned_text = text
        for pattern in url_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
        
        # Remove HTML tags
        cleaned_text = re.sub(r'<[^>]+>', '', cleaned_text)
        
        # Remove special characters used in URLs
        cleaned_text = re.sub(r'[\<\>\[\]\{\}\(\)]', '', cleaned_text)
        
        # Remove multiple spaces and trim
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Convert bytes to human readable format"""
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
        """Convert seconds to HH:MM:SS format"""
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

class MediaValidator:
    """Media validation utilities"""
    
    @staticmethod
    def is_video(message: Message) -> bool:
        """Check if message contains video"""
        if not message.media:
            return False
        
        if hasattr(message.media, 'document'):
            document = message.media.document
            if document:
                for attr in document.attributes:
                    if hasattr(attr, 'video'):
                        return True
        return False
    
    @staticmethod
    def get_video_info(message: Message) -> Dict:
        """Extract video information from message"""
        if not MediaValidator.is_video(message):
            return {}
        
        try:
            document = message.media.document
            file_size = document.size
            duration = 0
            width = 0
            height = 0
            
            for attr in document.attributes:
                if hasattr(attr, 'duration'):
                    duration = attr.duration
                if hasattr(attr, 'w'):
                    width = attr.w
                if hasattr(attr, 'h'):
                    height = attr.h
            
            mime_type = document.mime_type or 'video/mp4'
            
            return {
                'file_size': file_size,
                'duration': duration,
                'width': width,
                'height': height,
                'mime_type': mime_type,
                'file_name': document.attributes[0].file_name if hasattr(document.attributes[0], 'file_name') else 'video.mp4'
            }
        except Exception as e:
            logger.error(f"❌ Error getting video info: {e}")
            return {}

# ==================== TELEGRAM BOT ====================

class TelegramForwardBot:
    """Main Telegram Bot Class"""
    
    def __init__(self):
        self.client = None
        self.bot_info = None
        self.db_manager = DatabaseManager(config.MONGODB_URI, config.DATABASE_NAME)
        self.is_running = False
        self.start_time = None
        self.forwarded_count = 0
        self.error_count = 0
        
    async def initialize(self):
        """Initialize Telegram client and database"""
        logger.info("🚀 Initializing Telegram Forward Bot...")
        
        # Validate configuration
        if not self._validate_config():
            logger.error("❌ Invalid configuration. Please check environment variables.")
            return False
        
        # Connect to MongoDB
        if not await self.db_manager.connect():
            logger.warning("⚠️ Running without database connection")
        
        # Initialize Telegram client
        try:
            logger.info("🤖 Connecting to Telegram...")
            
            if config.SESSION_STRING:
                session = StringSession(config.SESSION_STRING)
                self.client = TelegramClient(session, config.API_ID, config.API_HASH)
            else:
                self.client = TelegramClient(
                    StringSession(),
                    config.API_ID,
                    config.API_HASH
                )
            
            await self.client.start(bot_token=config.BOT_TOKEN)
            self.bot_info = await self.client.get_me()
            
            # Save session string for future use
            if not config.SESSION_STRING:
                session_str = self.client.session.save()
                logger.info(f"💾 Session String (save this in SESSION_STRING): {session_str}")
            
            logger.info(f"✅ Bot started as @{self.bot_info.username} (ID: {self.bot_info.id})")
            
            # Set bot commands
            await self._set_bot_commands()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """Validate required configuration"""
        missing = []
        
        if not config.API_ID:
            missing.append("API_ID")
        if not config.API_HASH:
            missing.append("API_HASH")
        if not config.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not config.SOURCE_CHANNEL:
            missing.append("SOURCE_CHANNEL")
        if not config.DESTINATION_CHANNEL:
            missing.append("DESTINATION_CHANNEL")
        
        if missing:
            logger.error(f"❌ Missing required configuration: {', '.join(missing)}")
            return False
        
        return True
    
    async def _set_bot_commands(self):
        """Set bot commands for menu"""
        try:
            commands = [
                ("start", "Start the bot"),
                ("stats", "Get statistics"),
                ("health", "Check bot health"),
                ("help", "Show help message"),
                ("status", "Show bot status"),
            ]
            
            # Format for Telegram Bot API
            bot_commands = []
            for command, description in commands:
                bot_commands.append(types.BotCommand(command, description))
            
            await self.client(SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(),
                lang_code='en',
                commands=bot_commands
            ))
            
            logger.info("✅ Bot commands set successfully")
        except Exception as e:
            logger.warning(f"⚠️ Could not set bot commands: {e}")
    
    async def start_handlers(self):
        """Start all event handlers"""
        
        # ========== COMMAND HANDLERS ==========
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            """Handle /start command"""
            if event.is_private:
                user = await event.get_sender()
                welcome_text = f"""
👋 **Welcome {user.first_name}!**

🤖 **{config.BOT_NAME}**
_Auto Forward Bot with URL Removal_

📋 **Available Commands:**
/start - Show this message
/stats - Show forwarding statistics
/health - Check bot health
/help - Show help information
/status - Show bot status

🔧 **Configuration:**
• Source: `{config.SOURCE_CHANNEL}`
• Destination: `{config.DESTINATION_CHANNEL}`
• URL Removal: {'✅ Enabled' if config.REMOVE_URLS else '❌ Disabled'}

📊 **Bot Status:** {'🟢 Running' if self.is_running else '🔴 Stopped'}
                """
                
                buttons = [
                    [Button.inline("📊 Statistics", b"stats"),
                     Button.inline("🩺 Health Check", b"health")],
                    [Button.inline("🆘 Help", b"help"),
                     Button.inline("🔄 Status", b"status")]
                ]
                
                await event.reply(welcome_text, buttons=buttons)
        
        @self.client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            """Handle /stats command"""
            if event.is_private:
                stats = await self.db_manager.get_statistics()
                
                # Format statistics
                total = stats.get('total_forwarded', 0)
                daily = stats.get('daily', {})
                daily_count = daily.get('total_forwarded', 0) if daily else 0
                last_forwarded = stats.get('last_forwarded')
                
                # Format last forwarded time
                if last_forwarded:
                    try:
                        last_time = datetime.fromisoformat(last_forwarded)
                        last_str = last_time.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        last_str = "Never"
                else:
                    last_str = "Never"
                
                # Format media statistics
                media_stats_text = ""
                media_stats = stats.get('media_stats', [])
                for stat in media_stats:
                    media_type = stat.get('_id', 'unknown')
                    count = stat.get('count', 0)
                    total_size = stat.get('total_size', 0)
                    size_str = TextProcessor.format_file_size(total_size)
                    media_stats_text += f"  • {media_type.title()}: {count} ({size_str})\n"
                
                stats_text = f"""
📊 **Bot Statistics**
━━━━━━━━━━━━━━━━━━━
✅ **Total Forwarded:** {total}
📅 **Today's Count:** {daily_count}
⏰ **Last Forwarded:** {last_str}
🕐 **Uptime:** {self._get_uptime()}

📁 **Media Statistics:**
{media_stats_text if media_stats_text else '  • No data available'}

🤖 **Bot Info:**
  • Name: {config.BOT_NAME}
  • Username: @{self.bot_info.username if self.bot_info else 'N/A'}
  • Source: {config.SOURCE_CHANNEL}
  • Destination: {config.DESTINATION_CHANNEL}
━━━━━━━━━━━━━━━━━━━
                """
                
                await event.reply(stats_text)
        
        @self.client.on(events.NewMessage(pattern='/health'))
        async def health_handler(event):
            """Handle /health command"""
            if event.is_private:
                # Check bot connection
                bot_status = "🟢 Connected" if self.client.is_connected() else "🔴 Disconnected"
                
                # Check database connection
                db_status = "🟢 Connected" if self.db_manager.is_connected else "🔴 Disconnected"
                
                # Check channels
                source_status = "❓ Unknown"
                dest_status = "❓ Unknown"
                
                try:
                    source_entity = await self.client.get_entity(int(config.SOURCE_CHANNEL))
                    source_status = f"🟢 Accessible ({getattr(source_entity, 'title', 'Unknown')})"
                except Exception as e:
                    source_status = f"🔴 Error: {str(e)[:50]}"
                
                try:
                    dest_entity = await self.client.get_entity(int(config.DESTINATION_CHANNEL))
                    dest_status = f"🟢 Accessible ({getattr(dest_entity, 'title', 'Unknown')})"
                except Exception as e:
                    dest_status = f"🔴 Error: {str(e)[:50]}"
                
                health_text = f"""
🏥 **System Health Check**
━━━━━━━━━━━━━━━━━━━
🤖 **Bot Status:** {bot_status}
🗄️ **Database:** {db_status}
🔄 **Messages Processed:** {self.forwarded_count}
❌ **Errors:** {self.error_count}
⏰ **Uptime:** {self._get_uptime()}

📡 **Channels:**
  • Source: {source_status}
  • Destination: {dest_status}

⚙️ **Configuration:**
  • URL Removal: {'✅ Enabled' if config.REMOVE_URLS else '❌ Disabled'}  • Rate Limit: {config.RATE_LIMIT}/minute
  • Max File Size: {TextProcessor.format_file_size(config.MAX_FILE_SIZE)}
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
1. Bot monitors source channel for new videos
2. When video is detected, it forwards to destination channel
3. URLs are automatically removed from captions
4. All activity is logged in MongoDB

**⚙️ Environment Variables:**
**🛠️ Commands:**
• /start - Start the bot
• /stats - View statistics
• /health - System health check
• /help - This help message

**🔧 Features:**
• Auto video forwarding
• URL removal from captions
• MongoDB logging
• Duplicate prevention
• Rate limiting
• Health monitoring

**📞 Support:**
For issues or questions, contact the bot administrator.
━━━━━━━━━━━━━━━━━━━
                """
                
                await event.reply(help_text)
        
        @self.client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            """Handle /status command"""
            if event.is_private:
                status_text = f"""
🔄 **Bot Status**
━━━━━━━━━━━━━━━━━━━
**Bot:** {config.BOT_NAME}
**Status:** {'🟢 RUNNING' if self.is_running else '🔴 STOPPED'}
**Started:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}
**Uptime:** {self._get_uptime()}
**Forwarded Today:** {self.forwarded_count}
**Errors:** {self.error_count}

**Active Features:**
• Forwarding: {'✅ Active' if self.is_running else '❌ Inactive'}
• URL Removal: {'✅ Enabled' if config.REMOVE_URLS else '❌ Disabled'}
• Database: {'✅ Connected' if self.db_manager.is_connected else '❌ Disconnected'}
• Rate Limit: {config.RATE_LIMIT} msg/min

**Next Check:** Monitoring channels...
━━━━━━━━━━━━━━━━━━━
                """
                
                await event.reply(status_text)
        
        # ========== BUTTON HANDLERS ==========
        
        @self.client.on(events.CallbackQuery(data=b"stats"))
        async def stats_button_handler(event):
            """Handle stats button"""
            await stats_handler(event)
        
        @self.client.on(events.CallbackQuery(data=b"health"))
        async def health_button_handler(event):
            """Handle health button"""
            await health_handler(event)
        
        @self.client.on(events.CallbackQuery(data=b"help"))
        async def help_button_handler(event):
            """Handle help button"""
            await help_handler(event)
        
        @self.client.on(events.CallbackQuery(data=b"status"))
        async def status_button_handler(event):
            """Handle status button"""
            await status_handler(event)
        
        # ========== MAIN FORWARDING HANDLER ==========
        
        @self.client.on(events.NewMessage(chats=int(config.SOURCE_CHANNEL)))
        async def new_message_handler(event):
            """Handle new messages in source channel"""
            await self._process_message(event)
        
        logger.info("✅ Event handlers started successfully")
    
    async def _process_message(self, event):
        """Process incoming message"""
        try:
            # Check if it's a video
            if not MediaValidator.is_video(event.message):
                logger.debug(f"⚠️ Not a video, skipping message {event.message.id}")
                return
            
            message = event.message
            source_message_id = message.id
            source_channel = event.chat_id
            
            logger.info(f"🎬 New video detected: ID {source_message_id} from {source_channel}")
            
            # Check if already forwarded (duplicate prevention)
            if await self.db_manager.is_message_forwarded(source_message_id, source_channel):
                logger.info(f"⚠️ Message {source_message_id} already forwarded, skipping")
                return
            
            # Get video info
            video_info = MediaValidator.get_video_info(message)
            file_size = video_info.get('file_size', 0)
            
            # Check file size limit
            if file_size > config.MAX_FILE_SIZE:
                logger.warning(f"⚠️ File too large ({TextProcessor.format_file_size(file_size)}), skipping")
                return
            
            # Get and clean caption
            original_caption = message.text or message.caption or ""
            cleaned_caption = original_caption
            
            if config.REMOVE_URLS:
                cleaned_caption = TextProcessor.remove_urls(original_caption)
                logger.debug(f"✅ URLs removed from caption")
            
            # Prepare final caption
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if cleaned_caption:
                if config.ADD_WATERMARK:
                    final_caption = f"{cleaned_caption}\n\n{config.WATERMARK_TEXT} | {timestamp}"
                else:
                    final_caption = f"{cleaned_caption}\n\n📥 {timestamp}"
            else:
                if config.ADD_WATERMARK:
                    final_caption = f"{config.WATERMARK_TEXT} | {timestamp}"
                else:
                    final_caption = f"📥 {timestamp}"
            
            # Apply rate limiting delay
            if config.DELAY_BETWEEN_FORWARDS > 0:
                await asyncio.sleep(config.DELAY_BETWEEN_FORWARDS)
            
            # Forward the video
            logger.info(f"⏳ Forwarding video {source_message_id}...")
            
            try:
                forwarded_message = await self.client.send_file(
                    int(config.DESTINATION_CHANNEL),
                    message.media,
                    caption=final_caption,
                    supports_streaming=True,
                    parse_mode='html'
                )
                
                forwarded_id = forwarded_message.id
                logger.info(f"✅ Video forwarded successfully! New ID: {forwarded_id}")
                
                # Prepare data for MongoDB
                message_data = {
                    "source_channel": str(source_channel),
                    "source_message_id": source_message_id,
                    "destination_channel": str(config.DESTINATION_CHANNEL),
                    "destination_message_id": forwarded_id,
                    "media_type": "video",
                    "file_size": file_size,
                    "duration": video_info.get('duration', 0),
                    "width": video_info.get('width', 0),
                    "height": video_info.get('height', 0),
                    "mime_type": video_info.get('mime_type', ''),
                    "original_caption": original_caption[:1000],  # Limit length
                    "cleaned_caption": cleaned_caption[:1000],
                    "forwarded_at": datetime.now(),
                    "bot_username": self.bot_info.username if self.bot_info else None,
                    "status": "success"
                }
                
                # Save to MongoDB
                await self.db_manager.save_message(message_data)
                
                # Update statistics
                await self.db_manager.update_stats("forward")
                
                # Update counters
                self.forwarded_count += 1
                
                # Send success notification to admin (optional)
                if config.ADMIN_ID:
                    try:
                        await self.client.send_message(
                            config.ADMIN_ID,
                            f"✅ Forwarded video #{self.forwarded_count}\n"
                            f"📁 Size: {TextProcessor.format_file_size(file_size)}\n"
                            f"⏱️ Duration: {TextProcessor.format_duration(video_info.get('duration', 0))}\n"
                            f"🆔 From: {source_message_id} → {forwarded_id}"
                        )
                    except:
                        pass
                
            except FloodWaitError as e:
                logger.warning(f"⚠️ Flood wait: {e.seconds} seconds")
                await asyncio.sleep(e.seconds + 5)
                # Retry forwarding
                await self._process_message(event)
                return
                
            except ChannelPrivateError:
                logger.error("❌ Cannot access destination channel (private)")
                message_data = {
                    "source_channel": str(source_channel),
                    "source_message_id": source_message_id,
                    "status": "failed",
                    "error": "channel_private",
                    "forwarded_at": datetime.now()
                }
                await self.db_manager.save_message(message_data)
                
            except ChatAdminRequiredError:
                logger.error("❌ Bot is not admin in destination channel")
                message_data = {
                    "source_channel": str(source_channel),
                    "source_message_id": source_message_id,
                    "status": "failed",
                    "error": "admin_required",
                    "forwarded_at": datetime.now()
                }
                await self.db_manager.save_message(message_data)
                
            except Exception as e:
                logger.error(f"❌ Error forwarding video: {e}")
                self.error_count += 1
                
                message_data = {
                    "source_channel": str(source_channel),
                    "source_message_id": source_message_id,
                    "status": "failed",
                    "error": str(e)[:200],
                    "forwarded_at": datetime.now()
                }
                await self.db_manager.save_message(message_data)
                
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
            self.error_count += 1
    
    def _get_uptime(self) -> str:
        """Calculate and format bot uptime"""
        if not self.start_time:
            return "0s"
        
        uptime = datetime.now() - self.start_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    async def start_web_server(self):
        """Start a simple web server for health checks"""
        async def health_check(request):
            """Health check endpoint"""
            status = {
                "status": "running" if self.is_running else "stopped",
                "bot": config.BOT_NAME,
                "version": "2.0",
                "uptime": self._get_uptime(),
                "forwarded_count": self.forwarded_count,
                "error_count": self.error_count,
                "database": "connected" if self.db_manager.is_connected else "disconnected",
                "timestamp": datetime.now().isoformat()
            }
            return web.json_response(status)
        
        async def stats_endpoint(request):
            """Statistics endpoint"""
            stats = await self.db_manager.get_statistics()
            return web.json_response(stats)
        
        app = web.Application()
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        app.router.add_get('/stats', stats_endpoint)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, config.WEB_SERVER_HOST, config.WEB_SERVER_PORT)
        
        try:
            await site.start()
            logger.info(f"🌐 Web server started on http://{config.WEB_SERVER_HOST}:{config.WEB_SERVER_PORT}")
        except Exception as e:
            logger.error(f"❌ Failed to start web server: {e}")
    
    async def run(self):
        """Run the bot"""
        try:
            # Initialize bot
            if not await self.initialize():
                logger.error("❌ Bot initialization failed")
                return
            
            # Start web server (non-blocking)
            if config.WEB_SERVER_PORT > 0:
                asyncio.create_task(self.start_web_server())
            
            # Start event handlers
            await self.start_handlers()
            
            # Set running state
            self.is_running = True
            self.start_time = datetime.now()
            
            # Send startup notification
            logger.info(f"🚀 {config.BOT_NAME} is now running!")
            logger.info(f"📡 Source Channel: {config.SOURCE_CHANNEL}")
            logger.info(f"📡 Destination Channel: {config.DESTINATION_CHANNEL}")
            logger.info(f"🗄️ Database: {'Connected' if self.db_manager.is_connected else 'Not Connected'}")
            
            if config.ADMIN_ID:
                try:
                    await self.client.send_message(
                        config.ADMIN_ID,
                        f"🤖 *{config.BOT_NAME} Started!*\n\n"
                        f"✅ Bot: @{self.bot_info.username}\n"
                        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"📡 Source: `{config.SOURCE_CHANNEL}`\n"
                        f"🎯 Destination: `{config.DESTINATION_CHANNEL}`\n"
                        f"🗄️ Database: {'✅ Connected' if self.db_manager.is_connected else '❌ Not Connected'}\n\n"
                        f"_Bot is now monitoring for videos..._",
                        parse_mode='markdown'
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Could not send startup notification: {e}")
            
            # Keep bot running
            await self.client.run_until_disconnected()
            
        except KeyboardInterrupt:
            logger.info("\n👋 Bot stopped by user")
        except Exception as e:
            logger.error(f"💥 Fatal error: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the bot gracefully"""
        self.is_running = False
        
        logger.info("🛑 Shutting down bot...")
        
        # Send shutdown notification
        if config.ADMIN_ID and self.client and self.client.is_connected():
            try:
                uptime = self._get_uptime()
                await self.client.send_message(
                    config.ADMIN_ID,
                    f"🛑 *{config.BOT_NAME} Stopped*\n\n"
                    f"⏰ Uptime: {uptime}\n"
                    f"✅ Forwarded: {self.forwarded_count}\n"
                    f"❌ Errors: {self.error_count}\n"
                    f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"_Bot has been stopped._",
                    parse_mode='markdown'
                )
            except:
                pass
        
        # Close database connection
        await self.db_manager.close()
        
        # Disconnect Telegram client
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        
        logger.info("✅ Bot shutdown complete")

# ==================== MAIN ENTRY POINT ====================

async def main():
    """Main entry point"""
    print(f"""
    🤖 {config.BOT_NAME}
    🚀 Telegram Auto Forward Bot
    📅 Version 2.0
    ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """)
    
    # Create bot instance
    bot = TelegramForwardBot()
    
    # Run the bot
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"💥 Unhandled exception: {e}")
        print(f"\n❌ Bot crashed with error: {e}")
        print("🔄 Restarting in 10 seconds...")
        await asyncio.sleep(10)
        
        # Auto-restart
        await main()

if __name__ == '__main__':
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 or higher is required")
        sys.exit(1)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)
