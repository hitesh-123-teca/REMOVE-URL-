# bot.py - Advanced Watermark remover Telegram bot
# Admin commands + Progress indicator + MongoDB job tracking
# WARNING: credentials are hardcoded as requested. Keep repo private.

import os
import re
import time
import asyncio
import subprocess
import logging
from pathlib import Path
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message

import motor.motor_asyncio

# ------------------ HARD-CODED CREDENTIALS (user provided) ------------------
BOT_TOKEN = "7852091851:AAHQr_w4hi-RuJ5sJ8JvQCo_fOZtf6EWhvk"
API_ID = 21688431
API_HASH = "db274cb8e9167e731d9c8305197badeb"
MONGO_URI = "mongodb+srv://moviescorn:moviescorn@hitu.4jr5k.mongodb.net/hitu?retryWrites=true&w=majority&appName=Hitu"
# Admin ID (hardcoded)
ADMIN_ID = 6861892595
# -------------------------------------------------------------------------

# Runtime defaults (can be overridden via env but hardcoded defaults exist)
WATERMARK_METHOD = os.getenv("WATERMARK_METHOD", "delogo").lower()
WATERMARK_PARAMS = os.getenv("WATERMARK_PARAMS", "x=iw-160:y=ih-60:w=150:h=50")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE") or 500_000_000)

# Working directories
WORKDIR = Path("/tmp/wm_bot")
DOWNLOAD_DIR = WORKDIR / "download"
OUTPUT_DIR = WORKDIR / "out"
WORKDIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wm-bot")

