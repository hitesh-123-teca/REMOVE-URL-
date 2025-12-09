#!/usr/bin/env python3
"""
Simple Telegram Bot - No Health Check
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.bot_instance import TelegramBot

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

async def main():
    logger = setup_logging()
    
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    MONGO_URI = os.getenv('MONGO_URI')
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found!")
        sys.exit(1)
    
    if not MONGO_URI:
        logger.warning("MONGO_URI not found, using local")
        MONGO_URI = "mongodb://localhost:27017/"
    
    try:
        bot = TelegramBot(
            token=BOT_TOKEN,
            mongo_uri=MONGO_URI
        )
        
        logger.info("🚀 Starting Telegram URL Removal Bot")
        logger.info(f"💾 Database: {MONGO_URI[:20]}...")
        
        await bot.run()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
        sys.exit(0)
