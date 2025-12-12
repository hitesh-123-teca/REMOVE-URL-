"""
Bot command and message handlers
"""

import os
import tempfile
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, InputFile, InputMediaVideo
from telegram.ext import ContextTypes, CallbackContext
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError

from config import Config
from helpers import format_size, format_time, create_progress_message

class BotHandlers:
    """All bot command and message handlers"""
    
    def __init__(self, db, processor):
        self.db = db
        self.processor = processor
        self.temp_dir = "temp"
        
    # ========== COMMAND HANDLERS ==========
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with welcome message"""
        welcome_text = """
🤖 *Video Forward Bot Started!*

*🌟 Features:*
✅ MongoDB Database Storage
✅ Unlimited File Forwarding
✅ Admin-Only Channel Setup (No ID Entry)
✅ Auto Duplicate Detection & Delete
✅ URL Removal from Captions
✅ Auto Thumbnail Generation (3-5 sec frame)
✅ Basic Watermark Removal
✅ Welcome Message
✅ Koyeb Deployment Ready

*📋 Setup Commands:*
/set_source - Set source channel (send in source channel)
/set_target - Set target channel (send in target channel)
/stats - Show bot statistics
/settings - Configure bot settings
/help - Show help guide

*⚙️ Setup Instructions:*
1. Add bot as *ADMIN* in both channels
2. Use /set_source in source channel
3. Use /set_target in target channel
4. Start sending videos!

*🔄 Auto Processing:*
• Removes URLs from captions
• Generates thumbnails automatically
• Detects & removes duplicate files
• Forwards to target channel
• Supports unlimited file sizes

*📊 Status:* ✅ Active
*🔧 Version:* 2.0.0
*👨‍💻 Support:* Contact for help
"""
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        # Save user info
        user = update.effective_user
        self.db.save_user({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined_at": datetime.now(),
            "last_seen": datetime.now()
        })
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        help_text = """
🆘 *Help Guide*

*📌 Available Commands:*
• /start - Start the bot
• /help - Show this help
• /set_source - Set source channel
• /set_target - Set target channel
• /stats - Show statistics
• /settings - Configure bot
• /clear_duplicates - Clear duplicate records

*🔧 Setup Steps:*
1. Add bot as ADMIN in both channels
2. In source channel: /set_source
3. In target channel: /set_target
4. Start sending videos in source channel

*⚡ Features Explained:*
• *Auto URL Removal:* Removes all links from captions
• *Auto Thumbnail:* Takes frame at 3-5 seconds
• *Duplicate Detection:* Auto-deletes duplicate files
• *Watermark Removal:* Basic watermark removal
• *Unlimited Size:* No file size restrictions

*⚠️ Troubleshooting:*
• Bot not forwarding? Check admin permissions
• Duplicates not deleting? Check bot permissions in target channel
• Caption not cleaned? Check URL patterns