# Pyrogram client (bot)
APP = Client("wmremover", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Mongo client (motor async) - DB "hitu"
if not MONGO_URI:
    logger.error("MONGO_URI not set")
    raise SystemExit("MONGO_URI missing")

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client["hitu"]

# Collections
COL_USERS = db["users"]
COL_JOBS = db["jobs"]
COL_SETTINGS = db["settings"]

# For uptime
START_TIME = datetime.utcnow()

# ------------------ Helper functions ------------------

def hhmmss_to_seconds(hms_str: str) -> float:
    parts = hms_str.strip().split(':')
    try:
        if len(parts) == 3:
            h = int(parts[0]); m = int(parts[1]); s = float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m = int(parts[0]); s = float(parts[1])
            return m * 60 + s
        else:
            return float(parts[0])
    except Exception:
        try:
            return float(hms_str)
        except:
            return 0.0

def get_video_duration_seconds(path: str) -> float:
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries",
               "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        duration = float(out.decode().strip())
        return duration
    except Exception as e:
        logger.warning("ffprobe failed: %s", e)
        return 0.0

def parse_ffmpeg_time_from_line(line: str) -> float:
    m = re.search(r"time=(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+|\d+\.\d+)", line)
    if not m:
        return 0.0
    return hhmmss_to_seconds(m.group(1))

def parse_params(params: str):
    parts = params.replace(" ", "").split(":")
    d = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            d[k] = v
    return d

# ------------------ DB helpers ------------------

async def ensure_user(doc_user):
    q = {"user_id": doc_user["user_id"]}
    await COL_USERS.update_one(q, {"$setOnInsert": doc_user}, upsert=True)

async def create_job(user_id: int, tg_message_id: int, infile: str, method: str, params: str):
    job = {
        "user_id": user_id,
        "tg_message_id": tg_message_id,
        "infile": infile,
        "outfile": None,
        "method": method,
        "params": params,
        "status": "queued",
        "progress": 0,
        "error": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await COL_JOBS.insert_one(job)
    job["_id"] = res.inserted_id
    return job

async def update_job(job_id, patch: dict):
    patch["updated_at"] = datetime.utcnow()
    await COL_JOBS.update_one({"_id": job_id}, {"$set": patch})

# ------------------ Processing functions ------------------

def ffmpeg_delogo_with_progress(infile: str, outfile: str, params: str, progress_callback):
    duration = get_video_duration_seconds(infile)
    cmd = [
        "ffmpeg", "-y", "-i", infile,
        "-vf", f"delogo={params}",
        "-c:a", "copy",
        "-preset", "veryfast",
        outfile
    ]
    logger.info("FFMPEG command: %s", " ".join(cmd))
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, bufsize=1)

    last_percent = -1
    last_update_time = time.time()
    try:
        while True:
            line = proc.stderr.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            cur_seconds = parse_ffmpeg_time_from_line(line)
            if duration > 0:
                percent = int(min(100, (cur_seconds / duration) * 100))
            else:
                percent = 0
            now = time.time()
            if percent != last_percent and (now - last_update_time > 1.5 or abs(percent - last_percent) >= 2):
                last_percent = percent
                last_update_time = now
                try:
                    progress_callback(max(0, min(100, percent)))
                except Exception:
                    pass
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError("ffmpeg exited with code %d" % ret)
    finally:
        try:
            proc.kill()
        except:
            pass

def opencv_inpaint_with_progress(infile: str, outfile: str, x:int, y:int, w:int, h:int, progress_callback):
    import cv2
    cap = cv2.VideoCapture(infile)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(outfile, fourcc, fps, (width, height))

    frame_idx = 0
    mask = None
    last_percent = -1
    last_update_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if mask is None:
            mask = (frame[:,:,0]*0).astype("uint8")
            mask[y:y+h, x:x+w] = 255
        inpainted = cv2.inpaint(frame, mask, 3, cv2.INPAINT_TELEA)
        out.write(inpainted)
        frame_idx += 1
        if total_frames > 0:
            percent = int((frame_idx / total_frames) * 100)
        else:
            percent = int(min(99, frame_idx % 100))
        now = time.time()
        if percent != last_percent and (now - last_update_time > 1.5 or abs(percent - last_percent) >= 2):
            last_percent = percent
            last_update_time = now
            try:
                progress_callback(max(0, min(100, percent)))
            except:
                pass

    cap.release()
    out.release()
    try:
        progress_callback(100)
    except:
        pass

def process_video_sync(job_doc, progress_updater):
    infile = job_doc["infile"]
    base = Path(infile)
    outfile = str(OUTPUT_DIR / (base.stem + "_processed.mp4"))

    method = job_doc.get("method", "delogo")
    params = job_doc.get("params", "")

    if method == "delogo":
        ffmpeg_delogo_with_progress(infile, outfile, params, progress_updater)
    else:
        p = parse_params(params)
        w = int(p.get("w", "150"))
        h = int(p.get("h", "50"))
        import cv2
        cap = cv2.VideoCapture(infile)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        def resolve(v, fallback, total):
            if not v:
                return fallback
            if "iw" in v:
                try:
                    part = v.split("-")[-1]
                    return max(0, total - int(part) - w)
                except:
                    return fallback
            if "ih" in v:
                try:
                    part = v.split("-")[-1]
                    return max(0, total - int(part) - h)
                except:
                    return fallback
            try:
                return int(v)
            except:
                return fallback

        x = resolve(p.get("x",""), 0, width)
        y = resolve(p.get("y",""), 0, height)

        opencv_inpaint_with_progress(infile, outfile, x, y, w, h, progress_updater)

    return outfile

# ------------------ Bot Handlers & Admin Commands ------------------

def admin_only(func):
    async def wrapper(client, message: Message):
        uid = message.from_user.id if message.from_user else None
        if uid != ADMIN_ID:
            await message.reply_text("Yeh command sirf admin ke liye hai.")
            return
        return await func(client, message)
    return wrapper

@APP.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user = message.from_user
    doc_user = {
        "user_id": user.id,
        "first_name": user.first_name,
        "username": user.username,
        "created_at": datetime.utcnow()
    }
    await ensure_user(doc_user)
    await message.reply_text("Main watermark remover bot hun. Video bhejo — main process karke wapas bhej dungi. (Sirf apni videos par use karein.)")

@APP.on_message(filters.command("status") & filters.private)
@admin_only
async def cmd_status(client: Client, message: Message):
    uptime = datetime.utcnow() - START_TIME
    jobs_total = await COL_JOBS.count_documents({})
    jobs_processing = await COL_JOBS.count_documents({"status": "processing"})
    jobs_queued = await COL_JOBS.count_documents({"status": "queued"})
    jobs_done = await COL_JOBS.count_documents({"status": "done"})
    text = (
        f"Bot Status:\n"
        f"Uptime: {str(uptime).split('.',1)[0]}\n"
        f"Jobs total: {jobs_total}\n"
        f"Queued: {jobs_queued}, Processing: {jobs_processing}, Done: {jobs_done}\n"
        f"DB: hitu\n"
    )
    await message.reply_text(text)

@APP.on_message(filters.command("jobs") & filters.private)
@admin_only
async def cmd_jobs(client: Client, message: Message):
    cur = COL_JOBS.find().sort("created_at", -1).limit(10)
    jobs = await cur.to_list(length=10)
    if not jobs:
        await message.reply_text("Koi bhi job nahi mila.")
        return
    lines = []
    for j in jobs:
        jid = str(j["_id"])
        status = j.get("status", "unknown")
        user_id = j.get("user_id")
        created = j.get("created_at").strftime("%Y-%m-%d %H:%M:%S")
        progress = j.get("progress", 0)
        lines.append(f"{jid[:8]} | user:{user_id} | {status} | {progress}% | {created}")
    await message.reply_text("Recent jobs:\n" + "\n".join(lines))

@APP.on_message(filters.command("set_params") & filters.private)
@admin_only
async def cmd_set_params(client: Client, message: Message):
    global WATERMARK_METHOD, WATERMARK_PARAMS
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await message.reply_text("Usage: /set_params <delogo|inpaint> <params>")
        return
    method = parts[1].lower()
    params = parts[2] if len(parts) >= 3 else ""
    if method not in ("delogo", "inpaint"):
        await message.reply_text("Method must be 'delogo' or 'inpaint'.")
        return
    WATERMARK_METHOD = method
    if params:
        WATERMARK_PARAMS = params
    await COL_SETTINGS.update_one({"_id": "processing"}, {"$set": {"method": WATERMARK_METHOD, "params": WATERMARK_PARAMS}}, upsert=True)
    await message.reply_text(f"Updated method={WATERMARK_METHOD} params={WATERMARK_PARAMS}")

@APP.on_message((filters.video | filters.document))
async def on_video(client: Client, message: Message):
    m = message
    user = m.from_user
    if not user:
        await m.reply_text("User information missing.")
        return

    size = 0
    if m.video:
        size = m.video.file_size or 0
    elif m.document:
        size = m.document.file_size or 0

    if size > MAX_FILE_SIZE:
        await m.reply_text(f"File bahut bada hai ({size} > {MAX_FILE_SIZE}). Limit ko kam karo ya chhota file bhejo.")
        return

    status_msg = await m.reply_text("Video received — queue mein add kar rahi hun...")
    try:
        download_path = await m.download(file_name=str(DOWNLOAD_DIR))
        job = await create_job(user_id=user.id, tg_message_id=m.message_id, infile=download_path, method=WATERMARK_METHOD, params=WATERMARK_PARAMS)
        await update_job(job["_id"], {"status": "processing", "progress": 0})
        await status_msg.edit("Processing started — progress batati hun...")

        async def progress_update(percent: int):
            try:
                await update_job(job["_id"], {"progress": int(percent)})
            except Exception:
                pass
            try:
                await status_msg.edit(f"Processing: {int(percent)}%")
            except Exception:
                pass

        def progress_cb(percent: int):
            asyncio.get_event_loop().create_task(progress_update(percent))

        loop = asyncio.get_event_loop()
        try:
            outfile = await loop.run_in_executor(None, process_video_sync, job, progress_cb)
        except Exception as e:
            await update_job(job["_id"], {"status": "failed", "error": str(e), "progress": 0})
            await status_msg.edit(f"Processing failed: {e}")
            return

        await update_job(job["_id"], {"status": "done", "outfile": outfile, "progress": 100})
        await m.reply_video(video=outfile, caption="Watermark हटाकर भेज रही hun.")
        await status_msg.delete()
    except Exception as e:
        logger.exception("Error handling video")
        await status_msg.edit(f"Kuchh gadbad hui: {e}")
    finally:
        try:
            cutoff = datetime.utcnow().timestamp() - 3600
            for p in DOWNLOAD_DIR.iterdir():
                try:
                    if p.is_file() and p.stat().st_mtime < cutoff:
                        p.unlink()
                except:
                    pass
            for p in OUTPUT_DIR.iterdir():
                try:
                    if p.is_file() and p.stat().st_mtime < cutoff:
                        p.unlink()
                except:
                    pass
        except Exception:
            pass

# ------------------ Startup: Load settings from DB if present ------------------
async def load_settings():
    s = await COL_SETTINGS.find_one({"_id": "processing"})
    if s:
        global WATERMARK_METHOD, WATERMARK_PARAMS
        WATERMARK_METHOD = s.get("method", WATERMARK_METHOD)
        WATERMARK_PARAMS = s.get("params", WATERMARK_PARAMS)
        logger.info("Loaded settings from DB: %s %s", WATERMARK_METHOD, WATERMARK_PARAMS)

@APP.on_connect()
async def on_connect_handler(client, _):
    await load_settings()
    logger.info("Bot connected. Method=%s params=%s", WATERMARK_METHOD, WATERMARK_PARAMS)

if __name__ == "__main__":
    APP.run()
