import os
import asyncio
import logging
from datetime import datetime, timedelta
import shutil
from typing import Dict, List

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import ffmpeg
import cv2
import numpy as np

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", ""))
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI", "")

# Admin user ID
ADMIN_ID = 6861892595

# Initialize MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["hitu"]
users_collection = db["users"]
jobs_collection = db["jobs"]
settings_collection = db["settings"]

# Create bot
app = Client("watermark_remover_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Default settings
DEFAULT_SETTINGS = {
    "method": "delogo",
    "params": "x=iw-160:y=ih-60:w=150:h=50"
}

# Ensure temp directory exists
TEMP_DIR = "/tmp/wm_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

def get_settings():
    settings = settings_collection.find_one({"_id": "current"})
    if not settings:
        settings_collection.insert_one({"_id": "current", **DEFAULT_SETTINGS})
        return DEFAULT_SETTINGS
    return settings

def update_settings(method: str, params: str):
    settings_collection.update_one(
        {"_id": "current"},
        {"$set": {"method": method, "params": params}},
        upsert=True
    )

def create_progress_message(job_id: str, percentage: int, status: str):
    return f"🔄 **Processing Status**\n\n**Job ID:** `{job_id}`\n**Progress:** {percentage}%\n**Status:** {status}"

async def process_video_with_delogo(input_path: str, output_path: str, params: str, message: Message, job_id: str):
    """Process video using FFmpeg delogo filter"""
    try:
        # Parse parameters
        params_dict = {}
        for param in params.split(':'):
            if '=' in param:
                key, value = param.split('=', 1)
                params_dict[key] = value
        
        # Extract coordinates and dimensions
        x = params_dict.get('x', 'iw-160')
        y = params_dict.get('y', 'ih-60') 
        w = params_dict.get('w', '150')
        h = params_dict.get('h', '50')
        
        # Build FFmpeg command
        stream = ffmpeg.input(input_path)
        
        # Apply delogo filter with progress
        stream = ffmpeg.filter(stream, 'delogo', x=x, y=y, w=w, h=h)
        
        # Output with progress
        stream = ffmpeg.output(stream, output_path, 
                              vcodec='libx264',
                              acodec='copy',
                              **{'max_muxing_queue_size': 9999})
        
        # Run with progress callback
        process = ffmpeg.run_async(stream, pipe_stdout=True, pipe_stderr=True)
        
        # Monitor progress
        duration = None
        while True:
            line = process.stderr.readline().decode('utf-8')
            if not line:
                break
                
            # Extract duration
            if 'Duration:' in line:
                try:
                    time_str = line.split('Duration: ')[1].split(',')[0]
                    h, m, s = time_str.split(':')
                    duration = int(h) * 3600 + int(m) * 60 + float(s)
                except:
                    pass
            
            # Extract current time and calculate progress
            if 'time=' in line and duration:
                try:
                    time_str = line.split('time=')[1].split(' ')[0]
                    h, m, s = time_str.split(':')
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    percentage = min(int((current_time / duration) * 100), 100)
                    
                    # Update progress in database and message
                    jobs_collection.update_one(
                        {"job_id": job_id},
                        {"$set": {"progress": percentage, "status": "processing"}}
                    )
                    
                    # Update message every 10% progress
                    if percentage % 10 == 0:
                        progress_msg = create_progress_message(job_id, percentage, "Processing...")
                        await message.edit_text(progress_msg)
                        
                except Exception as e:
                    logger.error(f"Progress tracking error: {e}")
        
        process.wait()
        return True
        
    except Exception as e:
        logger.error(f"Delogo processing error: {e}")
        return False

async def process_video_with_inpaint(input_path: str, output_path: str, params: str, message: Message, job_id: str):
    """Process video using OpenCV inpainting"""
    try:
        cap = cv2.VideoCapture(input_path)
        
        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Parse parameters
        params_dict = {}
        for param in params.split(':'):
            if '=' in param:
                key, value = param.split('=', 1)
                params_dict[key] = value
        
        # Extract coordinates and dimensions for watermark area
        x = int(params_dict.get('x', '20'))
        y = int(params_dict.get('y', '20')) 
        w = int(params_dict.get('w', '200'))
        h = int(params_dict.get('h', '60'))
        
        # Setup video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Create mask for watermark area
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.rectangle(mask, (x, y), (x+w, y+h), 255, -1)
            
            # Apply inpainting
            inpainted_frame = cv2.inpaint(frame, mask, 3, cv2.INPAINT_TELEA)
            
            out.write(inpainted_frame)
            frame_count += 1
            
            # Update progress
            if frame_count % 30 == 0:  # Update every 30 frames
                percentage = min(int((frame_count / total_frames) * 100), 100)
                
                jobs_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {"progress": percentage, "status": "processing"}}
                )
                
                if percentage % 10 == 0:
                    progress_msg = create_progress_message(job_id, percentage, "Inpainting...")
                    await message.edit_text(progress_msg)
        
        cap.release()
        out.release()
        return True
        
    except Exception as e:
        logger.error(f"Inpaint processing error: {e}")
        return False

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Save user to database
    users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name,
                "joined_at": datetime.now()
            }
        },
        upsert=True
    )
    
    welcome_text = """
🌊 **Welcome to Video Watermark Remover Bot!**

Send me any video with watermark/URL, and I'll remove it for you!

**Features:**
✅ Remove watermarks & logos
✅ Remove URL overlays  
✅ Fast processing
✅ Progress tracking

Simply send a video to get started!
    """
    
    await message.reply_text(welcome_text)

