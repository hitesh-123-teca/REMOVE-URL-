#!/usr/bin/env python3
import os
import sys
import time
import logging
import subprocess
import asyncio
from pathlib import Path
import shutil
import cv2
import numpy as np
import pytesseract
from datetime import datetime
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message

# -------------------- CONFIGURATION --------------------
BOT_TOKEN = "7852091851:AAHQr_w4hi-RuJ5sJ8JvQCo_fOZ"
API_ID = 29227473
API_HASH = "d61b2bdb253758bcb90782bb17d4cc0c"
ADMIN_IDS = [6861892595]
MONGO_URI = "mongodb+srv://moviescorn:moviescorn@hitu.4jr5k.mongodb.net/?retryWrites=true&w=majority&appName=Hitu"

# -------------------- INITIAL SETUP --------------------
try:
    os.system("ntpdate -u time.google.com || true")
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bot")

WORKDIR = Path("/tmp/bot_work")
WORKDIR.mkdir(parents=True, exist_ok=True)

# -------------------- MONGO CONNECTION --------------------
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["remove_url_bot"]
    users_col = db["users"]
    logs_col = db["logs"]
    log.info("✅ MongoDB connected successfully.")
except Exception as e:
    log.error("❌ MongoDB connection failed: %s", e)
    sys.exit(1)

# -------------------- TELEGRAM CLIENT --------------------
app = Client("removeurl_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# -------------------- DATABASE HELPERS --------------------
def register_user(user):
    if not user:
        return
    if not users_col.find_one({"user_id": user.id}):
        users_col.insert_one({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "joined_at": datetime.utcnow()
        })

def save_log(user_id, file_type, status="done"):
    logs_col.insert_one({
        "user_id": user_id,
        "file_type": file_type,
        "status": status,
        "timestamp": datetime.utcnow()
    })

# -------------------- OCR & PROCESSING --------------------
def ocr_detect_boxes(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return []
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
    boxes = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        if any(s in text.lower() for s in [".com", ".in", "http", "www", "/", ".net", ".org"]):
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            boxes.append((x, y, w, h))
    return boxes

def inpaint_image(input_path, boxes, output_path):
    img = cv2.imread(input_path)
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    for x, y, w, h in boxes:
        cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
    res = cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)
    cv2.imwrite(output_path, res)

def largest_box(boxes):
    if not boxes:
        return None
    return sorted(boxes, key=lambda b: b[2]*b[3], reverse=True)[0]

def build_ffmpeg_cmd(input_video, x, y, w, h, output_video):
    return [
        "ffmpeg", "-y", "-i", input_video,
        "-vf", f"delogo=x={x}:y={y}:w={w}:h={h}:show=0",
        "-c:a", "copy", "-preset", "fast",
        output_video
    ]

# -------------------- PROCESSING FUNCTIONS --------------------
async def process_image(path_in, path_out, msg: Message):
    boxes = ocr_detect_boxes(path_in)
    if boxes:
        await msg.edit_text("Text detect hua — remove kar rahi hun...")
        inpaint_image(path_in, boxes, path_out)
    else:
        shutil.copyfile(path_in, path_out)
        await msg.edit_text("Koi URL text nahi mila, original bhej rahi hun.")

async def process_video(path_in, path_out, msg: Message):
    tmp_frame = WORKDIR / "frame.jpg"
    subprocess.run(["ffmpeg", "-y", "-i", path_in, "-vframes", "1", str(tmp_frame)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    boxes = ocr_detect_boxes(str(tmp_frame))
    if not boxes:
        shutil.copyfile(path_in, path_out)
        await msg.edit_text("Koi URL text nahi mila, original bhej rahi hun.")
        return
    x, y, w, h = largest_box(boxes)
    cmd = build_ffmpeg_cmd(path_in, x, y, w, h, path_out)
    await msg.edit_text("Video process ho raha hai (thoda time lagega)...")
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await msg.edit_text("Ho gaya ✅")

# -------------------- COMMANDS --------------------
@app.on_message(filters.command("start"))
async def start_cmd(_, msg):
    register_user(msg.from_user)
    await msg.reply_text("👋 Namaste! Mujhe photo/video bhejo, main URL hata dungi.\nUse /help for more info.")

@app.on_message(filters.command("help"))
async def help_cmd(_, msg):
    await msg.reply_text("Commands:\n/start - Start bot\n/help - Help\n/stats - Show usage stats (admin only)")

@app.on_message(filters.command("stats") & filters.user(ADMIN_IDS))
async def stats_cmd(_, msg):
    total_users = users_col.count_documents({})
    total_logs = logs_col.count_documents({})
    await msg.reply_text(f"👥 Users: {total_users}\n📂 Files processed: {total_logs}")

@app.on_message(filters.photo | filters.video)
async def media_handler(_, msg):
    register_user(msg.from_user)
    prog = await msg.reply_text("File mili — processing start kar rahi hun...")
    fpath = WORKDIR / f"input_{int(time.time())}"
    outpath = WORKDIR / f"output_{int(time.time())}"

    if msg.photo:
        fpath = Path(f"{fpath}.jpg")
        outpath = Path(f"{outpath}.jpg")
        await msg.download(file_name=str(fpath))
        await process_image(str(fpath), str(outpath), prog)
        await msg.reply_photo(str(outpath))
        save_log(msg.from_user.id, "image")

    elif msg.video:
        fpath = Path(f"{fpath}.mp4")
        outpath = Path(f"{outpath}.mp4")
        await msg.download(file_name=str(fpath))
        await process_video(str(fpath), str(outpath), prog)
        await msg.reply_video(str(outpath))
        save_log(msg.from_user.id, "video")

    await prog.delete()

# -------------------- RUN --------------------
if __name__ == "__main__":
    try:
        os.system("ntpdate -u time.google.com || true")
    except Exception:
        pass
    app.run()
