import os
import re
import logging
from typing import Dict, Optional
from datetime import datetime
import tempfile
import asyncio

from telegram import Update, Bot, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from pymongo import MongoClient
from moviepy.editor import VideoFileClip
from PIL import Image
import requests

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client.telegram_forward_bot

# Collections
settings_collection = db.settings
files_collection = db.forwarded_files
admin_collection = db.admins

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VideoForwardBot:
    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token)
        
    def remove_urls_from_caption(self, caption: str) -> str:
        """Remove URLs from caption"""
        if not caption:
            return ""
        # Remove URLs
        url_pattern = r'https?://\S+|www\.\S+'
        caption = re.sub(url_pattern, '', caption)
        # Remove Markdown/HTML links
        caption = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', caption)
        return caption.strip()
    
    async def extract_thumbnail(self, video_path: str, time_sec: int = 4) -> Optional[str]:
        """Extract thumbnail from video at specified time"""
        try:
            with VideoFileClip(video_path) as video:
                # Get frame at specified time
                frame_time = min(time_sec, video.duration - 1)
                frame = video.get_frame(frame_time)
                
                # Convert to PIL Image
                img = Image.fromarray(frame)
                
                # Save thumbnail
                thumbnail_path = f"{video_path}_thumb.jpg"
                img.save(thumbnail_path, "JPEG", quality=85)
                return thumbnail_path
        except Exception as e:
            logger.error(f"Thumbnail extraction failed: {e}")
            return None
    
    async def check_duplicate(self, file_id: str) -> tuple:
        """Check if file is duplicate and return existing message_id"""
        existing = files_collection.find_one({"file_id": file_id})
        if existing:
            return True, existing.get("target_message_id")
        return False, None
    
    async def forward_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video forwarding"""
        try:
            message = update.effective_message
            
            # Get settings
            settings = settings_collection.find_one({"bot_id": context.bot.id})
            if not settings or "target_channel" not in settings:
                await message.reply_text("Target channel not set! Use /set_target")
                return
            
            target_channel = settings["target_channel"]
            
            # Check if message from source channel
            if settings.get("source_channel"):
                if str(message.chat_id) != settings["source_channel"]:
                    return
            
            # Check for video
            if message.video:
                file_id = message.video.file_id
                file_size = message.video.file_size
                
                # Check duplicate
                is_duplicate, existing_msg_id = await self.check_duplicate(file_id)
                
                if is_duplicate and existing_msg_id:
                    try:
                        # Delete duplicate from target channel
                        await context.bot.delete_message(
                            chat_id=target_channel,
                            message_id=existing_msg_id
                        )
                        logger.info(f"Deleted duplicate: {file_id}")
                    except Exception as e:
                        logger.error(f"Failed to delete duplicate: {e}")
                
                # Remove URLs from caption
                caption = self.remove_urls_from_caption(message.caption)
                
                # Download video for processing
                file = await message.video.get_file()
                temp_video = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
                await file.download_to_drive(temp_video.name)
                
                # Generate thumbnail
                thumbnail_path = await self.extract_thumbnail(temp_video.name)
                
                # Prepare media
                media = InputMediaVideo(
                    media=file_id,
                    caption=caption,
                    thumbnail=open(thumbnail_path, 'rb') if thumbnail_path else None
                )
                
                # Forward to target channel
                forwarded_msg = await context.bot.send_video(
                    chat_id=target_channel,
                    video=file_id,
                    caption=caption,
                    thumbnail=open(thumbnail_path, 'rb') if thumbnail_path else None,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Store in database
                files_collection.update_one(
                    {"file_id": file_id},
                    {
                        "$set": {
                            "target_message_id": forwarded_msg.message_id,
                            "source_message_id": message.message_id,
                            "forwarded_at": datetime.now(),
                            "file_size": file_size
                        }
                    },
                    upsert=True
                )
                
                # Cleanup
                os.unlink(temp_video.name)
                if thumbnail_path and os.path.exists(thumbnail_path):
                    os.unlink(thumbnail_path)
                
                logger.info(f"Forwarded video: {file_id}")
                
        except Exception as e:
            logger.error(f"Forward error: {e}")
    
    async def set_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set source channel"""
        try:
            chat = update.effective_chat
            
            # Check if bot is admin
            chat_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if chat_member.status not in ["administrator", "creator"]:
                await update.message.reply_text("❌ Bot must be admin in this channel!")
                return
            
            settings_collection.update_one(
                {"bot_id": context.bot.id},
                {"$set": {"source_channel": str(chat.id)}},
                upsert=True
            )
            
            await update.message.reply_text(f"✅ Source channel set: {chat.title}")
            
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")
    
    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target channel"""
        try:
            chat = update.effective_chat
            
            # Check if bot is admin
            chat_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if chat_member.status not in ["administrator", "creator"]:
                await update.message.reply_text("❌ Bot must be admin in this channel!")
                return
            
            settings_collection.update_one(
                {"bot_id": context.bot.id},
                {"$set": {"target_channel": str(chat.id)}},
                upsert=True
            )
            
            await update.message.reply_text(f"✅ Target channel set: {chat.title}")
            
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with welcome message"""
        welcome_text = """
🤖 **Video Forward Bot Started!**

**Features:**
✅ MongoDB Database Storage
✅ Unlimited File Forwarding
✅ Duplicate Auto-Detection & Delete
✅ URL Removal from Captions
✅ Auto-Thumbnail Generation
✅ Admin-Only Channel Setup

**Commands:**
/set_source - Set source channel (Bot must be admin)
/set_target - Set target channel (Bot must be admin)
/stats - Get bot statistics
/help - Show help

**Setup Instructions:**
1. Add bot as ADMIN in both channels
2. Use /set_source in source channel
3. Use /set_target in target channel
4. Bot will automatically forward videos
"""
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        total_files = files_collection.count_documents({})
        settings = settings_collection.find_one({"bot_id": context.bot.id})
        
        stats_text = f"""
📊 **Bot Statistics**

📁 Total Files Forwarded: {total_files}
📈 Source Channel: {'Set' if settings and 'source_channel' in settings else 'Not Set'}
📉 Target Channel: {'Set' if settings and 'target_channel' in settings else 'Not Set'}
🤖 Bot Status: ✅ Active
"""
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

def main():
    """Main function"""
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("Please set TELEGRAM_BOT_TOKEN environment variable")
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    bot = VideoForwardBot(TOKEN)
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("set_source", bot.set_source))
    application.add_handler(CommandHandler("set_target", bot.set_target))
    application.add_handler(CommandHandler("stats", bot.stats))
    application.add_handler(MessageHandler(filters.VIDEO, bot.forward_video))
    
    # Start bot
    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
