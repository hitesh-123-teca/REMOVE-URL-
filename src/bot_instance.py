"""
Main Telegram Bot instance
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

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

from .config import Config
from .database import DatabaseManager
from .url_processor import URLProcessor
from .file_manager import FileManager

logger = logging.getLogger(__name__)

class TelegramBot:
    """Main Telegram Bot class"""
    
    # Conversation states
    WAITING_FOR_TEXT, WAITING_FOR_SETTING = range(2)
    
    def __init__(self, token: str, mongo_uri: str):
        """Initialize the bot"""
        self.token = token
        self.mongo_uri = mongo_uri
        
        # Initialize components
        self.db = DatabaseManager(mongo_uri, Config.MONGO_DB_NAME)
        self.url_processor = URLProcessor(Config.URL_REPLACEMENT_TEXT)
        self.file_manager = FileManager(Config.DOWNLOAD_DIR)
        
        # Create application
        self.application = Application.builder().token(token).build()
        
        # Register handlers
        self._register_handlers()
        
        # Register commands menu
        self._register_commands_menu()
    
    def _register_handlers(self):
        """Register all bot handlers"""
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("clean", self.clean_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("files", self.files_command))
        self.application.add_handler(CommandHandler("delete_my_files", self.delete_files_command))
        self.application.add_handler(CommandHandler("about", self.about_command))
        
        # Admin commands
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CommandHandler("broadcast", self.broadcast_command))
        self.application.add_handler(CommandHandler("system_stats", self.system_stats_command))
        
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
        self.application.add_handler(
            MessageHandler(filters.Document.ALL, self.handle_document)
        )
        
        # Callback query handler for buttons
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    def _register_commands_menu(self):
        """Register bot commands menu"""
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help message"),
            BotCommand("clean", "Clean URLs from text"),
            BotCommand("stats", "Show your statistics"),
            BotCommand("settings", "Configure bot settings"),
            BotCommand("files", "View your processed files"),
            BotCommand("about", "About this bot"),
        ]
        
        # Admin commands
        admin_commands = [
            BotCommand("admin", "Admin panel"),
            BotCommand("broadcast", "Broadcast message to all users"),
            BotCommand("system_stats", "System statistics"),
        ]
        
        # Set commands
        asyncio.create_task(self.application.bot.set_my_commands(commands))
        
        # Set admin commands for admin users
        for admin_id in Config.ADMIN_IDS:
            try:
                asyncio.create_task(
                    self.application.bot.set_my_commands(
                        commands + admin_commands,
                        scope={"type": "chat", "chat_id": admin_id}
                    )
                )
            except Exception as e:
                logger.error(f"Error setting admin commands for {admin_id}: {e}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Register user
        user_data = await self.db.create_user({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        })
        
        # Check if user is admin
        is_admin = user.id in Config.ADMIN_IDS
        
        # Welcome message
        welcome_message = f"""
🌟 **Welcome {user.first_name}!** 🌟

I'm **{Config.BOT_NAME}**, your personal URL cleaner bot! 

**What I can do:**
✅ Remove URLs from video captions
✅ Delete duplicate videos automatically  
✅ Clean URLs from any text message
✅ Support multiple video formats
✅ Free to use!

**Quick Commands:**
/start - Show this welcome message
/help - Detailed help guide
/clean <text> - Clean URLs from text
/stats - View your usage statistics
/settings - Configure bot settings
/files - View your processed files
/about - About this bot

**How to use:**
1. Send me a video with caption
2. Send me any text message
3. Use /clean command for text

