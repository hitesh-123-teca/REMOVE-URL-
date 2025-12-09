"""
Main Telegram Bot instance - Fixed Version
With proper context handling for callbacks
"""

import logging
import asyncio
import html
import re
import hashlib
import os
import shutil
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from telegram import (
    Update, 
    InputFile, 
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# Database class
class DatabaseManager:
    """Handles MongoDB operations"""
    
    def __init__(self, mongo_uri: str, db_name: str = "url_remover_bot"):
        from pymongo import MongoClient, ASCENDING, DESCENDING
        from pymongo.errors import DuplicateKeyError
        
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        
        # Ensure collections exist
        collections = ['users', 'files', 'stats', 'settings']
        for col in collections:
            if col not in self.db.list_collection_names():
                self.db.create_collection(col)
        
        # Create indexes
        self.db.users.create_index([("user_id", ASCENDING)], unique=True)
        self.db.files.create_index([("file_hash", ASCENDING)], unique=True)
        self.db.files.create_index([("user_id", ASCENDING)])
        
        logging.info(f"✅ Connected to MongoDB: {db_name}")
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        return self.db.users.find_one({"user_id": user_id})
    
    async def create_user(self, user_data: Dict) -> Dict:
        """Create a new user"""
        from pymongo.errors import DuplicateKeyError
        
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
                "is_admin": False,
                "settings": {
                    "auto_delete_duplicates": True,
                    "replace_url_with": "[LINK REMOVED]",
                    "language": "en",
                    "notifications": True
                }
            }
            
            self.db.users.insert_one(user_doc)
            logging.info(f"👤 Created user: {user_data.get('username')}")
            return user_doc
            
        except DuplicateKeyError:
            # Update last active
            self.db.users.update_one(
                {"user_id": user_data.get('id')},
                {"$set": {"last_active": datetime.utcnow()}}
            )
            return await self.get_user(user_data.get('id'))
    
    async def update_user_stats(self, user_id: int, increment: int = 1):
        """Update user statistics"""
        self.db.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_requests": increment, "files_processed": increment},
                "$set": {"last_active": datetime.utcnow()}
            }
        )
    
    async def save_file_record(self, file_data: Dict) -> str:
        """Save file record to database"""
        from pymongo.errors import DuplicateKeyError
        
        try:
            result = self.db.files.insert_one(file_data)
            return str(result.inserted_id)
        except DuplicateKeyError:
            return "duplicate"
        except Exception as e:
            logging.error(f"Error saving file: {e}")
            return ""
    
    async def check_duplicate_file(self, file_hash: str, user_id: int) -> bool:
        """Check if file is duplicate for the user"""
        existing = self.db.files.find_one({
            "file_hash": file_hash,
            "user_id": user_id
        })
        return existing is not None
    
    async def get_user_files(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get user's files"""
        from pymongo import DESCENDING
        
        cursor = self.db.files.find({"user_id": user_id}).sort("timestamp", DESCENDING).limit(limit)
        return list(cursor)
    
    async def get_system_stats(self) -> Dict:
        """Get system statistics"""
        total_users = self.db.users.count_documents({})
        total_files = self.db.files.count_documents({})
        
        # Calculate total requests
        pipeline = [
            {"$group": {"_id": None, "total": {"$sum": "$total_requests"}}}
        ]
        result = list(self.db.users.aggregate(pipeline))
        total_requests = result[0]["total"] if result else 0
        
        return {
            "total_users": total_users,
            "total_files": total_files,
            "total_requests": total_requests,
            "today_requests": 0,
            "today_users": 0
        }
    
    async def log_activity(self, log_data: Dict):
        """Log activity"""
        log_data['timestamp'] = datetime.utcnow()
        if 'logs' not in self.db.list_collection_names():
            self.db.create_collection('logs')
        self.db.logs.insert_one(log_data)

# URL Processor class
class URLProcessor:
    """Handles URL removal"""
    
    URL_PATTERNS = [
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
        r'www\.(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
        r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\\s]*)?',
    ]
    
    def __init__(self, replacement_text: str = "[LINK REMOVED]"):
        self.replacement_text = replacement_text
    
    def remove_urls(self, text: str, replacement: Optional[str] = None) -> str:
        """Remove URLs from text"""
        if not text:
            return text
        
        if replacement is None:
            replacement = self.replacement_text
        
        # Combine patterns
        combined_pattern = '|'.join(self.URL_PATTERNS)
        
        # Remove URLs
        cleaned_text = re.sub(combined_pattern, replacement, text, flags=re.IGNORECASE)
        
        # Also remove markdown links
        cleaned_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', cleaned_text)
        
        # Clean extra spaces
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        
        return cleaned_text
    
    def find_urls(self, text: str) -> List[Tuple[str, str]]:
        """Find URLs in text"""
        if not text:
            return []
        
        found_urls = []
        for pattern in self.URL_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                url = match.group()
                url_type = self._classify_url(url)
                found_urls.append((url, url_type))
        
        return found_urls
    
    def _classify_url(self, url: str) -> str:
        """Classify URL type"""
        url_lower = url.lower()
        if url_lower.startswith('http://'):
            return "HTTP"
        elif url_lower.startswith('https://'):
            return "HTTPS"
        elif url_lower.startswith('www.'):
            return "WWW"
        elif '@' in url_lower:
            return "EMAIL"
        else:
            return "OTHER"

