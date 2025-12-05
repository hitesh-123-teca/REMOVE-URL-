import threading
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, SOURCE_CHANNELS
from webserver import run as run_web
from handlers import on_channel_message, process
from state import pause_forward, resume_forward, get_forward_state
from db import forwards_col

ADMINS = []  # अपना Telegram ID यहाँ डालें (जैसे: [123456789])

app = Client("bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

@app.on_message(filters.chat(list(map(int, SOURCE_CHANNELS))) & (filters.video | filters.animation | filters.document))
async def _(_, message: Message):
    await on_channel_message(_, message)

@app.on_message(filters.private & filters.command("start"))
async def start_cmd(_, msg):
    await msg.reply("Hello 🌸 Bot kaam par hai — auto-forward + clean + safe.")

@app.on_message(filters.private & filters.command("pause"))
async def pause_cmd(_, msg):
    if msg.from_user.id not in ADMINS: 
        return
    pause_forward()
    await msg.reply("⏸ Forwarding Paused")

@app.on_message(filters.private & filters.command("resume"))
async def resume_cmd(_, msg):
    if msg.from_user.id not in ADMINS: 
        return
    resume_forward()
    await msg.reply("▶ Forwarding Resumed")

@app.on_message(filters.private & filters.command("stats"))
async def stats_cmd(_, msg):
    if msg.from_user.id not in ADMINS: 
        return
    c = forwards_col.count_documents({})
    await msg.reply(f"📊 Total forwarded: {c}\\n🟢 Status: {'Paused' if get_forward_state() else 'Running'}")

def start():
    # start webserver for healthchecks
    threading.Thread(target=run_web, daemon=True).start()
    # start queue worker in background thread
    worker_thread = threading.Thread(target=lambda: asyncio.run(process(app)), daemon=True)
    worker_thread.start()
    # run pyrogram client (blocking)
    app.run()

if __name__ == "__main__":
    start()
