import os
import asyncio
import logging
from datetime import datetime, timedelta
import subprocess
import signal
import time

from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pymongo import MongoClient
import cv2
import numpy as np

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "1234567"))
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# Admin user ID
ADMIN_ID = 6861892595

# Global variables
running = True
mongo_client = None
db = None
users_collection = None
jobs_collection = None
settings_collection = None

# Initialize MongoDB
try:
    if MONGO_URI:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client["hitu"]
        users_collection = db["users"]
        jobs_collection = db["jobs"]
        settings_collection = db["settings"]
        logger.info("✅ MongoDB connected successfully")
    else:
        logger.warning("❌ MONGO_URI not set, running without database")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")

# Create bot
app = Client(
    "watermark_remover_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN
)

# Default settings
DEFAULT_SETTINGS = {
    "method": "delogo",
    "params": "x=iw-160:y=ih-60:w=150:h=50"
}

# Ensure temp directory exists
TEMP_DIR = "/tmp/wm_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

def get_settings():
    if not settings_collection:
        return DEFAULT_SETTINGS
    
    try:
        settings = settings_collection.find_one({"_id": "current"})
        if not settings:
            settings_collection.insert_one({"_id": "current", **DEFAULT_SETTINGS})
            return DEFAULT_SETTINGS
        return settings
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return DEFAULT_SETTINGS