# File Manager class
class FileManager:
    """Handles file operations"""
    
    def __init__(self, temp_dir: str = "temp/downloads"):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs("temp/processed", exist_ok=True)
    
    async def download_file(self, file_obj, file_name: str) -> Optional[str]:
        """Download file from Telegram"""
        try:
            # Create safe filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._sanitize_filename(file_name)
            unique_name = f"{timestamp}_{safe_name}"
            file_path = os.path.join(self.temp_dir, unique_name)
            
            # Download file
            await file_obj.download_to_drive(file_path)
            
            logging.info(f"📥 Downloaded: {file_name}")
            return file_path
            
        except Exception as e:
            logging.error(f"Download error: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename"""
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        safe_name = ''.join(c for c in filename if c in safe_chars)
        return safe_name or "file"
    
    async def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """Calculate file hash"""
        if not os.path.exists(file_path):
            return None
        
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logging.error(f"Hash error: {e}")
            return None
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get file information"""
        if not os.path.exists(file_path):
            return {}
        
        try:
            stat = os.stat(file_path)
            _, ext = os.path.splitext(file_path)
            
            return {
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime),
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "extension": ext.lower(),
                "path": file_path,
                "filename": os.path.basename(file_path)
            }
        except Exception as e:
            logging.error(f"File info error: {e}")
            return {}
    
    def is_file_supported(self, file_path: str, supported_formats: list) -> bool:
        """Check if file format is supported"""
        if not os.path.exists(file_path):
            return False
        
        _, ext = os.path.splitext(file_path)
        return ext.lower() in supported_formats
    
    async def move_to_processed(self, file_path: str) -> Optional[str]:
        """Move file to processed directory"""
        if not os.path.exists(file_path):
            return None
        
        try:
            filename = os.path.basename(file_path)
            processed_path = os.path.join("temp/processed", filename)
            shutil.move(file_path, processed_path)
            return processed_path
        except Exception as e:
            logging.error(f"Move error: {e}")
            return file_path

# Main Bot Class
class TelegramBot:
    """Main Telegram Bot - Fixed for Button Callbacks"""
    
    def __init__(self, token: str, mongo_uri: str):
        """Initialize bot"""
        self.token = token
        self.mongo_uri = mongo_uri
        
        # Initialize components
        self.db = DatabaseManager(mongo_uri)
        self.url_processor = URLProcessor("[LINK REMOVED]")
        self.file_manager = FileManager()
        
        # Bot configuration
        self.config = {
            "BOT_NAME": "URL Remover Bot",
            "MAX_FILE_SIZE": 50 * 1024 * 1024,  # 50MB
            "SUPPORTED_FORMATS": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
            "MAX_USER_REQUESTS_PER_DAY": 100,
            "ADMIN_IDS": []
        }
        
        # Create application
        self.application = Application.builder().token(token).build()
        
        # Register handlers
        self._register_handlers()
        
        logging.info("🤖 Bot initialized")
    
    def _register_handlers(self):
        """Register bot handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("clean", self.clean_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("files", self.files_command))
        self.application.add_handler(CommandHandler("about", self.about_command))
        
        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text)
        )
        self.application.add_handler(
            MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, self.handle_video)
        )
        self.application.add_handler(
            MessageHandler(filters.Document.VIDEO, self.handle_video_document)
        )
        
        # Callback handler - FIXED
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    def escape_text(self, text: str) -> str:
        """Escape text for safe display"""
        if not text:
            return text
        
        # Replace problematic characters
        text = html.escape(text)
        
        # Truncate if too long
        if len(text) > 4000:
            text = text[:4000] + "..."
        
        return text
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Register user
        await self.db.create_user({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        })
        
        # Welcome message (NO MARKDOWN)
        welcome_message = f"""
🌟 Welcome {user.first_name}! 🌟

I'm {self.config['BOT_NAME']}, your personal URL cleaner bot!

What I can do:
✅ Remove URLs from video captions
✅ Delete duplicate videos automatically
✅ Clean URLs from any text message
✅ Support multiple video formats
✅ Free to use!

Quick Commands:
/start - Show this welcome message
/help - Detailed help guide
/clean <text> - Clean URLs from text
/stats - View your usage statistics
/settings - Configure bot settings
/files - View your processed files
/about - About this bot

How to use:
1. Send me a video with caption
2. Send me any text message
3. Use /clean command for text

Note: I support files up to {self.config['MAX_FILE_SIZE'] // (1024*1024)}MB
"""
        
        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("📖 Help", callback_data="help"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings")
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="stats"),
                InlineKeyboardButton("🧹 Clean Text", callback_data="clean_text")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_markup
        )
        
        # Log activity
        await self.db.log_activity({
            "user_id": user.id,
            "action": "start",
            "details": {"username": user.username}
        })
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
📚 Help Guide

