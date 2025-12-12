"""
Bot command and message handlers
"""

import os
import tempfile
import asyncio
from datetime import datetime
from typing import Dict, Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config import Config
from helpers import format_size, create_progress_message


class BotHandlers:
    """All bot command and message handlers"""

    def __init__(self, db, processor):
        self.db = db
        self.processor = processor
        self.temp_dir = "temp"

    # =========================================================
    # START COMMAND
    # =========================================================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with welcome message"""

        welcome_text = """
🤖 *Video Forward Bot Started!*

🌟 *Features:*
• MongoDB Database Storage
• Unlimited File Forwarding
• Admin-Only Channel Setup
• Auto Duplicate Detection & Delete
• URL Removal from Captions
• Auto Thumbnail Generation (3–5 sec frame)
• Basic Watermark Removal
• Welcome Message
• Koyeb Deployment Ready

📋 *Setup Commands:*
/set_source - Set source channel
/set_target - Set target channel
/stats - Show bot statistics
/settings - Configure bot settings
/help - Show help guide

⚙️ *Setup Instructions:*
1. Add bot as *ADMIN* in both channels  
2. Use `/set_source` in source channel  
3. Use `/set_target` in target channel  
4. Start sending videos!

🔄 *Auto Processing:*
• Removes URLs from captions  
• Generates thumbnails automatically  
• Detects & removes duplicates  
• Forwards to target channel  
• Unlimited file sizes supported  

📊 *Status:* Active  
🔧 *Version:* 2.0.0
"""

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

        # Save user data
        user = update.effective_user
        self.db.save_user({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined_at": datetime.now(),
            "last_seen": datetime.now()
        })

    # =========================================================
    # HELP COMMAND
    # =========================================================

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""

        help_text = """
🆘 *Help Guide*

📌 *Commands:*
• /start  
• /help  
• /set_source  
• /set_target  
• /stats  
• /settings  
• /clear_duplicates  

⚡ *Features Explained:*
• Auto URL Removal  
• Auto Thumbnail  
• Duplicate Removal  
• Watermark Removal  
• Unlimited Size Support  

⚠️ *Troubleshooting:*
• Check admin permissions  
• Check duplicate settings  
• Check caption cleaning patterns
"""

        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    # =========================================================
    # SET SOURCE CHANNEL
    # =========================================================

    async def set_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set source channel"""

        try:
            chat = update.effective_chat

            if chat.type == "private":
                await update.message.reply_text(
                    "❌ Use this command *inside the source channel*.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Admin check
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ["administrator", "creator"]:
                    await update.message.reply_text(
                        "❌ Bot must be *ADMIN* in this channel.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
            except TelegramError as e:
                await update.message.reply_text(f"❌ Admin check failed: {e}")
                return

            # Save channel
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

            self.db.update_bot_settings(
                context.bot.id,
                {
                    "source_channel": str(chat.id),
                    "source_title": chat.title,
                    "source_username": chat.username
                }
            )

            await update.message.reply_text(
                f"✅ *Source channel set!*\n"
                f"📢 {chat.title}\n🆔 `{chat.id}`\n\n"
                f"Next: Go to target channel and send /set_target",
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # =========================================================
    # SET TARGET CHANNEL
    # =========================================================

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target channel"""

        try:
            chat = update.effective_chat

            if chat.type == "private":
                await update.message.reply_text(
                    "❌ Use this command *inside the target channel*.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            # Admin check
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ["administrator", "creator"]:
                    await update.message.reply_text(
                        "❌ Bot must be ADMIN here.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
            except TelegramError as e:
                await update.message.reply_text(f"❌ Admin check error: {e}")
                return

            # Save channel
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

            self.db.update_bot_settings(
                context.bot.id,
                {
                    "target_channel": str(chat.id),
                    "target_title": chat.title,
                    "target_username": chat.username
                }
            )

            await update.message.reply_text(
                f"✅ *Target channel set!*\n"
                f"📢 {chat.title}\n🆔 `{chat.id}`\n\n"
                f"Setup complete!",
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # =========================================================
    # BOT STATISTICS
    # =========================================================

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""

        try:
            total_stats = self.db.get_total_stats()
            daily_stats = self.db.get_daily_stats(7)
            settings = self.db.get_bot_settings(context.bot.id)

            stats_text = f"""
📊 *Bot Statistics*

📈 *Overall:*
• Total Files: `{total_stats.get('total_files', 0)}`
• Total Chats: `{total_stats.get('total_chats', 0)}`
• Files Today: `{self.db.get_file_count():,}`

📅 *Last 7 Days:*
"""
            for stat in daily_stats:
                stats_text += f"• {stat['_id'].strftime('%Y-%m-%d')}: `{stat.get('total_files', 0)}` files\n"

            stats_text += f"""
🔧 *Bot Settings:*
• Source Channel: {'Set' if settings and 'source_channel' in settings else 'Not Set'}
• Target Channel: {'Set' if settings and 'target_channel' in settings else 'Not Set'}
• Auto Thumbnail: {'Enabled' if Config.AUTO_THUMBNAIL else 'Disabled'}
• Duplicate Check: {'Enabled' if Config.CHECK_DUPLICATES else 'Disabled'}

⚙️ *System Status:*
• Bot: Online  
• Database: Connected  
"""

            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # =========================================================
    # BOT SETTINGS
    # =========================================================

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot settings"""

        settings_text = """
⚙️ *Bot Settings*

*Current Configuration:*
• Auto Thumbnail: Enabled
• Duplicate Check: Enabled
• Watermark Removal: Disabled
• Max File Size: 2GB

*To change settings:* Edit `.env` file and restart bot.

*Environment Variables:*
• AUTO_THUMBNAIL  
• CHECK_DUPLICATES  
• WATERMARK_REMOVAL  
• MAX_FILE_SIZE  
"""

        await update.message.reply_text(
            settings_text,
            parse_mode=ParseMode.MARKDOWN
        )
