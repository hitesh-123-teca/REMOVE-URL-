"""
Utility functions for the bot
"""

import os
import hashlib
from datetime import datetime
from typing import List

def format_size(size_bytes: int) -> str:
    """Format file size to human readable format"""
    if size_bytes == 0:
        return "0B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
        
    return f"{size_bytes:.2f} {units[unit_index]}"

def format_time(seconds: int) -> str:
    """Format seconds to MM:SS"""
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def create_progress_message(text: str, progress: int) -> str:
    """Create a progress bar message"""
    bar_length = 20
    filled_length = int(bar_length * progress / 100)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    return f"{text}\n\n`[{bar}] {progress}%`"

def cleanup_temp_files():
    """Cleanup temporary files directory"""
    temp_dir = "temp"
    if os.path.exists(temp_dir):
        try:
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
        except Exception as e:
            print(f"Error cleaning temp directory: {e}")

def ensure_directories():
    """Ensure required directories exist"""
    directories = ["temp", "logs", "thumbnails", "processed"]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def get_timestamp() -> str:
    """Get current timestamp string"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def safe_filename(filename: str) -> str:
    """Make filename safe for all OS"""
    import re
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    return filename

def calculate_md5(file_path: str) -> str:
    """Calculate MD5 hash of file"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_file_info(file_path: str) -> dict:
    """Get file information"""
    import os
    stat = os.stat(file_path)
    return {
        "size": stat.st_size,
        "created": datetime.fromtimestamp(stat.st_ctime),
        "modified": datetime.fromtimestamp(stat.st_mtime),
        "accessed": datetime.fromtimestamp(stat.st_atime)
    }

def split_list(lst: List, n: int) -> List[List]:
    """Split list into chunks of size n"""
    return [lst[i:i + n] for i in range(0, len(lst), n)]
