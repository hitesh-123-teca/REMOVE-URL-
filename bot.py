# bot.py - Advanced Watermark remover Telegram bot (final stable)
# Admin commands + Progress indicator + MongoDB job tracking

import os
import re
import time
import asyncio
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# ------------------ MANUAL TIME SYNC (final Pyrogram fix) ------------------
import datetime as dt
utc_now = dt.datetime.utcnow()
local_now = dt.datetime.now()
offset = (utc_now - local_now).total_seconds()
if abs(offset) > 1:
    print(f"[INFO] Local time offset detected: {offset:.2f}s")
    print("[INFO] Adjusting Pyrogram timestamps internally (UTC sync active).")
    time.time = lambda: dt.datetime.utcnow().timestamp()
# ---------------------------------------------------------------------------

from pyrogram import Client, filters
from pyrogram.types import Message
import motor.motor_asyncio

# ------------------ BOT CREDENTIALS ------------------
BOT_TOKEN = "7852091851:AAHQr_w4hi-RuJ5sJ8JvQCo_fOZtf6EWhvk"
API_ID = 123456
API_HASH = "db274cb8e9167e731d9c8305197badeb"
MONGO_URI = "mongodb+srv://moviescorn:moviescorn@hitu.4jr5k.mongodb.net/?retryWrites=true&w=majority&appName=Hitu"
ADMIN_ID = 6861892595
# -----------------------------------------------------

# Defaults
WATERMARK_METHOD = os.getenv("WATERMARK_METHOD", "delogo").lower()
WATERMARK_PARAMS = os.getenv("WATERMARK_PARAMS", "x=iw-160:y=ih-60:w=150:h=50")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE") or 500_000_000)

# Work directories
WORKDIR = Path("/tmp/wm_bot")
DOWNLOAD_DIR = WORKDIR / "download"
OUTPUT_DIR = WORKDIR / "out"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wm-bot")

# Pyrogram Client
APP = Client("wmremover", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Mongo Client
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client["hitu"]
COL_USERS = db["users"]
COL_JOBS = db["jobs"]
COL_SETTINGS = db["settings"]

START_TIME = datetime.utcnow()

# ------------------ Helper Functions ------------------

def get_video_duration_seconds(path: str) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", path
        ])
        return float(out.decode().strip())
    except:
        return 0.0

def parse_ffmpeg_time_from_line(line: str) -> float:
    m = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
    if not m:
        return 0.0
    h, m_, s = m.group(1).split(":")
    return int(h) * 3600 + int(m_) * 60 + float(s)

def parse_params(params: str):
    d = {}
    for part in params.split(":"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k] = v
    return d

# ------------------ Mongo Helpers ------------------

async def ensure_user(user):
    await COL_USERS.update_one(
        {"user_id": user["user_id"]},
        {"$setOnInsert": user},
        upsert=True
    )

async def create_job(user_id, msg_id, infile, method, params):
    job = {
        "user_id": user_id,
        "tg_message_id": msg_id,
        "infile": infile,
        "outfile": None,
        "method": method,
        "params": params,
        "status": "queued",
        "progress": 0,
        "created_at": datetime.utcnow()
    }
    res = await COL_JOBS.insert_one(job)
    job["_id"] = res.inserted_id
    return job

async def update_job(job_id, patch):
    patch["updated_at"] = datetime.utcnow()
    await COL_JOBS.update_one({"_id": job_id}, {"$set": patch})

# ------------------ Video Processing ------------------

def ffmpeg_delogo(infile, outfile, params, progress_cb):
    duration = get_video_duration_seconds(infile)
    cmd = [
        "ffmpeg", "-y", "-i", infile,
        "-vf", f"delogo={params}",
        "-c:a", "copy", outfile
    ]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
    while True:
        line = proc.stderr.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        cur = parse_ffmpeg_time_from_line(line)
        if duration > 0:
            percent = int((cur / duration) * 100)
            progress_cb(min(percent, 100))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg failed")

