"""
Core bot functionality
"""

import os
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext
)
from telegram.constants import ParseMode

from config import Config
from database import MongoDB
from video_processor import VideoProcessor
from bot_handlers import BotHandlers
from helpers import cleanup_temp_files

class VideoForwardBot:
    def __init__(self):
        self.config = Config()
        self.db = MongoDB()
        self.processor = VideoProcessor()
        self.handlers = BotHandlers(self.db, self.processor)
        
        # Create temp directory
        os.makedirs("temp", exist_ok=True)
        
    async def run(self):
        """Start the bot"""
        # Check token
        if not self.config.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        
        # Initialize bot application
        self.application = Application.builder() \
            .token(self.config.TELEGRAM_BOT_TOKEN) \
            .post_init(self.on_startup) \
            .post_shutdown(self.on_shutdown) \
            .build()
        
        # Register handlers
        self.register_handlers()
        
        # Start bot
        print("🤖 Bot is running...")
        print("Press Ctrl+C to stop")
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
        # Keep running
        await self.idle()
        
    async def idle(self):
        """Keep bot running until interrupted"""
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
            
    def register_handlers(self):
        """Register all command and message handlers"""
        app = self.application
        
        # Command handlers
        app.add_handler(CommandHandler("start", self.handlers.start))
        app.add_handler(CommandHandler("help", self.handlers.help_command))
        app.add_handler(CommandHandler("set_source", self.handlers.set_source))
        app.add_handler(CommandHandler("set_target", self.handlers.set_target))
        app.add_handler(CommandHandler("stats", self.handlers.stats))
        app.add_handler(CommandHandler("settings", self.handlers.settings))
        app.add_handler(CommandHandler("clear_duplicates", self.handlers.clear_duplicates))
        
        # Message handlers
        app.add_handler(MessageHandler(
            filters.VIDEO | filters.Document.VIDEO,
            self.handlers.handle_video
        ))
        
        # Error handler
        app.add_error_handler(self.handlers.error_handler)
        
    async def on_startup(self, application: Application):
        """Run on bot startup"""
        print("\n✅ Bot started successfully!")
        print("📊 Database connected")
        print("⚙️  All handlers registered")
        print("🚀 Ready to forward videos")
        
        # Send startup notification if configured
        if self.config.ADMIN_ID:
            try:
                await application.bot.send_message(
                    chat_id=self.config.ADMIN_ID,
                    text=f"✅ Bot started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                print(f"⚠️  Failed to send startup notification: {e}")
                
    async def on_shutdown(self, application: Application):
        """Run on bot shutdown"""
        print("\n🛑 Bot shutting down...")
        cleanup_temp_files()
        print("✅ Cleanup completed")
        
        # Send shutdown notification if configured
        if self.config.ADMIN_ID:
            try:
                await application.bot.send_message(
                    chat_id=self.config.ADMIN_ID,
                    text=f"🛑 Bot stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception:
                pass
