# bot/main.py
import asyncio
import os
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from .config import BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS
from .processor import enqueue, worker
from .db import log_action

load_dotenv()

app = Client("hitesh-auto-poster", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# welcome on /start (private)
@app.on_message(filters.private & filters.command("start"))
async def cmd_start(_, message: Message):
    await message.reply_text("Hello 🌸 Main ready hun — media aane par caption se URLs remove kar dungi. Admin ho to /stats, /pause, /resume use karo.")
    log_action("cmd_start", {"from": message.from_user.id})

# pause
@app.on_message(filters.private & filters.command("pause"))
async def cmd_pause(_, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply_text("❌ Aap admin nahi ho.")
    from .state import set_paused
    set_paused(True)
    await message.reply_text("⏸ Bot paused. Processing ruk gaya hai.")
    log_action("cmd_pause", {"by": message.from_user.id})

# resume
@app.on_message(filters.private & filters.command("resume"))
async def cmd_resume(_, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply_text("❌ Aap admin nahi ho.")
    from .state import set_paused
    set_paused(False)
    await message.reply_text("▶ Bot resumed. Processing shuru ho gaya hai.")
    log_action("cmd_resume", {"by": message.from_user.id})

# stats
@app.on_message(filters.private & filters.command("stats"))
async def cmd_stats(_, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.reply_text("❌ Aap admin nahi ho.")
    try:
        from .db import files_col, logs_col
        total = files_col.count_documents({})
        logs = logs_col.count_documents({})
        await message.reply_text(f"📊 Total unique media processed: {total}\n📝 Logs entries: {logs}")
    except Exception as e:
        await message.reply_text("Error fetching stats.")
        log_action("stats_failed", {"error": str(e)})

# media handler
@app.on_message(filters.video | filters.document | filters.animation)
async def on_media(_, message: Message):
    # enqueue for processing
    enqueue(message)
    # quick local ack (worker will show processing & final)
    log_action("enqueued", {"chat_id": message.chat.id, "msg_id": message.message_id})

async def start_background_tasks():
    # start worker coroutine
    loop = asyncio.get_event_loop()
    loop.create_task(worker(app))
    # notify admins
    try:
        for admin in ADMIN_IDS:
            try:
                await app.send_message(chat_id=admin, text="🤖 HITESH-AUTO-POSTER Bot started and running.")
            except Exception:
                pass
    except Exception:
        pass

def run():
    app.start()
    asyncio.get_event_loop().run_until_complete(start_background_tasks())
    app.idle()

if __name__ == "__main__":
    run()
