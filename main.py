#!/usr/bin/env python3
"""
Telegram Video Forward Bot
Main entry point with all features:
1. MongoDB Database
2. Unlimited File Forwarding
3. Admin-based Channel Setup
4. Duplicate Auto-Delete
5. URL Removal from Captions
6. Auto Thumbnail Generation
7. Watermark Removal
8. Welcome Message
9. Koyeb Deployment Ready
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """Main async function to start the bot"""
    try:
        from bot_core import VideoForwardBot
        bot = VideoForwardBot()
        await bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Create logs directory if not exists
    os.makedirs("logs", exist_ok=True)
    
    print("\n" + "="*60)
    print("🎬 TELEGRAM VIDEO FORWARD BOT")
    print("="*60)
    print("✅ Starting bot with all features...")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")
    
    # Run bot
    asyncio.run(main())