def process_video_sync(job, progress_cb):
    infile = job["infile"]
    outfile = str(OUTPUT_DIR / (Path(infile).stem + "_processed.mp4"))
    ffmpeg_delogo(infile, outfile, job["params"], progress_cb)
    return outfile

# ------------------ Decorators ------------------

def admin_only(func):
    async def wrapper(client, message: Message):
        if message.from_user.id != ADMIN_ID:
            await message.reply_text("Yeh command sirf admin ke liye hai.")
            return
        return await func(client, message)
    return wrapper

# ------------------ Commands ------------------

@APP.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user = message.from_user
    await ensure_user({
        "user_id": user.id,
        "first_name": user.first_name,
        "username": user.username,
        "created_at": datetime.utcnow()
    })
    await message.reply_text("Main watermark remover bot hun. Video bhejo — main process karke wapas bhej dungi.")

@APP.on_message(filters.command("status") & filters.private)
@admin_only
async def cmd_status(client, message):
    uptime = datetime.utcnow() - START_TIME
    total = await COL_JOBS.count_documents({})
    done = await COL_JOBS.count_documents({"status": "done"})
    proc = await COL_JOBS.count_documents({"status": "processing"})
    await message.reply_text(
        f"🕐 Uptime: {str(uptime).split('.')[0]}\n"
        f"📦 Total: {total}\n✅ Done: {done}\n⚙️ Processing: {proc}"
    )

@APP.on_message(filters.command("jobs") & filters.private)
@admin_only
async def cmd_jobs(client, message):
    jobs = await COL_JOBS.find().sort("created_at", -1).limit(5).to_list(5)
    text = "\n".join([f"{j['_id']} | {j['status']} | {j.get('progress',0)}%" for j in jobs]) or "No jobs"
    await message.reply_text(text)

@APP.on_message(filters.command("set_params") & filters.private)
@admin_only
async def cmd_set_params(client, message):
    global WATERMARK_METHOD, WATERMARK_PARAMS
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.reply_text("Usage: /set_params <method> <params>")
        return
    WATERMARK_METHOD = args[1]
    WATERMARK_PARAMS = args[2] if len(args) > 2 else WATERMARK_PARAMS
    await COL_SETTINGS.update_one(
        {"_id": "processing"},
        {"$set": {"method": WATERMARK_METHOD, "params": WATERMARK_PARAMS}},
        upsert=True
    )
    await message.reply_text(f"✅ Method: {WATERMARK_METHOD}\nParams: {WATERMARK_PARAMS}")

# ------------------ Video Handling ------------------

@APP.on_message(filters.video | filters.document)
async def handle_video(client, message):
    m = await message.reply_text("Video receive hui — processing start kar rahi hun...")

    user = message.from_user
    path = await message.download(file_name=str(DOWNLOAD_DIR))
    job = await create_job(user.id, message.id, path, WATERMARK_METHOD, WATERMARK_PARAMS)
    await update_job(job["_id"], {"status": "processing"})

    async def update_progress(p):
        await update_job(job["_id"], {"progress": p})
        try:
            await m.edit(f"Processing: {p}%")
        except:
            pass

    def cb(p):
        asyncio.get_event_loop().create_task(update_progress(p))

    try:
        outfile = await asyncio.get_event_loop().run_in_executor(None, process_video_sync, job, cb)
        await update_job(job["_id"], {"status": "done", "outfile": outfile, "progress": 100})
        await message.reply_video(outfile, caption="✅ Watermark हटाकर भेज रही hun.")
        await m.delete()
    except Exception as e:
        await update_job(job["_id"], {"status": "failed", "error": str(e)})
        await m.edit(f"❌ Error: {e}")

# ------------------ Startup ------------------

async def load_settings():
    s = await COL_SETTINGS.find_one({"_id": "processing"})
    if s:
        global WATERMARK_METHOD, WATERMARK_PARAMS
        WATERMARK_METHOD = s.get("method", WATERMARK_METHOD)
        WATERMARK_PARAMS = s.get("params", WATERMARK_PARAMS)
        logger.info("Loaded settings from DB: %s %s", WATERMARK_METHOD, WATERMARK_PARAMS)

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(load_settings())
    APP.run()
