"""
Configuration settings for the bot
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration class"""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "telegram_video_bot")
    
    # Bot Settings
    ADMIN_ID = os.getenv("ADMIN_ID")
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 2000000000))  # 2GB default
    
    # Video Processing
    THUMBNAIL_TIME = int(os.getenv("THUMBNAIL_TIME", 4))  # seconds
    REMOVE_WATERMARK = os.getenv("REMOVE_WATERMARK", "false").lower() == "true"
    AUTO_THUMBNAIL = os.getenv("AUTO_THUMBNAIL", "true").lower() == "true"
    
    # Duplicate Detection
    CHECK_DUPLICATES = os.getenv("CHECK_DUPLICATES", "true").lower() == "true"
    DELETE_DUPLICATES = os.getenv("DELETE_DUPLICATES", "true").lower() == "true"
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Koyeb/Server
    PORT = int(os.getenv("PORT", 8080))
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
            
        if not cls.MONGO_URI:
            errors.append("MONGO_URI is required")
            
        if errors:
            raise ValueError("\n".join(errors))
            
        return True