*📞 Support:* Contact administrator
"""
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def set_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set source channel"""
        try:
            chat = update.effective_chat
            
            # Check if private chat
            if chat.type == "private":
                await update.message.reply_text(
                    "❌ Please use this command in the *source channel* where you want to forward videos FROM.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Check admin status
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ["administrator", "creator"]:
                    await update.message.reply_text(
                        "❌ *Bot must be ADMIN in this channel!*\n\n"
                        "Please promote me to admin first with these permissions:\n"
                        "• Post Messages\n"
                        "• Edit Messages\n"
                        "• Delete Messages",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
            except TelegramError as e:
                await update.message.reply_text(
                    f"❌ Error checking admin status: {str(e)}"
                )
                return
            
            # Save channel info
            self.db.save_channel({
                "chat_id": str(chat.id),
                "title": chat.title,
                "username": chat.username,
                "type": chat.type,
                "is_source": True,
                "is_target": False,
                "set_at": datetime.now(),
                "set_by": update.effective_user.id
            })
            
            # Update bot settings
            self.db.update_bot_settings(
                context.bot.id,
                {
                    "source_channel": str(chat.id),
                    "source_title": chat.title,
                    "source_username": chat.username
                }
            )
            
            await update.message.reply_text(
                f"✅ *Source channel set successfully!*\n\n"
                f"📢 Channel: {chat.title}\n"
                f"🆔 ID: `{chat.id}`\n"
                f"👤 Type: {chat.type}\n\n"
                f"Bot will now forward videos from this channel.\n"
                f"Next step: Go to target channel and use /set_target",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error setting source channel: {str(e)}"
            )
    
    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target channel"""
        try:
            chat = update.effective_chat
            
            # Check if private chat
            if chat.type == "private":
                await update.message.reply_text(
                    "❌ Please use this command in the *target channel* where you want to forward videos TO.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Check admin status
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ["administrator", "creator"]:
                    await update.message.reply_text(
                        "❌ *Bot must be ADMIN in this channel!*\n\n"
                        "Please promote me to admin first with these permissions:\n"
                        "• Post Messages\n"
                        "• Edit Messages\n"
                        "• Delete Messages",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
            except TelegramError as e:
                await update.message.reply_text(
                    f"❌ Error checking admin status: {str(e)}"
                )
                return
            
            # Save channel info
            self.db.save_channel({
                "chat_id": str(chat.id),
                "title": chat.title,
                "username": chat.username,
                "type": chat.type,
                "is_source": False,
                "is_target": True,
                "set_at": datetime.now(),
                "set_by": update.effective_user.id
            })
            
            # Update bot settings
            self.db.update_bot_settings(
                context.bot.id,
                {
                    "target_channel": str(chat.id),
                    "target_title": chat.title,
                    "target_username": chat.username
                }
            )
            
            await update.message.reply_text(
                f"✅ *Target channel set successfully!*\n\n"
                f"📢 Channel: {chat.title}\n"
                f"🆔 ID: `{chat.id}`\n"
                f"👤 Type: {chat.type}\n\n"
                f"Bot will now forward videos to this channel.\n"
                f"Setup complete! Start sending videos in source channel.",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error setting target channel: {str(e)}"
            )
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        try:
            # Get statistics
            total_stats = self.db.get_total_stats()
            daily_stats = self.db.get_daily_stats(7)
            file_count = self.db.get_file_count()
            
            # Get bot settings
            settings = self.db.get_bot_settings(context.bot.id)
            
            # Format statistics
            stats_text = f"""
📊 *Bot Statistics*

*📈 Overall Stats:*
├─ Total Files: `{total_stats.get('total_files', 0)}`
├─ Total Chats: `{total_stats.get('total_chats', 0)}`
├─ Files Today: `{self.db.get_file_count():,}`
└─ Database Size: `Calculating...`

*📅 Last 7 Days:*
"""
            
            for stat in daily_stats:
                date_str = stat["_id"].strftime("%Y-%m-%d")
                stats_text += f"├─ {date_str}: `{stat.get('total_files', 0)}` files\n"
            
            stats_text += f"""
*🔧 Bot Settings:*
├─ Source Channel: {'✅ Set' if settings and 'source_channel' in settings else '❌ Not Set'}
├─ Target Channel: {'✅ Set' if settings and 'target_channel' in settings else '❌ Not Set'}
├─ Auto Thumbnail: {'✅ Enabled' if Config.AUTO_THUMBNAIL else '❌ Disabled'}
└─ Duplicate Check: {'✅ Enabled' if Config.CHECK_DUPLICATES else '❌ Disabled'}

*⚙️ System Status:*
├─ Bot: ✅ Online
├─ Database: ✅ Connected
├─ Storage: ✅ Available
└─ Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error getting statistics: {str(e)}"
            )
    
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configure bot settings"""
        settings_text = """
⚙️ *Bot Settings*

*Current Configuration:*
• Auto Thumbnail: Enabled
• Duplicate Check: Enabled
• Watermark Removal: Disabled
• Max File Size: 2GB

*To change settings:* Edit .env file and restart bot.

*Environment Variables:*
