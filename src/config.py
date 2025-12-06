"""
Configuration settings for the Telegram URL Removal Bot
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for the application"""
    
    # Telegram Bot Configuration
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
    BOT_NAME: str = os.getenv('BOT_NAME', 'URL Remover Bot')
    
    # Parse admin IDs from comma-separated string
    ADMIN_IDS_STR: str = os.getenv('ADMIN_IDS', '')
    ADMIN_IDS: List[int] = [
        int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') 
        if admin_id.strip().isdigit()
    ]
    
    # MongoDB Configuration
    MONGO_URI: str = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME: str = os.getenv('MONGO_DB_NAME', 'url_remover_bot')
    
    # Application Settings
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()
    MAX_FILE_SIZE: int = int(os.getenv('MAX_FILE_SIZE', '52428800'))  # 50MB
    MAX_MESSAGE_LENGTH: int = int(os.getenv('MAX_MESSAGE_LENGTH', '4000'))
    
    # Parse supported formats
    SUPPORTED_FORMATS_STR: str = os.getenv('SUPPORTED_FORMATS', '.mp4,.avi,.mov,.mkv,.webm')
    SUPPORTED_FORMATS: List[str] = [
        fmt.strip().lower() for fmt in SUPPORTED_FORMATS_STR.split(',')
    ]
    
    # Server Configuration
    PORT: int = int(os.getenv('PORT', '8080'))
    HOST: str = os.getenv('HOST', '0.0.0.0')
    
    # Feature Toggles
    ENABLE_DUPLICATE_CHECK: bool = os.getenv('ENABLE_DUPLICATE_CHECK', 'true').lower() == 'true'
    ENABLE_URL_REMOVAL: bool = os.getenv('ENABLE_URL_REMOVAL', 'true').lower() == 'true'
    ENABLE_STATISTICS: bool = os.getenv('ENABLE_STATISTICS', 'true').lower() == 'true'
    ENABLE_WELCOME_MESSAGE: bool = os.getenv('ENABLE_WELCOME_MESSAGE', 'true').lower() == 'true'
    
    # Text Customization
    URL_REPLACEMENT_TEXT: str = os.getenv('URL_REPLACEMENT_TEXT', '[LINK REMOVED]')
    WELCOME_MESSAGE: str = os.getenv('WELCOME_MESSAGE', 'Welcome! I remove URLs from your videos and text.')
    ERROR_MESSAGE: str = os.getenv('ERROR_MESSAGE', 'Sorry, an error occurred. Please try again.')
    
    # Cleanup Settings
    TEMP_FILE_TTL: int = int(os.getenv('TEMP_FILE_TTL', '3600'))
    LOG_RETENTION_DAYS: int = int(os.getenv('LOG_RETENTION_DAYS', '30'))
    MAX_USER_REQUESTS_PER_DAY: int = int(os.getenv('MAX_USER_REQUESTS_PER_DAY', '100'))
    
    # Rate Limiting
    RATE_LIMIT_PER_USER: int = 10  # requests per minute
    RATE_LIMIT_PER_IP: int = 30    # requests per minute
    
    # File paths
    LOG_DIR: str = 'logs'
    TEMP_DIR: str = 'temp'
    DOWNLOAD_DIR: str = 'temp/downloads'
    
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required")
        
        if not cls.MONGO_URI:
            errors.append("MONGO_URI is required")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    @classmethod
    def print_summary(cls):
        """Print configuration summary"""
        print("=" * 50)
        print("🔧 Configuration Summary")
        print("=" * 50)
        print(f"📱 Bot Name: {cls.BOT_NAME}")
        print(f"👤 Admin IDs: {len(cls.ADMIN_IDS)}")
        print(f"💾 Database: {cls.MONGO_URI[:50]}...")
        print(f"📁 Max File Size: {cls.MAX_FILE_SIZE / (1024*1024):.0f} MB")
        print(f"📝 Supported Formats: {', '.join(cls.SUPPORTED_FORMATS)}")
        print(f"⚡ Features: Duplicate Check={cls.ENABLE_DUPLICATE_CHECK}")
        print("=" * 50)