**Note:** I support files up to {Config.MAX_FILE_SIZE // (1024*1024)}MB
"""
        
        if is_admin:
            welcome_message += "\n\n👑 **Admin Access:** You have access to admin commands!"
        
        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("📖 Help", callback_data="help"),
                InlineKeyboardButton("⚙️ Settings", callback_data="settings")
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="stats"),
                InlineKeyboardButton("🧹 Clean Text", callback_data="clean")
            ],
            [
                InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/your_username"),
                InlineKeyboardButton("⭐ Rate Bot", url="https://t.me/bots")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
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
📚 **Help Guide**

**Basic Commands:**
/start - Start the bot and see welcome message
/help - Show this help message
/clean <text> - Remove URLs from provided text
/stats - View your usage statistics
/settings - Configure bot settings
/files - View your recently processed files
/delete_my_files - Delete all your stored file records
/about - Information about this bot

**How to clean URLs:**
1. **From videos:** Send me any video file with caption
2. **From text:** Send me any text message or use /clean command
3. **Batch processing:** Send multiple files one by one

**Supported Video Formats:**
- MP4, AVI, MOV, MKV, WebM, FLV, WMV
- Maximum size: {max_size}MB

**Features:**
✅ Automatic URL removal
✅ Duplicate file detection
✅ Multiple language support
✅ Privacy focused
✅ Free forever for basic use

**Tips:**
• I work best with videos under 50MB
• URLs in captions are automatically removed
• You can customize replacement text in settings
• Use /delete_my_files to clear your history

**Need Help?**
Contact: @your_support_username
""".format(max_size=Config.MAX_FILE_SIZE // (1024*1024))
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def clean_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clean command"""
        if not context.args:
            await update.message.reply_text(
                "**Usage:** `/clean <text>`\n\n"
                "**Example:**\n"
                "`/clean Check this website: https://example.com and also www.test.com`\n\n"
                "**Or simply send me any text message!**",
                parse_mode='Markdown'
            )
            return
        
        text_to_clean = ' '.join(context.args)
        user = update.effective_user
        
        # Get user settings
        user_data = await self.db.get_user(user.id)
        replacement = user_data.get('settings', {}).get('replace_url_with', Config.URL_REPLACEMENT_TEXT)
        
        # Find URLs first
        urls_found = self.url_processor.find_urls(text_to_clean)
        
        if not urls_found:
            await update.message.reply_text("ℹ️ No URLs found in the provided text!")
            return
        
        # Clean the text
        cleaned_text = self.url_processor.remove_urls(text_to_clean, replacement)
        
        # Prepare response
        url_count = len(urls_found)
        url_types = self.url_processor.count_urls(text_to_clean)
        
        response = f"""
✅ **URLs Removed Successfully!**

📊 **Stats:**
• URLs found: {url_count}
• Text cleaned: {len(cleaned_text)} characters

🔗 **URL Types Found:**
"""
        
        for url_type, count in url_types.items():
            response += f"• {url_type}: {count}\n"
        
        response += f"\n📝 **Cleaned Text:**\n\n{cleaned_text}"
        
        # Truncate if too long
        if len(response) > Config.MAX_MESSAGE_LENGTH:
            response = response[:Config.MAX_MESSAGE_LENGTH - 100] + "...\n\n(Message truncated)"
        
        # Update user stats
        await self.db.update_user_stats(user.id)
        await self.db.update_daily_stats()
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        original_text = update.message.text
        user = update.effective_user
        
        # Get user settings
        user_data = await self.db.get_user(user.id)
        replacement = user_data.get('settings', {}).get('replace_url_with', Config.URL_REPLACEMENT_TEXT)
        
        # Check for URLs
        urls_found = self.url_processor.find_urls(original_text)
        
        if not urls_found:
            # No URLs found, just acknowledge
            await update.message.reply_text(
                "ℹ️ I received your message. No URLs detected.\n\n"
                "Send me a video or use `/clean <text>` to remove URLs.",
                parse_mode='Markdown'
            )
            return
        
        # Remove URLs
        cleaned_text = self.url_processor.remove_urls(original_text, replacement)
        
        # Update statistics
        await self.db.update_user_stats(user.id)
        await self.db.update_daily_stats()
        
        # Send cleaned text
        response = f"✅ **Cleaned Text**\n\n{cleaned_text}"
        
        # Add button to see original
        keyboard = [[
            InlineKeyboardButton("🔍 Show Original", callback_data=f"show_original:{user.id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store original text temporarily in context
        context.user_data['original_text'] = original_text
        
        await update.message.reply_text(
            response, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
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
        
        # Check if user exists, create if not
        user_data = await self.db.get_user(user.id)
        if not user_data:
            user_data = await self.db.create_user({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
        
        # Check daily limit
        if user_data.get('total_requests', 0) >= Config.MAX_USER_REQUESTS_PER_DAY and not user_data.get('is_premium', False):
            await update.message.reply_text(
                f"⚠️ **Daily Limit Reached!**\n\n"
                f"You've processed {user_data.get('total_requests', 0)} files today.\n"
                f"Daily limit: {Config.MAX_USER_REQUESTS_PER_DAY} files\n\n"
                f"Premium users get higher limits. Contact admin for upgrade."
            )
            return
        
        # Check file size
        if video_file.file_size > Config.MAX_FILE_SIZE:
            size_mb = video_file.file_size / (1024 * 1024)
            max_mb = Config.MAX_FILE_SIZE / (1024 * 1024)
            
            await update.message.reply_text(
                f"⚠️ **File Too Large!**\n\n"
                f"File size: {size_mb:.1f}MB\n"
                f"Maximum size: {max_mb:.0f}MB\n\n"
                f"Please send a smaller video file."
            )
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            "⏳ **Processing your video...**\n"
            "• Downloading file\n"
            "• Checking for duplicates\n"
            "• Removing URLs from caption\n"
            "This may take a moment..."
        )
        
        try:
            # Download file
            file_path = await self.file_manager.download_file(video_file, file_name)
            
            if not file_path:
                await processing_msg.edit_text("❌ Failed to download video. Please try again.")
                return
            
            # Check file format
            if not self.file_manager.is_file_supported(file_path, Config.SUPPORTED_FORMATS):
                await processing_msg.edit_text(
                    f"❌ **Unsupported Format!**\n\n"
                    f"Supported formats: {', '.join(Config.SUPPORTED_FORMATS)}\n"
                    f"Your file: {file_name}"
                )
                # Clean up
                if os.path.exists(file_path):
                    os.remove(file_path)
                return
            
            # Calculate file hash
            file_hash = await self.file_manager.calculate_file_hash(file_path)
            
            if Config.ENABLE_DUPLICATE_CHECK and file_hash:
                # Check for duplicate
                is_duplicate = await self.db.check_duplicate_file(file_hash, user.id)
                
                if is_duplicate:
                    await processing_msg.edit_text(
                        "⚠️ **Duplicate File Detected!**\n\n"
                        "This video has already been processed.\n"
                        "Duplicate files are deleted automatically."
                    )
                    
                    # Delete duplicate file
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    
                    # Log duplicate detection
                    await self.db.log_activity({
                        "user_id": user.id,
                        "action": "duplicate_detected",
                        "details": {"file_hash": file_hash[:12]}
                    })
                    return
            
            # Process caption
            original_caption = update.message.caption or ""
            replacement = user_data.get('settings', {}).get('replace_url_with', Config.URL_REPLACEMENT_TEXT)
            
            cleaned_caption = self.url_processor.remove_urls(original_caption, replacement)
            urls_found = self.url_processor.find_urls(original_caption)
            
            # Get file info
            file_info = self.file_manager.get_file_info(file_path)
            
            # Save file record to database
            file_record = {
                "user_id": user.id,
                "file_id": video_file.file_id,
                "file_hash": file_hash,
                "file_name": file_name,
                "file_size": video_file.file_size,
                "file_type": file_info.get('type', ''),
                "original_caption": original_caption,
                "cleaned_caption": cleaned_caption,
                "urls_found": len(urls_found),
                "timestamp": datetime.utcnow(),
                "processed": True
            }
            
            file_id = await self.db.save_file_record(file_record)
            
            if file_id == "duplicate":
                await processing_msg.edit_text(
                    "⚠️ **Duplicate detected during processing!**\n"
                    "This file was already in our database."
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
                return
            
            # Update processing message
            await processing_msg.edit_text(
                "✅ **Processing Complete!**\n"
                "• File downloaded\n"
                "• Duplicate checked\n"
                "• URLs removed\n"
                "• Now uploading..."
            )
            
            # Send cleaned video back
            with open(file_path, 'rb') as video:
                await update.message.reply_video(
                    video=InputFile(video, filename=file_name),
                    caption=cleaned_caption if cleaned_caption else None,
                    parse_mode='Markdown',
                    duration=video_file.duration if hasattr(video_file, 'duration') else None,
                    width=video_file.width if hasattr(video_file, 'width') else None,
                    height=video_file.height if hasattr(video_file, 'height') else None,
                    thumbnail=video_file.thumbnail if hasattr(video_file, 'thumbnail') else None
                )
            
            # Update final message
            stats_message = f"""
✅ **Video Processing Complete!**

📊 **Statistics:**
• File: {file_name}
• Size: {video_file.file_size / (1024*1024):.1f}MB
• URLs removed: {len(urls_found)}
• Duplicate check: {"Passed" if not is_duplicate else "Failed"}

📝 **Caption:**
{cleaned_caption if cleaned_caption else "No caption"}

💾 **Status:** Saved to your history
"""
            
            await processing_msg.edit_text(stats_message, parse_mode='Markdown')
            
            # Update user stats
            await self.db.update_user_stats(user.id)
            await self.db.update_daily_stats()
            
            # Move file to processed directory
            await self.file_manager.move_to_processed(file_path)
            
            # Log successful processing
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
            logger.error(f"Error processing video: {e}", exc_info=True)
            
            try:
                await processing_msg.edit_text(
                    f"❌ **Error Processing Video**\n\n"
                    f"Error: {str(e)[:100]}\n\n"
                    f"Please try again or contact support."
                )
            except:
                await update.message.reply_text(
                    f"❌ **Error Processing Video**\n\n"
                    f"Please try again."
                )
            
            # Log error
            await self.db.log_activity({
                "user_id": user.id,
                "action": "processing_error",
                "details": {"error": str(e)[:200]}
            })
        
        finally:
            # Cleanup: remove temp file if it still exists
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
            await update.message.reply_text(
                "You're not registered yet! Use /start to begin."
            )
            return
        
        # Get user's recent files
        recent_files = await self.db.get_user_files(user.id, limit=5)
        
        # Get system stats
        system_stats = await self.db.get_system_stats()
        
        # Prepare stats message
        stats_message = f"""
📊 **Your Statistics**

👤 **User Info:**
• Name: {user_data.get('first_name', '')} {user_data.get('last_name', '')}
• Username: @{user_data.get('username', 'Not set')}
• Joined: {user_data.get('join_date', '').strftime('%Y-%m-%d') if user_data.get('join_date') else 'N/A'}

📈 **Usage Stats:**
• Total Requests: {user_data.get('total_requests', 0)}
• Files Processed: {user_data.get('files_processed', 0)}
• Last Active: {user_data.get('last_active', '').strftime('%Y-%m-%d %H:%M') if user_data.get('last_active') else 'N/A'}

⚡ **Account:**
• Premium: {'✅ Yes' if user_data.get('is_premium') else '❌ No'}
• Admin: {'✅ Yes' if user_data.get('is_admin') else '❌ No'}

🌐 **System Stats:**
• Total Users: {system_stats.get('total_users', 0)}
• Total Requests: {system_stats.get('total_requests', 0)}
• Today's Requests: {system_stats.get('today_requests', 0)}
"""
        
        if recent_files:
            stats_message += "\n📁 **Recent Files:**\n"
            for i, file in enumerate(recent_files[:3], 1):
                file_name = file.get('file_name', 'Unknown')
                timestamp = file.get('timestamp', '').strftime('%m-%d %H:%M') if file.get('timestamp') else 'N/A'
                stats_message += f"{i}. {file_name[:20]}... ({timestamp})\n"
        
        # Add buttons
        keyboard = [
            [
                InlineKeyboardButton("📁 View All Files", callback_data="view_files"),
                InlineKeyboardButton("🗑️ Delete My Files", callback_data="delete_files")
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats"),
                InlineKeyboardButton("🏠 Home", callback_data="home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            stats_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user = update.effective_user
        
        # Get user data
        user_data = await self.db.get_user(user.id)
        
        if not user_data:
            user_data = await self.db.create_user({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
        
        settings = user_data.get('settings', {})
        
        # Prepare settings message
        settings_message = f"""
⚙️ **Settings**

**Current Settings:**
• Auto-delete duplicates: {'✅ On' if settings.get('auto_delete_duplicates', True) else '❌ Off'}
• URL Replacement Text: `{settings.get('replace_url_with', Config.URL_REPLACEMENT_TEXT)}`
• Language: {settings.get('language', 'English')}
• Notifications: {'✅ On' if settings.get('notifications', True) else '❌ Off'}

**Quick Actions:**
"""
        
        # Create settings keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    "🔁 Duplicates: " + ("ON" if settings.get('auto_delete_duplicates', True) else "OFF"),
                    callback_data="toggle_duplicates"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔔 Notifications: " + ("ON" if settings.get('notifications', True) else "OFF"),
                    callback_data="toggle_notifications"
                )
            ],
            [
                InlineKeyboardButton("🌐 Change Language", callback_data="change_language"),
                InlineKeyboardButton("📝 Change Replacement Text", callback_data="change_replacement")
            ],
            [
                InlineKeyboardButton("🔄 Reset to Default", callback_data="reset_settings"),
                InlineKeyboardButton("🏠 Home", callback_data="home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            settings_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        
        if data == "help":
            await self.help_command_callback(query)
        elif data == "settings":
            await self.settings_command_callback(query)
        elif data == "stats":
            await self.stats_command_callback(query)
        elif data == "clean":
            await self.clean_command_callback(query)
        elif data == "home":
            await self.home_callback(query)
        elif data.startswith("show_original:"):
            await self.show_original_callback(query, context)
        elif data == "toggle_duplicates":
            await self.toggle_duplicates_callback(query)
        elif data == "toggle_notifications":
            await self.toggle_notifications_callback(query)
        elif data == "change_replacement":
            await self.change_replacement_callback(query, context)
        elif data == "reset_settings":
            await self.reset_settings_callback(query)
        elif data == "view_files":
            await self.view_files_callback(query)
        elif data == "delete_files":
            await self.delete_files_callback(query)
        elif data == "refresh_stats":
            await self.refresh_stats_callback(query)
        else:
            await query.edit_message_text(
                "❌ Unknown action. Please use the menu buttons.",
                parse_mode='Markdown'
            )
    
    async def help_command_callback(self, query):
        """Handle help button callback"""
        await self.help_command(query.message)
        await query.message.delete()
    
    async def settings_command_callback(self, query):
        """Handle settings button callback"""
        await self.settings_command(query.message)
        await query.message.delete()
    
    async def stats_command_callback(self, query):
        """Handle stats button callback"""
        await self.stats_command(query.message)
        await query.message.delete()
    
    async def clean_command_callback(self, query):
        """Handle clean button callback"""
        await query.edit_message_text(
            "🧹 **Clean Text**\n\n"
            "Please send me the text you want to clean, or use:\n"
            "`/clean <your text here>`",
            parse_mode='Markdown'
        )
    
    async def home_callback(self, query):
        """Handle home button callback"""
        await self.start_command(query.message, None)
        await query.message.delete()
    
    async def show_original_callback(self, query, context):
        """Show original text"""
        original_text = context.user_data.get('original_text', 'Not available')
        
        await query.edit_message_text(
            f"📄 **Original Text**\n\n{original_text}",
            parse_mode='Markdown'
        )
    
    async def toggle_duplicates_callback(self, query):
        """Toggle duplicate detection"""
        user = query.from_user
        user_data = await self.db.get_user(user.id)
        
        if not user_data:
            await query.edit_message_text("User not found!")
            return
        
        settings = user_data.get('settings', {})
        current = settings.get('auto_delete_duplicates', True)
        settings['auto_delete_duplicates'] = not current
        
        # Update in database
        await self.db.update_user_settings(user.id, settings)
        
        # Update message
        await self.settings_command_callback(query)
    
    async def toggle_notifications_callback(self, query):
        """Toggle notifications"""
        user = query.from_user
        user_data = await self.db.get_user(user.id)
        
        if not user_data:
            await query.edit_message_text("User not found!")
            return
        
        settings = user_data.get('settings', {})
        current = settings.get('notifications', True)
        settings['notifications'] = not current
        
        # Update in database
        await self.db.update_user_settings(user.id, settings)
        
        # Update message
        await self.settings_command_callback(query)
    
    async def change_replacement_callback(self, query, context):
        """Change replacement text"""
        await query.edit_message_text(
            "📝 **Change Replacement Text**\n\n"
            "Please send me the new text to use for replacing URLs.\n"
            "Example: `[LINK REMOVED]` or `[REDACTED]`\n\n"
            "Type /cancel to cancel."
        )
        
        context.user_data['awaiting_replacement'] = True
        return self.WAITING_FOR_SETTING
    
    async def reset_settings_callback(self, query):
        """Reset settings to default"""
        user = query.from_user
        
        default_settings = {
            "auto_delete_duplicates": True,
            "replace_url_with": Config.URL_REPLACEMENT_TEXT,
            "language": "en",
            "notifications": True
        }
        
        await self.db.update_user_settings(user.id, default_settings)
        
        await query.edit_message_text(
            "✅ **Settings Reset!**\n\n"
            "All settings have been reset to default values.",
            parse_mode='Markdown'
        )
    
    async def view_files_callback(self, query):
        """View user files"""
        user = query.from_user
        files = await self.db.get_user_files(user.id, limit=10)
        
        if not files:
            await query.edit_message_text(
                "📁 **Your Files**\n\n"
                "No files processed yet. Send me a video to get started!",
                parse_mode='Markdown'
            )
            return
        
        files_message = "📁 **Your Recent Files**\n\n"
        
        for i, file in enumerate(files, 1):
            file_name = file.get('file_name', 'Unknown')
            timestamp = file.get('timestamp', '').strftime('%Y-%m-%d %H:%M') if file.get('timestamp') else 'N/A'
            size_mb = file.get('file_size', 0) / (1024 * 1024)
            urls = file.get('urls_found', 0)
            
            files_message += f"**{i}. {file_name[:30]}...**\n"
            files_message += f"   • Size: {size_mb:.1f}MB\n"
            files_message += f"   • URLs removed: {urls}\n"
            files_message += f"   • Date: {timestamp}\n\n"
        
        keyboard = [[
            InlineKeyboardButton("🗑️ Delete All Files", callback_data="confirm_delete_files"),
            InlineKeyboardButton("🏠 Home", callback_data="home")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            files_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def delete_files_callback(self, query):
        """Delete user files confirmation"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Delete All", callback_data="confirm_delete_all_files"),
                InlineKeyboardButton("❌ Cancel", callback_data="home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚠️ **Delete All Files?**\n\n"
            "This will delete **all** your processed file records from our database.\n"
            "This action cannot be undone!\n\n"
            "Are you sure you want to continue?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def refresh_stats_callback(self, query):
        """Refresh statistics"""
        await self.stats_command_callback(query)
    
    # Additional command handlers
    async def files_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /files command"""
        await self.view_files_callback(update.callback_query)
    
    async def delete_files_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_my_files command"""
        user = update.effective_user
        
        # Confirm deletion
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Delete Everything", callback_data="confirm_delete_all"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **Delete All Your Data?**\n\n"
            "This will delete:\n"
            "• All your file records\n"
            "• Your processing history\n"
            "• Your statistics\n\n"
            "This action is **permanent** and cannot be undone!\n\n"
            "Are you sure?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def about_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /about command"""
        about_message = f"""
🤖 **About {Config.BOT_NAME}**

**Version:** 1.0.0
**Author:** Your Name
**Description:** A Telegram bot to remove URLs from video content and text messages

**Features:**
✅ URL removal from text and video captions
✅ Automatic duplicate file detection
✅ MongoDB database for data storage
✅ User statistics and history
✅ Customizable settings
✅ Admin panel for management

**Technology Stack:**
• Python 3.11
• python-telegram-bot library
• MongoDB database
• Docker containerization
• Koyeb deployment

**Privacy:**
• We store only necessary user data
• Files are processed temporarily
• You can delete your data anytime
• No sharing with third parties

**Source Code:** [GitHub Repository](https://github.com/yourusername/telegram-url-remover-bot)

**Support:** @your_support_username

**Thank you for using our bot!** ❤️
"""
        
        await update.message.reply_text(about_message, parse_mode='Markdown')
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command (admin only)"""
        user = update.effective_user
        
        if user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Access denied. Admin only.")
            return
        
        # Admin panel
        admin_message = """
👑 **Admin Panel**

**Quick Actions:**
• /broadcast - Broadcast message to all users
• /system_stats - View system statistics
• /admin_users - Manage users
• /admin_settings - Bot settings

**Server Status:**
• Bot: Online
• Database: Connected
• Storage: Normal

**Maintenance:**
• Cleanup temporary files
• Backup database
• Update settings
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"),
                InlineKeyboardButton("👥 User Management", callback_data="admin_users")
            ],
            [
                InlineKeyboardButton("🔧 Settings", callback_data="admin_settings"),
                InlineKeyboardButton("🧹 Cleanup", callback_data="admin_cleanup")
            ],
            [
                InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
                InlineKeyboardButton("🚪 Exit Admin", callback_data="home")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            admin_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /broadcast command (admin only)"""
        user = update.effective_user
        
        if user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Access denied. Admin only.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "**Usage:** `/broadcast <message>`\n\n"
                "Example: `/broadcast Hello users! Bot will be down for maintenance tomorrow.`",
                parse_mode='Markdown'
            )
            return
        
        message = ' '.join(context.args)
        
        # Get all users
        users = await self.db.get_all_users()
        
        if not users:
            await update.message.reply_text("No users to broadcast to.")
            return
        
        # Confirm broadcast
        keyboard = [
            [
                InlineKeyboardButton("✅ Send to All Users", callback_data=f"confirm_broadcast:{len(users)}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store message in context for confirmation
        context.user_data['broadcast_message'] = message
        
        await update.message.reply_text(
            f"📢 **Broadcast Confirmation**\n\n"
            f"**Message:**\n{message[:200]}...\n\n"
            f"**Recipients:** {len(users)} users\n\n"
            f"Are you sure you want to send this broadcast?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def system_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /system_stats command (admin only)"""
        user = update.effective_user
        
        if user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("❌ Access denied. Admin only.")
            return
        
        # Get system stats
        system_stats = await self.db.get_system_stats()
        storage_info = self.file_manager.get_storage_info()
        
        # Get recent users
        recent_users = await self.db.get_all_users(limit=5)
        
        stats_message = """
📈 **System Statistics**

**Database:**
• Total Users: {total_users}
• Total Files: {total_files}
• Total Requests: {total_requests}
• Today's Requests: {today_requests}
• Today's Active Users: {today_users}

**Storage:**
• Temp Files: {temp_files} ({temp_size_mb:.1f}MB)
• Processed Files: {processed_files} ({processed_size_mb:.1f}MB)
• Trash Files: {trash_files} ({trash_size_mb:.1f}MB)

**Recent Users:**
""".format(
            total_users=system_stats.get('total_users', 0),
            total_files=system_stats.get('total_files', 0),
            total_requests=system_stats.get('total_requests', 0),
            today_requests=system_stats.get('today_requests', 0),
            today_users=system_stats.get('today_users', 0),
            temp_files=storage_info.get('temp_files', 0),
            temp_size_mb=storage_info.get('temp_size', 0) / (1024 * 1024),
            processed_files=storage_info.get('processed_files', 0),
            processed_size_mb=storage_info.get('processed_size', 0) / (1024 * 1024),
            trash_files=storage_info.get('trash_files', 0),
            trash_size_mb=storage_info.get('trash_size', 0) / (1024 * 1024)
        )
        
        if recent_users:
            for i, user_data in enumerate(recent_users, 1):
                username = user_data.get('username', 'No username')
                first_name = user_data.get('first_name', '')
                join_date = user_data.get('join_date', '').strftime('%m-%d') if user_data.get('join_date') else 'N/A'
                requests = user_data.get('total_requests', 0)
                
                stats_message += f"{i}. {first_name} (@{username}) - {requests} req - Joined: {join_date}\n"
        
        await update.message.reply_text(stats_message, parse_mode='Markdown')
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Exception while handling update: {context.error}", exc_info=True)
        
        try:
            # Try to notify the user
            error_message = Config.ERROR_MESSAGE
            
            if update and update.effective_message:
                await update.effective_message.reply_text(error_message)
        except:
            pass
        
        # Log the error to database
        try:
            user_id = update.effective_user.id if update and update.effective_user else 0
            await self.db.log_activity({
                "user_id": user_id,
                "action": "error",
                "details": {
                    "error": str(context.error)[:200],
                    "update": str(update)[:100] if update else "None"
                }
            })
        except:
            pass
    
    async def run(self):
        """Run the bot"""
        # Start periodic cleanup task
        asyncio.create_task(self._periodic_cleanup())
        
        # Start the bot
        logger.info("🤖 Bot is running... Press Ctrl+C to stop")
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Keep running until stopped
        await asyncio.Event().wait()
    
    async def _periodic_cleanup(self):
        """Periodic cleanup task"""
        import asyncio
        
        while True:
            try:
                # Wait for 6 hours
                await asyncio.sleep(6 * 3600)
                
                # Cleanup temp files
                await self.file_manager.cleanup_temp_files(older_than_hours=24)
                
                # Cleanup old database data
                await self.db.cleanup_old_data(days=30)
                
                logger.info("✅ Periodic cleanup completed")
                
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
