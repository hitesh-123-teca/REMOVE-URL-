# bot.py
import os
import asyncio
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from pyrogram import Client, filters
from pyrogram.types import Message

import motor.motor_asyncio
import bson

# load env (local dev). On Koyeb, set real env via Secrets.
load_dotenv()

# --- Configuration / env ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI")
WATERMARK_METHOD = os.getenv("WATERMARK_METHOD", "delogo").lower()
WATERMARK_PARAMS = os.getenv("WATERMARK_PARAMS", "x=iw-160:y=ih-60:w=150:h=50")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE") or 500_000_000)

# working directories
WORKDIR = Path("/tmp/wm_bot")
DOWNLOAD_DIR = WORKDIR / "download"
OUTPUT_DIR = WORKDIR / "out"
WORKDIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# setup logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wm-bot")

# Pyrogram client
APP = Client("wmremover", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# Mongo client (motor async)
if not MONGO_URI:
    logger.error("MONGO_URI not set in environment")
    raise SystemExit("MONGO_URI missing")

mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client.get_default_database()  # Atlas connection string can include DB name

# Collections
COL_USERS = db["users"]
COL_JOBS = db["jobs"]
COL_SETTINGS = db["settings"]

# Utility: ffmpeg delogo
def ffmpeg_delogo(infile: str, outfile: str, params: str):
    cmd = [
        "ffmpeg", "-y", "-i", infile,
        "-vf", f"delogo={params}",
        "-c:a", "copy",
        outfile
    ]
    logger.info("Running ffmpeg delogo: %s", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc

# Utility: parse params (x=..:y=..:w=..:h=..)
def parse_params(params: str):
    parts = params.replace(" ", "").split(":")
    d = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            d[k] = v
    return d

# Store user if new
async def ensure_user(doc_user):
    q = {"user_id": doc_user["user_id"]}
    await COL_USERS.update_one(q, {"$setOnInsert": doc_user}, upsert=True)

# Create a job in DB
async def create_job(user_id: int, tg_message_id: int, infile: str, method: str, params: str):
    job = {
        "user_id": user_id,
        "tg_message_id": tg_message_id,
        "infile": infile,
        "outfile": None,
        "method": method,
        "params": params,
        "status": "queued",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = await COL_JOBS.insert_one(job)
    job["_id"] = res.inserted_id
    return job

# Update job
async def update_job(job_id, patch: dict):
    patch["updated_at"] = datetime.utcnow()
    await COL_JOBS.update_one({"_id": job_id}, {"$set": patch})

# Processing function (runs in threadpool)
def process_video_sync(job_doc):
    infile = job_doc["infile"]
    base = Path(infile)
    outfile = str(OUTPUT_DIR / (base.stem + "_processed.mp4"))

    method = job_doc.get("method", "delogo")
    params = job_doc.get("params", "")

    if method == "delogo":
        proc = ffmpeg_delogo(infile, outfile, params)
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="ignore")
            raise RuntimeError(f"ffmpeg failed: {err[:1000]}")
    else:
        # fallback to simple inpaint using OpenCV - basic implementation
        try:
            import cv2
            p = parse_params(params)
            # defaults
            w = int(p.get("w", "150"))
            h = int(p.get("h", "50"))
            # open capture to get dimensions
            cap = cv2.VideoCapture(infile)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            # compute x,y if expressions exist like iw-160
            def resolve(v, fallback, total):
                if not v:
                    return fallback
                if "iw" in v:
                    # example iw-160
                    try:
                        return max(0, total - int(v.split("-")[-1]) - w)
                    except:
                        return fallback
                if "ih" in v:
                    try:
                        return max(0, total - int(v.split("-")[-1]) - h)
                    except:
                        return fallback
                try:
                    return int(v)
                except:
                    return fallback
            x = resolve(p.get("x",""), 0, width)
            y = resolve(p.get("y",""), 0, height)

            # perform frame-by-frame inpaint
            cap = cv2.VideoCapture(infile)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(outfile, fourcc, fps, (width, height))
            mask = None
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if mask is None:
                    mask = (frame[:,:,0]*0).astype("uint8")
                    mask[y:y+h, x:x+w] = 255
                inpainted = cv2.inpaint(frame, mask, 3, cv2.INPAINT_TELEA)
                out.write(inpainted)
            cap.release()
            out.release()
        except Exception as e:
            raise RuntimeError(f"opencv inpaint failed: {e}")

    return outfile

# --- Handlers ---
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

@APP.on_message((filters.video | filters.document) & ~filters.edited)
async def on_video(client: Client, message: Message):
    # Accept video files only
    m = message
    user = m.from_user
    if not user:
        await m.reply_text("User info missing.")
        return

    # check file size
    size = 0
    if m.video:
        size = m.video.file_size or 0
    elif m.document:
        size = m.document.file_size or 0

    if size > MAX_FILE_SIZE:
        await m.reply_text(f"File bahut bada hai ({size} > {MAX_FILE_SIZE}). Limit ko kam karo ya chhota file bhejo.")
        return

    status_msg = await m.reply_text("Video received — queue mein add kar rahi hun...")

    # download file
    try:
        download_path = await m.download(file_name=str(DOWNLOAD_DIR))
        # record job in DB
        job = await create_job(user_id=user.id, tg_message_id=m.message_id, infile=download_path, method=WATERMARK_METHOD, params=WATERMARK_PARAMS)
        await update_job(job["_id"], {"status": "processing"})
        await status_msg.edit("Processing started — thoda samay lag sakta hai.")

        # run processing in threadpool to avoid blocking asyncio loop
        loop = asyncio.get_event_loop()
        try:
            outfile = await loop.run_in_executor(None, process_video_sync, job)
        except Exception as e:
            await update_job(job["_id"], {"status": "failed", "error": str(e)})
            await status_msg.edit(f"Processing failed: {e}")
            return

        # upload result
        await update_job(job["_id"], {"status": "done", "outfile": outfile})
        await m.reply_video(video=outfile, caption="Watermark हटाकर भेज रही hun.")
        await status_msg.delete()
    except Exception as e:
        logger.exception("Error handling video")
        await status_msg.edit(f"Kuchh gadbad hui: {e}")
    finally:
        # cleanup old files (simple policy)
        try:
            # remove files older than 1 hour
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

if __name__ == "__main__":
    APP.run()
