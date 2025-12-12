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
        welcome_text = """
🤖 *Video Forward Bot Started!*

*🌟 Features:*
✅ MongoDB Database Storage
✅ Unlimited File Forwarding
✅ Admin-Only Channel Setup (No ID Entry)
✅ Auto Duplicate Detection & Delete
✅ URL Removal from Captions
✅ Auto Thumbnail Generation (3–5 sec)
✅ Basic Watermark Removal
✅ Welcome Message
✅ Koyeb Deployment Ready

📋 *Setup Commands:*
/set_source  
/set_target  
/stats  
/settings  
/help  

⚙️ *Setup:*
1. Add bot as ADMIN in both channels  
2. Use /set_source in source channel  
3. Use /set_target in target channel  

📊 *Status:* Active  
🔧 *Version:* 2.0.0
"""
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

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
        help_text = """
🆘 *Help Guide*

📌 *Commands:*
/start  
/help  
/set_source  
/set_target  
/stats  
/settings  
/clear_duplicates  

⚡ *Features:*
• Auto URL Removal  
• Auto Thumbnail  
• Duplicate Detection  
• Watermark Removal  
• Unlimited Video Support  

⚠️ *Troubleshooting:*
• Check admin permissions  
• Check duplicate settings  
• Check caption cleaning  
"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    # =========================================================
    # SET SOURCE CHANNEL
    # =========================================================
    async def set_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            chat = update.effective_chat

            if chat.type == "private":
                await update.message.reply_text(
                    "❌ Use this command *in the source channel*.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status not in ["administrator", "creator"]:
                await update.message.reply_text(
                    "❌ Bot must be ADMIN in this channel.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

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

            self.db.update_bot_settings(context.bot.id, {
                "source_channel": str(chat.id),
                "source_title": chat.title,
                "source_username": chat.username
            })

            await update.message.reply_text(
                f"✅ *Source channel set!*\n📢 {chat.title}\n🆔 `{chat.id}`",
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # =========================================================
    # SET TARGET CHANNEL
    # =========================================================
    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            chat = update.effective_chat

            if chat.type == "private":
                await update.message.reply_text(
                    "❌ Use this in the target channel.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status not in ["administrator", "creator"]:
                await update.message.reply_text(
                    "❌ Bot must be ADMIN in this channel.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

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

            self.db.update_bot_settings(context.bot.id, {
                "target_channel": str(chat.id),
                "target_title": chat.title,
                "target_username": chat.username
            })

            await update.message.reply_text(
                f"✅ *Target channel set!*\n📢 {chat.title}\n🆔 `{chat.id}`",
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # =========================================================
    # STATS
    # =========================================================
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            total = self.db.get_total_stats()
            daily = self.db.get_daily_stats(7)
            settings = self.db.get_bot_settings(context.bot.id)

            stats_text = f"""
📊 *Bot Statistics*

📈 *Overall:*
• Total Files: `{total.get('total_files',0)}`
• Total Chats: `{total.get('total_chats',0)}`
• Files Today: `{self.db.get_file_count():,}`

📅 *Last 7 Days:*
"""
            for stat in daily:
                stats_text += f"• {stat['_id'].strftime('%Y-%m-%d')}: `{stat.get('total_files',0)}` files\n"

            stats_text += f"""
🔧 *Settings:*
• Source Channel: {'Set' if settings and 'source_channel' in settings else 'Not Set'}
• Target Channel: {'Set' if settings and 'target_channel' in settings else 'Not Set'}

⚙️ Status:
• Bot: Online  
• DB: Connected  
"""

            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    # =========================================================
    # SETTINGS PAGE
    # =========================================================
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings_text = """
⚙️ *Bot Settings*

*Current Configuration:*
• Auto Thumbnail: Enabled  
• Duplicate Check: Enabled  
• Watermark Removal: Disabled  
• Max File Size: 2GB  

*To change settings: Edit `.env` file*

*Environment Variables:*
• AUTO_THUMBNAIL  
• CHECK_DUPLICATES  
• WATERMARK_REMOVAL  
• MAX_FILE_SIZE  
"""
        await update.message.reply_text(settings_text, parse_mode=ParseMode.MARKDOWN)

    # =========================================================
    # CLEAR DUPLICATES  ✅ FIX ADDED
    # =========================================================
    async def clear_duplicates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear duplicate file records from database"""
        try:
            deleted = self.db.clear_duplicate_records()

            await update.message.reply_text(
                f"🧹 *Duplicate Cleanup Completed!*\n"
                f"🗑️ Deleted Duplicate Entries: `{deleted}`",
                parse_mode=ParseMode.MARKDOWN
            )

        except Exception as e:
            await update.message.reply_text(
                f"❌ Error clearing duplicates: {e}"
            )