@app.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    """Show bot status (admin only)"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("🚫 This command is for admin only.")
        return
    
    # Calculate uptime (you might want to track this properly)
    uptime = "1 day 2 hours"  # Example
    
    # Get stats from database
    total_users = users_collection.count_documents({})
    total_jobs = jobs_collection.count_documents({})
    completed_jobs = jobs_collection.count_documents({"status": "completed"})
    processing_jobs = jobs_collection.count_documents({"status": "processing"})
    
    status_text = f"""
🤖 **Bot Status**

**Uptime:** {uptime}
**Total Users:** {total_users}
**Total Jobs:** {total_jobs}
**Completed Jobs:** {completed_jobs}
**Processing Jobs:** {processing_jobs}

**Server:** Koyeb
**Database:** MongoDB
    """
    
    await message.reply_text(status_text)

@app.on_message(filters.command("jobs") & filters.private)
async def jobs_command(client: Client, message: Message):
    """Show recent jobs (admin only)"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("🚫 This command is for admin only.")
        return
    
    recent_jobs = jobs_collection.find().sort("created_at", -1).limit(10)
    
    jobs_text = "📊 **Recent Jobs**\n\n"
    for job in recent_jobs:
        jobs_text += f"**Job ID:** `{job['job_id']}`\n"
        jobs_text += f"**User:** {job.get('user_id', 'N/A')}\n"
        jobs_text += f"**Status:** {job.get('status', 'unknown')}\n"
        jobs_text += f"**Progress:** {job.get('progress', 0)}%\n"
        jobs_text += "─" * 20 + "\n"
    
    await message.reply_text(jobs_text)

@app.on_message(filters.command("set_params") & filters.private)
async def set_params_command(client: Client, message: Message):
    """Set watermark removal parameters (admin only)"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("🚫 This command is for admin only.")
        return
    
    try:
        args = message.text.split()[1:]
        if len(args) < 2:
            await message.reply_text("Usage: /set_params <method> <parameters>\n\nMethods: delogo, inpaint\nExample: /set_params delogo x=iw-160:y=ih-60:w=150:h=50")
            return
        
        method = args[0]
        params = ' '.join(args[1:])
        
        if method not in ['delogo', 'inpaint']:
            await message.reply_text("❌ Invalid method. Use 'delogo' or 'inpaint'")
            return
        
        update_settings(method, params)
        
        await message.reply_text(f"✅ Settings updated!\n**Method:** {method}\n**Params:** {params}")
        
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.video | filters.document)
async def handle_video(client: Client, message: Message):
    """Handle incoming videos and documents"""
    user_id = message.from_user.id
    
    # Create job record
    job_id = f"job_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now(),
        "file_name": "",
        "method": "",
        "params": ""
    }
    jobs_collection.insert_one(job_data)
    
    # Send initial message
    progress_msg = await message.reply_text(create_progress_message(job_id, 0, "Downloading..."))
    
    try:
        # Download video
        download_path = os.path.join(TEMP_DIR, f"input_{job_id}.mp4")
        await message.download(download_path)
        
        # Get settings
        settings = get_settings()
        method = settings["method"]
        params = settings["params"]
        
        # Update job info
        jobs_collection.update_one(
            {"job_id": job_id},
            {"$set": {
                "file_name": os.path.basename(download_path),
                "method": method,
                "params": params,
                "status": "processing",
                "progress": 10
            }}
        )
        
        await progress_msg.edit_text(create_progress_message(job_id, 10, "Processing video..."))
        
        # Process video based on method
        output_path = os.path.join(TEMP_DIR, f"output_{job_id}.mp4")
        
        if method == "delogo":
            success = await process_video_with_delogo(download_path, output_path, params, progress_msg, job_id)
        else:  # inpaint
            success = await process_video_with_inpaint(download_path, output_path, params, progress_msg, job_id)
        
        if success:
            # Update progress to completed
            jobs_collection.update_one(
                {"job_id": job_id},
                {"$set": {"status": "completed", "progress": 100}}
            )
            
            await progress_msg.edit_text(create_progress_message(job_id, 100, "Uploading..."))
            
            # Send processed video
            await message.reply_video(
                video=output_path,
                caption="✅ **Watermark removed successfully!**\n\nYour video is ready!",
                reply_to_message_id=message.id
            )
            
            await progress_msg.delete()
            
        else:
            raise Exception("Video processing failed")
            
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        
        # Update job as failed
        jobs_collection.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )
        
        await progress_msg.edit_text(f"❌ **Processing Failed**\n\nError: {str(e)}\n\nPlease try again with a different video.")
    
    finally:
        # Cleanup temporary files
        try:
            if 'download_path' in locals() and os.path.exists(download_path):
                os.remove(download_path)
            if 'output_path' in locals() and os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

async def cleanup_old_files():
    """Cleanup old temporary files periodically"""
    while True:
        try:
            now = datetime.now()
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.isfile(filepath):
                    file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                    if now - file_time > timedelta(hours=1):
                        os.remove(filepath)
                        logger.info(f"Cleaned up: {filename}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        
        await asyncio.sleep(3600)  # Run every hour

@app.on_startup()
async def startup():
    """Run on bot startup"""
    logger.info("🤖 Watermark Remover Bot Started!")
    asyncio.create_task(cleanup_old_files())

@app.on_shutdown()
async def shutdown():
    """Run on bot shutdown"""
    logger.info("🤖 Watermark Remover Bot Stopped!")

if __name__ == "__main__":
    logger.info("Starting Watermark Remover Bot...")
    app.run()
