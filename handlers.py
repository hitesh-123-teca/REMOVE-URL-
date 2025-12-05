import re
import datetime
from queue import Queue, Empty
from pyrogram.types import InlineKeyboardMarkup
from config import SOURCE_CHANNELS, TARGET_CHANNEL, CAPTION_TEMPLATE
from db import forwards_col
from state import get_forward_state, check_duplicate, add_duplicate
import asyncio

q = Queue()

URL_REGEX = re.compile(
    r"(https?://\S+)|((?:t\.me|telegram\.me)/\S+)|(\bwww\.\S+\b)",
    flags=re.IGNORECASE
)

def remove_urls_from_text(text):
    if not text: 
        return text, []
    removed = []
    def collect(m):
        for g in m.groups():
            if g:
                removed.append(g)
                break
        return ""
    cleaned = URL_REGEX.sub(collect, text).strip()
    return cleaned, removed

def clean_keyboard(kb):
    if not kb: 
        return None
    rows = []
    for row in kb:
        new_row = [btn for btn in row if not (btn.url and URL_REGEX.search(btn.url))]
        if new_row:
            rows.append(new_row)
    return InlineKeyboardMarkup(rows) if rows else None

async def process(client):
    """
    Worker: runs in background thread via asyncio.run
    Processes messages from queue (blocking Queue), handles forward logic.
    """
    loop = asyncio.get_event_loop()
    while True:
        try:
            message = q.get(timeout=1)
        except Empty:
            await asyncio.sleep(0.5)
            continue

        if get_forward_state():
            q.task_done()
            continue

        # determine unique id
        uid = None
        if message.video:
            uid = message.video.file_unique_id
        elif message.document:
            uid = message.document.file_unique_id
        elif message.animation:
            uid = message.animation.file_unique_id
        else:
            q.task_done()
            continue

        if check_duplicate(uid):
            q.task_done()
            continue
        add_duplicate(uid)

        caption = message.caption or message.text or ""
        cleaned, removed_links = remove_urls_from_text(caption)
        final = CAPTION_TEMPLATE.replace("{caption}", cleaned).replace("{source}", message.chat.username or "source")
        kb = clean_keyboard(message.reply_markup)

        try:
            # copy and then edit as needed
            copied = await message.copy(chat_id=TARGET_CHANNEL)
            if final:
                try:
                    await copied.edit(final, reply_markup=kb, disable_web_page_preview=True)
                except Exception:
                    pass
            elif kb:
                try:
                    await copied.edit_reply_markup(kb)
                except Exception:
                    pass

            forwards_col.insert_one({
                "source_chat": message.chat.id,
                "source_msg_id": message.id,
                "copied_msg_id": copied.id,
                "timestamp": datetime.datetime.utcnow(),
                "removed_links": removed_links
            })
        except Exception as e:
            # best-effort logging to console
            print("Forward error:", e)

        q.task_done()

async def on_channel_message(client, message):
    """
    Handler attached to pyrogram. Put message into queue.
    """
    if str(message.chat.id) not in SOURCE_CHANNELS:
        return
    if not (message.video or message.document or message.animation):
        return
    # put message into processing queue
    q.put(message)