Basic Commands:
/start - Start the bot
/help - Show this help
/clean <text> - Remove URLs from text
/stats - View your statistics
/settings - Configure bot settings
/files - View your files
/about - About this bot

How to clean URLs:
1. From videos: Send me any video with caption
2. From text: Send me any text message
3. Batch: Send multiple files one by one

Supported Video Formats:
MP4, AVI, MOV, MKV, WebM
Maximum size: 50MB

Tips:
• I work best with videos under 50MB
• URLs in captions are automatically removed
• You can customize replacement text
• Use /files to see your history

Need Help?
Contact support if needed.
"""
        await update.message.reply_text(help_message)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages - FIXED NO MARKDOWN"""
        original_text = update.message.text
        user = update.effective_user
        
        if not original_text:
            return
        
        # Get user settings
        user_data = await self.db.get_user(user.id)
        if not user_data:
            user_data = await self.db.create_user({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
        
        replacement = user_data.get('settings', {}).get('replace_url_with', '[LINK REMOVED]')
        
        # Check for URLs
        urls_found = self.url_processor.find_urls(original_text)
        
        if not urls_found:
            await update.message.reply_text(
                "I received your message. No URLs detected.\n\n"
                "Send me a video or use /clean <text> to remove URLs."
            )
            return
        
        # Remove URLs
        cleaned_text = self.url_processor.remove_urls(original_text, replacement)
        
        # Escape text for safe display
        cleaned_text = self.escape_text(cleaned_text)
        
        # Update statistics
        await self.db.update_user_stats(user.id)
        
        # Send cleaned text (NO MARKDOWN)
        response = f"✅ URLs Removed!\n\n{cleaned_text}"
        
        # Add button to see original
        keyboard = [[
            InlineKeyboardButton("🔍 Show Original", callback_data=f"show_original:{user.id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store original text
        context.user_data['original_text'] = original_text
        
        await update.message.reply_text(
            response,
            reply_markup=reply_markup
        )
    
    async def clean_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clean command"""
        if not context.args:
            await update.message.reply_text(
                "Usage: /clean <text>\n\n"
                "Example: /clean Check this website: https://example.com"
            )
            return
        
        text_to_clean = ' '.join(context.args)
        user = update.effective_user
        
        # Get user settings
        user_data = await self.db.get_user(user.id)
        replacement = user_data.get('settings', {}).get('replace_url_with', '[LINK REMOVED]')
        
        # Clean the text
        cleaned_text = self.url_processor.remove_urls(text_to_clean, replacement)
        cleaned_text = self.escape_text(cleaned_text)
        
        # Update statistics
        await self.db.update_user_stats(user.id)
        
        # Send response
        urls_found = self.url_processor.find_urls(text_to_clean)
        response = f"✅ Cleaned Text ({len(urls_found)} URLs removed)\n\n{cleaned_text}"
        
        await update.message.reply_text(response)
    
    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video messages"""
        await self._process_video(update, context, is_document=False)
    
    async def handle_video_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video documents"""
        await self._process_video(update, context, is_document=True)
    
    async def _process_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_document: bool = False):
        """Process video file"""
        user = update.effective_user
        
        # Get the video file
        if is_document:
            video_file = update.message.document
            file_name = video_file.file_name or "video.mp4"
        else:
            video_file = update.message.video or update.message.video_note
            file_name = "video.mp4"
        
        # Check if user exists
        user_data = await self.db.get_user(user.id)
        if not user_data:
            user_data = await self.db.create_user({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
        
        # Check file size
        if video_file.file_size > self.config['MAX_FILE_SIZE']:
            await update.message.reply_text(
                f"File is too large! Maximum size is {self.config['MAX_FILE_SIZE'] // (1024*1024)}MB"
            )
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text("⏳ Processing your video...")
        
        try:
            # Download file
            file_path = await self.file_manager.download_file(video_file, file_name)
            
            if not file_path:
                await processing_msg.edit_text("❌ Failed to download video.")
                return
            
            # Check file format
            if not self.file_manager.is_file_supported(file_path, self.config['SUPPORTED_FORMATS']):
                await processing_msg.edit_text(
                    f"❌ Unsupported format!\n"
                    f"Supported: {', '.join(self.config['SUPPORTED_FORMATS'])}"
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
                return
            
            # Calculate file hash
            file_hash = await self.file_manager.calculate_file_hash(file_path)
            
            # Check for duplicate
            is_duplicate = False
            if file_hash:
                is_duplicate = await self.db.check_duplicate_file(file_hash, user.id)
                
                if is_duplicate:
                    await processing_msg.edit_text(
                        "⚠️ Duplicate File Detected!\n"
                        "This video has already been processed."
                    )
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    return
            
            # Process caption
            original_caption = update.message.caption or ""
            replacement = user_data.get('settings', {}).get('replace_url_with', '[LINK REMOVED]')
            
            cleaned_caption = self.url_processor.remove_urls(original_caption, replacement)
            urls_found = self.url_processor.find_urls(original_caption)
            
            # Escape caption for safe display
            cleaned_caption = self.escape_text(cleaned_caption)
            
            # Get file info
            file_info = self.file_manager.get_file_info(file_path)
            
            # Save file record
            file_record = {
                "user_id": user.id,
                "file_id": video_file.file_id,
                "file_hash": file_hash,
                "file_name": file_name,
                "file_size": video_file.file_size,
                "file_type": file_info.get('extension', ''),
                "original_caption": original_caption,
                "cleaned_caption": cleaned_caption,
                "urls_found": len(urls_found),
                "timestamp": datetime.utcnow(),
                "processed": True
            }
            
            file_id = await self.db.save_file_record(file_record)
            
            if file_id == "duplicate":
                await processing_msg.edit_text("⚠️ Duplicate detected during processing!")
                if os.path.exists(file_path):
                    os.remove(file_path)
                return
            
            # Update processing message
            await processing_msg.edit_text("✅ Processing complete! Now uploading...")
            
            # Send cleaned video back (NO MARKDOWN in caption)
            with open(file_path, 'rb') as video:
                await update.message.reply_video(
                    video=InputFile(video, filename=file_name),
                    caption=cleaned_caption if cleaned_caption else None,
                    duration=video_file.duration if hasattr(video_file, 'duration') else None,
                    width=video_file.width if hasattr(video_file, 'width') else None,
                    height=video_file.height if hasattr(video_file, 'height') else None
                )
            
            # Update final message
            stats_message = f"""
✅ Video Processing Complete!

📊 Statistics:
• File: {file_name}
• Size: {video_file.file_size / (1024*1024):.1f}MB
• URLs removed: {len(urls_found)}
• Duplicate check: {"Passed" if not is_duplicate else "Failed"}

💾 Status: Saved to your history
"""
            
            await processing_msg.edit_text(stats_message)
            
            # Update user stats
            await self.db.update_user_stats(user.id)
            
            # Move file to processed directory
            await self.file_manager.move_to_processed(file_path)
            
            # Log activity
            await self.db.log_activity({
                "user_id": user.id,
                "action": "video_processed",
                "details": {
                    "file_name": file_name,
                    "file_size": video_file.file_size,
                    "urls_removed": len(urls_found)
                }
            })
            
        except Exception as e:
            logging.error(f"Error processing video: {e}")
            
            try:
                await processing_msg.edit_text(
                    f"❌ Error Processing Video\n\n"
                    f"Error: {str(e)[:100]}"
                )
            except:
                await update.message.reply_text("❌ Error processing video. Please try again.")
            
            # Log error
            await self.db.log_activity({
                "user_id": user.id,
                "action": "processing_error",
                "details": {"error": str(e)[:200]}
            })
        
        finally:
            # Cleanup temp file if it exists
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user = update.effective_user
        
        # Get user data
        user_data = await self.db.get_user(user.id)
        
        if not user_data:
            await update.message.reply_text("Use /start to begin.")
            return
        
        # Get user's recent files
        recent_files = await self.db.get_user_files(user.id, limit=5)
        
        # Get system stats
        system_stats = await self.db.get_system_stats()
        
        # Prepare stats message (NO MARKDOWN)
        stats_message = f"""
📊 Your Statistics

👤 User Info:
Name: {user_data.get('first_name', '')} {user_data.get('last_name', '')}
Username: @{user_data.get('username', 'Not set')}
Joined: {user_data.get('join_date', '').strftime('%Y-%m-%d') if user_data.get('join_date') else 'N/A'}

📈 Usage Stats:
Total Requests: {user_data.get('total_requests', 0)}
Files Processed: {user_data.get('files_processed', 0)}
Last Active: {user_data.get('last_active', '').strftime('%Y-%m-%d %H:%M') if user_data.get('last_active') else 'N/A'}

⚡ Account:
Premium: {'Yes' if user_data.get('is_premium') else 'No'}
Admin: {'Yes' if user_data.get('is_admin') else 'No'}

🌐 System Stats:
Total Users: {system_stats.get('total_users', 0)}
Total Files: {system_stats.get('total_files', 0)}
Total Requests: {system_stats.get('total_requests', 0)}
"""
        
        if recent_files:
            stats_message += "\n📁 Recent Files:\n"
            for i, file in enumerate(recent_files[:3], 1):
                file_name = file.get('file_name', 'Unknown')
                timestamp = file.get('timestamp', '').strftime('%m-%d') if file.get('timestamp') else 'N/A'
                stats_message += f"{i}. {file_name[:20]}... ({timestamp})\n"
        
        # Add buttons
        keyboard = [
            [
                InlineKeyboardButton("📁 View Files", callback_data="view_files"),
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")
            ],
            [
                InlineKeyboardButton("🏠 Home", callback_data="home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            stats_message,
            reply_markup=reply_markup
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user = update.effective_user
        
        # Get user data
        user_data = await self.db.get_user(user.id)
        
        if not user_data:
            await update.message.reply_text("Use /start to begin.")
            return
        
        settings = user_data.get('settings', {})
        
        # Prepare settings message
        settings_message = f"""
⚙️ Settings

Current Settings:
• Auto-delete duplicates: {'On' if settings.get('auto_delete_duplicates', True) else 'Off'}
• URL Replacement Text: {settings.get('replace_url_with', '[LINK REMOVED]')}
• Language: {settings.get('language', 'English')}
• Notifications: {'On' if settings.get('notifications', True) else 'Off'}
"""
        
        # Create settings keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🔁 Duplicates: {'ON' if settings.get('auto_delete_duplicates', True) else 'OFF'}",
                    callback_data="toggle_duplicates"
                )
            ],
            [
                InlineKeyboardButton(
                    f"🔔 Notifications: {'ON' if settings.get('notifications', True) else 'OFF'}",
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton("📝 Change Replacement", callback_data="change_replacement"),
                InlineKeyboardButton("🔄 Reset", callback_data="reset_settings")
            ],
            [
                InlineKeyboardButton("🏠 Home", callback_data="home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            settings_message,
            reply_markup=reply_markup
        )
    
    async def files_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /files command"""
        user = update.effective_user
        files = await self.db.get_user_files(user.id, limit=10)
        
        if not files:
            await update.message.reply_text("No files processed yet. Send me a video!")
            return
        
        files_message = "📁 Your Recent Files\n\n"
        
        for i, file in enumerate(files, 1):
            file_name = file.get('file_name', 'Unknown')
            timestamp = file.get('timestamp', '').strftime('%Y-%m-%d') if file.get('timestamp') else 'N/A'
            size_mb = file.get('file_size', 0) / (1024 * 1024)
            urls = file.get('urls_found', 0)
            
            files_message += f"{i}. {file_name[:30]}...\n"
            files_message += f"   Size: {size_mb:.1f}MB | URLs: {urls} | Date: {timestamp}\n\n"
        
        keyboard = [[
            InlineKeyboardButton("🏠 Home", callback_data="home")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            files_message,
            reply_markup=reply_markup
        )
    
    async def about_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /about command"""
        about_message = f"""
🤖 About {self.config['BOT_NAME']}

Version: 1.0.0
Description: A Telegram bot to remove URLs from video content and text messages

Features:
✅ URL removal from text and video captions
✅ Automatic duplicate file detection
✅ MongoDB database for data storage
✅ User statistics and history
✅ Customizable settings

Technology:
• Python 3.11
• python-telegram-bot library
• MongoDB database
• Docker & Koyeb deployment

Privacy:
• We store only necessary user data
• Files are processed temporarily
• You can delete your data anytime

Thank you for using our bot! ❤️
"""
        await update.message.reply_text(about_message)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks - FIXED WITH CONTEXT"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        # Create a new update-like object with the message
        # for command handlers that need it
        class MockUpdate:
            def __init__(self, message, user):
                self.message = message
                self.effective_user = user
                self.effective_message = message
        
        # Create mock context
        class MockContext:
            def __init__(self, user_data=None):
                self.user_data = user_data or {}
        
        mock_context = MockContext(context.user_data if context else {})
        
        if data == "help":
            # Create a mock update with the message
            mock_update = MockUpdate(query.message, user)
            await self.help_command(mock_update, mock_context)
            await query.message.delete()
        elif data == "settings":
            mock_update = MockUpdate(query.message, user)
            await self.settings_command(mock_update, mock_context)
            await query.message.delete()
        elif data == "stats":
            mock_update = MockUpdate(query.message, user)
            await self.stats_command(mock_update, mock_context)
            await query.message.delete()
        elif data == "clean_text":
            await query.edit_message_text(
                "Send me the text you want to clean, or use:\n"
                "/clean <your text here>"
            )
        elif data == "home":
            mock_update = MockUpdate(query.message, user)
            await self.start_command(mock_update, mock_context)
            await query.message.delete()
        elif data.startswith("show_original:"):
            original_text = context.user_data.get('original_text', 'Not available')
            await query.edit_message_text(f"📄 Original Text\n\n{original_text}")
        elif data == "view_files":
            mock_update = MockUpdate(query.message, user)
            await self.files_command(mock_update, mock_context)
            await query.message.delete()
        elif data == "refresh_stats":
            mock_update = MockUpdate(query.message, user)
            await self.stats_command(mock_update, mock_context)
            await query.message.delete()
        elif data == "toggle_duplicates":
            await query.edit_message_text("Feature coming soon!")
        elif data == "toggle_notifications":
            await query.edit_message_text("Feature coming soon!")
        elif data == "change_replacement":
            await query.edit_message_text("Feature coming soon!")
        elif data == "reset_settings":
            await query.edit_message_text("Feature coming soon!")
        else:
            await query.edit_message_text("Unknown action. Please use menu buttons.")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logging.error(f"Exception: {context.error}", exc_info=True)
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Sorry, an error occurred. Please try again."
                )
        except:
            pass
    
    async def run(self):
        """Run the bot"""
        # Start the bot
        logging.info("🤖 Bot is running... Press Ctrl+C to stop")
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Keep running until stopped
        await asyncio.Event().wait()
