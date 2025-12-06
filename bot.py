#!/usr/bin/env python3
"""
Telegram URL Removal Bot - Main Entry Point
Author: Your Name
Version: 1.0.0
Description: This bot removes URLs from video captions and text messages
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import Config
from src.bot_instance import TelegramBot

# Setup logging
def setup_logging():
    """Configure logging for the application"""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

async def main():
    """Main async function to run the bot"""
    logger = setup_logging()
    
    # Check required environment variables
    if not Config.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found in environment variables!")
        sys.exit(1)
    
    if not Config.MONGO_URI:
        logger.warning("⚠️ MONGO_URI not found, using local database")
    
    try:
        # Initialize bot
        bot = TelegramBot(
            token=Config.BOT_TOKEN,
            mongo_uri=Config.MONGO_URI
        )
        
        logger.info("=" * 50)
        logger.info("🚀 Starting Telegram URL Removal Bot")
        logger.info(f"📱 Bot Name: {Config.BOT_NAME}")
        logger.info(f"👤 Admin IDs: {Config.ADMIN_IDS}")
        logger.info(f"💾 Database: {Config.MONGO_URI[:20]}...")
        logger.info("=" * 50)
        
        # Start the bot
        await bot.run()
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
        sys.exit(0)
