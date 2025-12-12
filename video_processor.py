"""
Video processing utilities:
1. Thumbnail extraction
2. Watermark removal
3. URL removal from captions
4. File operations
"""

import re
import os
import tempfile
import subprocess
from typing import Optional, Tuple, List
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip

from config import Config

class VideoProcessor:
    """Video processing utilities"""
    
    def __init__(self):
        self.temp_dir = "temp"
        os.makedirs(self.temp_dir, exist_ok=True)
        
    # ========== CAPTION PROCESSING ==========
    
    @staticmethod
    def remove_urls(text: str) -> str:
        """Remove all URLs from text"""
        if not text:
            return ""
        
        # Remove various URL patterns
        patterns = [
            r'https?://\S+',                     # http/https URLs
            r'www\.\S+',                         # www URLs
            r't\.me/\S+',                        # Telegram links
            r'telegram\.me/\S+',                 # Telegram.me links
            r'@\w+',                             # Mentions
            r'#\w+',                             # Hashtags
            r'\[([^\]]+)\]\([^)]+\)',           # Markdown links
            r'<a[^>]*>(.*?)</a>',               # HTML links
            r'[\U00010000-\U0010ffff]',         # Remove emojis
        ]
        
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned)
            
        # Clean extra spaces and newlines
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()
    
    @staticmethod
    def clean_caption(caption: str, max_length: int = 1000) -> str:
        """Clean and format caption"""
        if not caption:
            return ""
            
        # Remove URLs
        caption = VideoProcessor.remove_urls(caption)
        
        # Truncate if too long
        if len(caption) > max_length:
            caption = caption[:max_length] + "..."
            
        return caption
    
    # ========== THUMBNAIL GENERATION ==========
    
    async def extract_thumbnail(self, video_path: str, time_sec: int = None) -> Optional[str]:
        """Extract thumbnail from video at specified time"""
        if time_sec is None:
            time_sec = Config.THUMBNAIL_TIME
            
        try:
            # Use moviepy to extract frame
            with VideoFileClip(video_path) as video:
                # Validate time
                duration = video.duration
                if time_sec > duration:
                    time_sec = min(5, duration - 1)
                
                # Get frame
                frame = video.get_frame(time_sec)
                
                # Convert to PIL Image
                img = Image.fromarray(frame)
                
                # Resize to Telegram specifications (max 320x320)
                img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                
                # Save thumbnail
                thumb_path = os.path.join(self.temp_dir, f"thumb_{os.path.basename(video_path)}.jpg")
                img.save(thumb_path, "JPEG", quality=90)
                
                return thumb_path
                
        except Exception as e:
            print(f"Thumbnail extraction error: {e}")
            return None
    
    async def extract_multiple_thumbnails(self, video_path: str, times: List[int] = None) -> List[str]:
        """Extract multiple thumbnails at different times"""
        if times is None:
            times = [2, 4, 6, 10, 15]
            
        thumbnails = []
        
        try:
            with VideoFileClip(video_path) as video:
                duration = video.duration
                
                for time_sec in times:
                    if time_sec < duration:
                        frame = video.get_frame(time_sec)
                        img = Image.fromarray(frame)
                        img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                        
                        thumb_path = os.path.join(
                            self.temp_dir, 
                            f"thumb_{os.path.basename(video_path)}_{time_sec}.jpg"
                        )
                        img.save(thumb_path, "JPEG", quality=90)
                        thumbnails.append(thumb_path)
                        
        except Exception as e:
            print(f"Multiple thumbnail extraction error: {e}")
            
        return thumbnails
    
    # ========== WATERMARK REMOVAL ==========
    
    async def remove_watermark(self, video_path: str) -> Optional[str]:
        """Remove watermark from video (basic implementation)"""
        if not Config.REMOVE_WATERMARK:
            return video_path
            
        try:
            # Create output path
            output_path = os.path.join(self.temp_dir, f"no_watermark_{os.path.basename(video_path)}")
            
            # Use FFmpeg for watermark removal (basic approach)
            # This is a placeholder - you need to customize based on watermark position
            command = [
                'ffmpeg',
                '-i', video_path,
                '-vf', 'delogo=x=10:y=10:w=100:h=30:show=0',  # Example: remove logo at (10,10) with size 100x30
                '-c:a', 'copy',
                output_path
            ]
            
            # Run FFmpeg
            subprocess.run(command, check=True, capture_output=True)
            
            return output_path if os.path.exists(output_path) else video_path
            
        except Exception as e:
            print(f"Watermark removal error: {e}")
            return video_path
    
    # ========== VIDEO INFO ==========
    
    async def get_video_info(self, video_path: str) -> Dict:
        """Get video information"""
        try:
            with VideoFileClip(video_path) as video:
                return {
                    "duration": video.duration,
                    "fps": video.fps,
                    "size": video.size,
                    "has_audio": video.audio is not None
                }
        except Exception as e:
            print(f"Video info error: {e}")
            return {}
    
    # ========== FILE OPERATIONS ==========
    
    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """Calculate MD5 hash of file"""
        import hashlib
        
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
                
        return hash_md5.hexdigest()
    
    @staticmethod
    def get_file_size_mb(file_path: str) -> float:
        """Get file size in MB"""
        return os.path.getsize(file_path) / (1024 * 1024)
    
    # ========== UTILITIES ==========
    
    async def compress_video(self, video_path: str, quality: int = 23) -> Optional[str]:
        """Compress video using FFmpeg"""
        try:
            output_path = os.path.join(self.temp_dir, f"compressed_{os.path.basename(video_path)}")
            
            command = [
                'ffmpeg',
                '-i', video_path,
                '-c:v', 'libx264',
                '-crf', str(quality),  # Lower value = better quality
                '-c:a', 'aac',
                '-b:a', '128k',
                output_path
            ]
            
            subprocess.run(command, check=True, capture_output=True)
            
            return output_path if os.path.exists(output_path) else None
            
        except Exception as e:
            print(f"Video compression error: {e}")
            return None
    
    async def convert_format(self, video_path: str, output_format: str = "mp4") -> Optional[str]:
        """Convert video to different format"""
        try:
            output_path = os.path.join(
                self.temp_dir, 
                f"{Path(video_path).stem}.{output_format}"
            )
            
            command = [
                'ffmpeg',
                '-i', video_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                output_path
            ]
            
            subprocess.run(command, check=True, capture_output=True)
            
            return output_path if os.path.exists(output_path) else None
            
        except Exception as e:
            print(f"Format conversion error: {e}")
            return None
