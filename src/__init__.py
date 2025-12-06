"""
Telegram URL Removal Bot - Source Package
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__description__ = "Bot to remove URLs from video content and text messages"

# Export main classes
from .bot_instance import TelegramBot
from .config import Config
from .database import DatabaseManager
from .url_processor import URLProcessor
from .file_manager import FileManager

__all__ = [
    'TelegramBot',
    'Config',
    'DatabaseManager',
    'URLProcessor',
    'FileManager'
]
