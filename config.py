"""
Configuration settings for the bot
"""

import os
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration class"""
    
    # Telegram Bot Token
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    
    # MongoDB
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "telegram_video_bot")
    
    # Bot Settings
    ADMIN_ID: Optional[str] = os.getenv("ADMIN_ID")
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", 2000000000))  # 2GB default
    
    # Video Processing
    THUMBNAIL_TIME: int = int(os.getenv("THUMBNAIL_TIME", 4))  # seconds
    REMOVE_WATERMARK: bool = os.getenv("REMOVE_WATERMARK", "false").lower() == "true"
    AUTO_THUMBNAIL: bool = os.getenv("AUTO_THUMBNAIL", "true").lower() == "true"
    
    # Duplicate Detection
    CHECK_DUPLICATES: bool = os.getenv("CHECK_DUPLICATES", "true").lower() == "true"
    DELETE_DUPLICATES: bool = os.getenv("DELETE_DUPLICATES", "true").lower() == "true"
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Koyeb/Server
    PORT: int = int(os.getenv("PORT", 8080))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration"""
        errors = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
            
        if not cls.MONGO_URI:
            errors.append("MONGO_URI is required")
            
        if errors:
            raise ValueError("\n".join(errors))
            
        return True
