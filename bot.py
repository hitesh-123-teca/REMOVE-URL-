#!/usr/bin/env python3
"""
Telegram Auto Forward Bot
Simple version for Koyeb deployment
"""

import os
import re
import sys
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
SOURCE_CHANNEL = os.getenv('SOURCE_CHANNEL')
DESTINATION_CHANNEL = os.getenv('DESTINATION_CHANNEL')

print(f"""
🤖 Telegram Auto Forward Bot
🚀 Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📡 Source: {SOURCE_CHANNEL}
🎯 Destination: {DESTINATION_CHANNEL}
""")

# URL removal function
def remove_urls(text):
    """Remove all URLs from text"""
    if not text:
        return ""
    
    patterns = [
        r'https?://\S+',
        r't\.me/\S+',
        r'@\w+',
        r'bit\.ly/\S+',
        r'tinyurl\.com/\S+',
        r'wa\.me/\S+',
        r'youtu\.be/\S+',
        r'instagram\.com/\S+',
        r'facebook\.com/\S+',
        r'twitter\.com/\S+',
    ]
    
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

# Initialize Telegram client
client = TelegramClient(StringSession(), API_ID, API_HASH)

# Start bot
client.start(bot_token=BOT_TOKEN)

@client.on(events.NewMessage(chats=int(SOURCE_CHANNEL)))
async def forward_handler(event):
    """Handle new messages and forward videos"""
    try:
        # Check if message has video
        if event.message.video:
            print(f"🎬 Video detected: Message ID {event.message.id}")
            
            # Get and clean caption
            original_caption = event.message.text or event.message.caption or ""
            cleaned_caption = remove_urls(original_caption)
            
            # Add timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            if cleaned_caption:
                final_caption = f"{cleaned_caption}\n\n🕐 {timestamp}"
            else:
                final_caption = f"🕐 {timestamp}"
            
            # Forward the video
            await client.send_file(
                int(DESTINATION_CHANNEL),
                event.message.video,
                caption=final_caption,
                supports_streaming=True
            )
            
            print(f"✅ Video forwarded successfully!")
            
            # Log details
            print(f"📝 Original: {original_caption[:50]}...")
            print(f"🧹 Cleaned: {cleaned_caption[:50]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Handle /start command"""
    await event.reply(f"""
🤖 Auto Forward Bot Started!
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ Features:
• Auto forward videos
• Remove URLs from captions
• 24/7 running on Koyeb

📡 Source: {SOURCE_CHANNEL}
🎯 Destination: {DESTINATION_CHANNEL}
    """)

@client.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Handle /help command"""
    await event.reply("""
🆘 Help Guide:

This bot automatically forwards videos from source channel to destination channel.

🔧 Setup:
1. Add bot as admin in both channels
2. Set environment variables:
   - API_ID, API_HASH
   - BOT_TOKEN
   - SOURCE_CHANNEL
   - DESTINATION_CHANNEL

🤖 Commands:
/start - Start bot
/help - Show this message

📞 Support: Contact admin for help.
    """)

@client.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    """Handle /status command"""
    await event.reply(f"""
🔄 Bot Status
━━━━━━━━━━━━━
✅ Status: Running
🕐 Time: {datetime.now().strftime('%H:%M:%S')}
📡 Source: Active
🎯 Destination: Active
━━━━━━━━━━━━━
Bot is monitoring for videos...
    """)

print("🤖 Bot is running and monitoring for videos...")
print("Press Ctrl+C to stop")

# Run the bot
client.run_until_disconnected()
