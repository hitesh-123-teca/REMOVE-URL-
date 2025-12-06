"""
File handling and duplicate detection
"""

import os
import hashlib
import aiofiles
import logging
import magic
import shutil
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class FileManager:
    """Handles file operations and duplicate detection"""
    
    def __init__(self, temp_dir: str = "temp/downloads"):
        self.temp_dir = temp_dir
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs("temp/processed", exist_ok=True)
        os.makedirs("temp/trash", exist_ok=True)
    
    async def download_file(self, file_obj, file_name: str) -> Optional[str]:
        """
        Download file from Telegram to local storage
        Returns path to downloaded file
        """
        try:
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._sanitize_filename(file_name)
            unique_name = f"{timestamp}_{safe_name}"
            file_path = os.path.join(self.temp_dir, unique_name)
            
            # Download file
            await file_obj.download_to_drive(file_path)
            
            logger.info(f"📥 Downloaded file: {file_name} -> {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"❌ Error downloading file: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to remove unsafe characters"""
        # Keep only safe characters
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        safe_name = ''.join(c for c in filename if c in safe_chars)
        
        # If name becomes empty, use default
        if not safe_name:
            safe_name = f"file_{hashlib.md5(filename.encode()).hexdigest()[:8]}"
        
        return safe_name
    
    async def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """
        Calculate MD5 hash of file for duplicate detection
        Uses efficient chunked reading for large files
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            hash_md5 = hashlib.md5()
            chunk_size = 8192  # 8KB chunks
            
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    hash_md5.update(chunk)
            
            file_hash = hash_md5.hexdigest()
            logger.debug(f"🔢 Calculated hash for {file_path}: {file_hash[:8]}...")
            return file_hash
            
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
            return None
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get information about a file"""
        if not os.path.exists(file_path):
            return {}
        
        try:
            stat = os.stat(file_path)
            
            # Get file type using magic
            mime = magic.Magic(mime=True)
            file_type = mime.from_file(file_path)
            
            # Get file extension
            _, ext = os.path.splitext(file_path)
            
            return {
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime),
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "type": file_type,
                "extension": ext.lower(),
                "path": file_path,
                "filename": os.path.basename(file_path)
            }
            
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return {}
    
    def is_file_supported(self, file_path: str, supported_formats: list) -> bool:
        """Check if file format is supported"""
        if not os.path.exists(file_path):
            return False
        
        try:
            # Get file extension
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            # Check extension against supported formats
            if ext in supported_formats:
                return True
            
            # Also check MIME type for video files
            mime = magic.Magic(mime=True)
            file_type = mime.from_file(file_path)
            
            # Common video MIME types
            video_mimes = [
                'video/mp4', 'video/avi', 'video/quicktime',
                'video/x-msvideo', 'video/x-matroska',
                'video/webm', 'video/x-flv', 'video/x-ms-wmv'
            ]
            
            if file_type.startswith('video/') and file_type in video_mimes:
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking file format: {e}")
            return False
    
    def check_file_size(self, file_path: str, max_size: int) -> Tuple[bool, str]:
        """Check if file size is within limits"""
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        try:
            size = os.path.getsize(file_path)
            
            if size > max_size:
                size_mb = size / (1024 * 1024)
                max_mb = max_size / (1024 * 1024)
                return False, f"File too large: {size_mb:.1f}MB > {max_mb:.0f}MB"
            
            return True, f"Size OK: {size / (1024*1024):.1f}MB"
            
        except Exception as e:
            return False, f"Error checking size: {e}"
    
    async def move_to_processed(self, file_path: str) -> Optional[str]:
        """Move file to processed directory"""
        if not os.path.exists(file_path):
            return None
        
        try:
            filename = os.path.basename(file_path)
            processed_path = os.path.join("temp/processed", filename)
            
            shutil.move(file_path, processed_path)
            logger.debug(f"Moved to processed: {processed_path}")
            return processed_path
            
        except Exception as e:
            logger.error(f"Error moving to processed: {e}")
            return file_path  # Return original path if move fails
    
    async def cleanup_temp_files(self, older_than_hours: int = 24):
        """Cleanup temporary files older than specified hours"""
        try:
            cutoff_time = datetime.now().timestamp() - (older_than_hours * 3600)
            cleaned_count = 0
            
            # Clean temp directories
            temp_dirs = ["temp/downloads", "temp/processed", "temp/trash"]
            
            for temp_dir in temp_dirs:
                if not os.path.exists(temp_dir):
                    continue
                
                for filename in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, filename)
                    
                    # Skip directories
                    if not os.path.isfile(file_path):
                        continue
                    
                    # Check file age
                    file_time = os.path.getmtime(file_path)
                    if file_time < cutoff_time:
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except Exception as e:
                            logger.error(f"Error removing {file_path}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"🧹 Cleaned {cleaned_count} temporary files")
                
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")
    
    def find_duplicates_in_directory(self, directory: str) -> Dict[str, list]:
        """Find duplicate files in a directory"""
        if not os.path.exists(directory):
            return {}
        
        duplicates = {}
        hashes = {}
        
        try:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                
                if not os.path.isfile(file_path):
                    continue
                
                # Calculate hash
                file_hash = asyncio.run(self.calculate_file_hash(file_path))
                if not file_hash:
                    continue
                
                # Add to hashes dict
                if file_hash in hashes:
                    hashes[file_hash].append(file_path)
                else:
                    hashes[file_hash] = [file_path]
            
            # Find duplicates (files with same hash)
            for file_hash, file_paths in hashes.items():
                if len(file_paths) > 1:
                    duplicates[file_hash] = file_paths
            
            return duplicates
            
        except Exception as e:
            logger.error(f"Error finding duplicates: {e}")
            return {}
    
    async def delete_duplicates(self, duplicates: Dict[str, list], keep_first: bool = True):
        """Delete duplicate files, keeping only one copy"""
        deleted_count = 0
        
        try:
            for file_hash, file_paths in duplicates.items():
                if len(file_paths) <= 1:
                    continue
                
                # Determine which files to keep
                if keep_first:
                    keep_file = file_paths[0]
                    delete_files = file_paths[1:]
                else:
                    # Keep the newest file
                    file_times = [(os.path.getmtime(p), p) for p in file_paths]
                    keep_file = max(file_times)[1]
                    delete_files = [p for p in file_paths if p != keep_file]
                
                # Delete duplicate files
                for file_path in delete_files:
                    try:
                        # Move to trash instead of permanent delete
                        trash_path = os.path.join("temp/trash", os.path.basename(file_path))
                        shutil.move(file_path, trash_path)
                        deleted_count += 1
                        logger.debug(f"Moved duplicate to trash: {file_path}")
                    except Exception as e:
                        logger.error(f"Error moving duplicate: {e}")
            
            if deleted_count > 0:
                logger.info(f"🗑️ Deleted {deleted_count} duplicate files")
                
        except Exception as e:
            logger.error(f"Error deleting duplicates: {e}")
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage information"""
        info = {
            "temp_size": 0,
            "processed_size": 0,
            "trash_size": 0,
            "temp_files": 0,
            "processed_files": 0,
            "trash_files": 0
        }
        
        try:
            directories = {
                "temp_size": "temp/downloads",
                "processed_size": "temp/processed",
                "trash_size": "temp/trash"
            }
            
            for key, directory in directories.items():
                if os.path.exists(directory):
                    total_size = 0
                    file_count = 0
                    
                    for dirpath, dirnames, filenames in os.walk(directory):
                        for filename in filenames:
                            file_path = os.path.join(dirpath, filename)
                            if os.path.isfile(file_path):
                                total_size += os.path.getsize(file_path)
                                file_count += 1
                    
                    info[key] = total_size
                    info[key.replace("_size", "_files")] = file_count
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting storage info: {e}")
            return info