def update_settings(method: str, params: str):
    if settings_collection:
        try:
            settings_collection.update_one(
                {"_id": "current"},
                {"$set": {"method": method, "params": params}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating settings: {e}")

def create_progress_message(job_id: str, percentage: int, status: str):
    return f"🔄 **Processing Status**\n\n**Job ID:** `{job_id}`\n**Progress:** {percentage}%\n**Status:** {status}"

def run_ffmpeg_command(cmd):
    """Run FFmpeg command and return success status"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return True
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg command timed out")
        return False
    except Exception as e:
        logger.error(f"FFmpeg execution error: {e}")
        return False

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
        cmd = f'ffmpeg -i "{input_path}" -vf "delogo=x={x}:y={y}:w={w}:h={h}" -c:a copy "{output_path}" -y'
        
        # Update initial progress
        if jobs_collection:
            try:
                jobs_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {"progress": 20, "status": "processing"}}
                )
            except Exception as e:
                logger.error(f"Database update error: {e}")
        
        await message.edit_text(create_progress_message(job_id, 20, "Removing watermark..."))
        
        # Run FFmpeg command
        success = run_ffmpeg_command(cmd)
        
        if success:
            if jobs_collection:
                try:
                    jobs_collection.update_one(
                        {"job_id": job_id},
                        {"$set": {"progress": 90, "status": "finalizing"}}
                    )
                except Exception as e:
                    logger.error(f"Database update error: {e}")
            
            await message.edit_text(create_progress_message(job_id, 90, "Finalizing..."))
            
        return success
        
    except Exception as e:
        logger.error(f"Delogo processing error: {e}")
        return False

async def process_video_with_inpaint(input_path: str, output_path: str, params: str, message: Message, job_id: str):
    """Process video using OpenCV inpainting"""
    try:
        cap = cv2.VideoCapture(input_path)
        
        if not cap.isOpened():
            raise Exception("Could not open video file")
            
        # Get video properties
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0:
            cap.release()
            raise Exception("Could not read video frames")
        
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
        last_update = 0
        
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
            
            # Update progress every 10%
            current_progress = int((frame_count / total_frames) * 100)
            if current_progress >= last_update + 10 and current_progress <= 90:
                last_update = current_progress
                
                if jobs_collection:
                    try:
                        jobs_collection.update_one(
                            {"job_id": job_id},
                            {"$set": {"progress": current_progress, "status": "processing"}}
                        )
                    except Exception as e:
                        logger.error(f"Database update error: {e}")
                
                progress_msg = create_progress_message(job_id, current_progress, "Inpainting...")
                await message.edit_text(progress_msg)
        
        cap.release()
        out.release()
        
        # Final progress update
        if jobs_collection:
            try:
                jobs_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {"progress": 90, "status": "finalizing"}}
                )
            except Exception as e:
                logger.error(f"Database update error: {e}")
        
        await message.edit_text(create_progress_message(job_id, 90, "Finalizing..."))
        
        return True
        
    except Exception as e:
        logger.error(f"Inpaint processing error: {e}")
        return False

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Save user to database if available
    if users_collection:
        try:
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
        except Exception as e:
            logger.error(f"Error saving user: {e}")
    
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
    
    if not jobs_collection or not users_collection:
        status_text = """
🤖 **Bot Status**

**Database:** ❌ Not connected
**Status:** ✅ Bot is running
**Server:** Koyeb
**Uptime:** Since last restart
"""
    else:
        try:
            # Get stats from database
            total_users = users_collection.count_documents({})
            total_jobs = jobs_collection.count_documents({})
            completed_jobs = jobs_collection.count_documents({"status": "completed"})
            processing_jobs = jobs_collection.count_documents({"status": "processing"})
            queued_jobs = jobs_collection.count_documents({"status": "queued"})
            
            status_text = f"""
🤖 **Bot Status**

**Total Users:** {total_users}
**Total Jobs:** {total_jobs}
**Completed Jobs:** {completed_jobs}
**Processing Jobs:** {processing_jobs}
**Queued Jobs:** {queued_jobs}

**Server:** Koyeb
**Database:** ✅ Connected
**Status:** ✅ Running
    """
        except Exception as e:
            status_text = f"""
🤖 **Bot Status**

**Database:** ⚠️ Connection issue
**Error:** {str(e)}
**Status:** ✅ Bot is running
"""
    
    await message.reply_text(status_text)

@app.on_message(filters.command("jobs") & filters.private)
async def jobs_command(client: Client, message: Message):
    """Show recent jobs (admin only)"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("🚫 This command is for admin only.")
        return
    
    if not jobs_collection:
        await message.reply_text("❌ Database not connected")
        return
    
    try:
        recent_jobs = jobs_collection.find().sort("created_at", -1).limit(10)
        
        jobs_text = "📊 **Recent Jobs**\n\n"
        job_count = 0
        
        for job in recent_jobs:
            jobs_text += f"**Job ID:** `{job['job_id']}`\n"
            jobs_text += f"**User:** {job.get('user_id', 'N/A')}\n"
            jobs_text += f"**Status:** {job.get('status', 'unknown')}\n"
            jobs_text += f"**Progress:** {job.get('progress', 0)}%\n"
            jobs_text += "─" * 20 + "\n"
            job_count += 1
        
        if job_count == 0:
            jobs_text = "No jobs found."
        
        await message.reply_text(jobs_text)
    except Exception as e:
        await message.reply_text(f"❌ Error fetching jobs: {str(e)}")

@app.on_message(filters.command("set_params") & filters.private)
async def set_params_command(client: Client, message: Message):
    """Set watermark removal parameters (admin only)"""
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("🚫 This command is for admin only.")
        return
    
    try:
        args = message.text.split()[1:]
        if len(args) < 2:
            await message.reply_text("""Usage: /set_params <method> <parameters>

Methods: delogo, inpaint

Examples:
/set_params delogo x=iw-160:y=ih-60:w=150:h=50
/set_params inpaint x=20:y=20:w=200:h=60""")
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
    
    # Create job record if database available
    job_id = f"job_{user_id}_{int(time.time())}"
    if jobs_collection:
        try:
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
        except Exception as e:
            logger.error(f"Error creating job record: {e}")
    
    # Send initial message
    progress_msg = await message.reply_text(create_progress_message(job_id, 0, "Downloading..."))
    
    download_path = None
    output_path = None
    
    try:
        # Download video
        download_path = os.path.join(TEMP_DIR, f"input_{job_id}.mp4")
        
        # Update progress
        if jobs_collection:
            try:
                jobs_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {"progress": 10, "status": "downloading"}}
                )
            except Exception as e:
                logger.error(f"Database update error: {e}")
        
        await progress_msg.edit_text(create_progress_message(job_id, 10, "Downloading..."))
        
        await message.download(download_path)
        
        if not os.path.exists(download_path):
            raise Exception("Failed to download video")
        
        # Get settings
        settings = get_settings()
        method = settings["method"]
        params = settings["params"]
        
        # Update job info
        if jobs_collection:
            try:
                jobs_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {
                        "file_name": os.path.basename(download_path),
                        "method": method,
                        "params": params,
                        "status": "processing",
                        "progress": 20
                    }}
                )
            except Exception as e:
                logger.error(f"Database update error: {e}")
        
        await progress_msg.edit_text(create_progress_message(job_id, 20, "Starting processing..."))
        
        # Process video based on method
        output_path = os.path.join(TEMP_DIR, f"output_{job_id}.mp4")
        
        success = False
        if method == "delogo":
            success = await process_video_with_delogo(download_path, output_path, params, progress_msg, job_id)
        else:  # inpaint
            success = await process_video_with_inpaint(download_path, output_path, params, progress_msg, job_id)
        
        if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # Update progress to completed
            if jobs_collection:
                try:
                    jobs_collection.update_one(
                        {"job_id": job_id},
                        {"$set": {"status": "completed", "progress": 100}}
                    )
                except Exception as e:
                    logger.error(f"Database update error: {e}")
            
            await progress_msg.edit_text(create_progress_message(job_id, 100, "Uploading..."))
            
            # Send processed video
            await message.reply_video(
                video=output_path,
                caption="✅ **Watermark removed successfully!**\n\nYour video is ready!",
                reply_to_message_id=message.id
            )
            
            await progress_msg.delete()
            
        else:
            raise Exception("Video processing failed - no output file generated")
            
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        
        # Update job as failed
        if jobs_collection:
            try:
                jobs_collection.update_one(
                    {"job_id": job_id},
                    {"$set": {"status": "failed", "error": str(e)}}
                )
            except Exception as e:
                logger.error(f"Database update error: {e}")
        
        await progress_msg.edit_text(f"❌ **Processing Failed**\n\nError: {str(e)}\n\nPlease try again with a different video.")
    
    finally:
        # Cleanup temporary files
        try:
            if download_path and os.path.exists(download_path):
                os.remove(download_path)
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

async def cleanup_old_files():
    """Cleanup old temporary files periodically"""
    while running:
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

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False

async def main():
    """Main function to start the bot"""
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("🤖 Starting Watermark Remover Bot...")
    
    # Start cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_files())
    
    try:
        # Start the bot
        await app.start()
        logger.info("✅ Bot started successfully!")
        
        # Get bot info
        me = await app.get_me()
        logger.info(f"🤖 Bot username: @{me.username}")
        logger.info(f"🆔 Bot ID: {me.id}")
        logger.info("🚀 Bot is now running and ready to process videos!")
        
        # Keep the bot running
        while running:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        
