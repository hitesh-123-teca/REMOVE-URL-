# bot/processor.py
import re
import asyncio
import hashlib
import tempfile
import os
from queue import Queue, Empty
from typing import Optional
from pyrogram.types import Message
from .db import files_col, log_action
from .config import USE_HASH_FOR_DUPLICATES, DELETE_DELAY_SECONDS, PROCESSING_MESSAGE

URL_REGEX = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+", flags=re.IGNORECASE)

q = Queue()

def remove_urls_from_text(text: Optional[str]):
    if not text:
        return None, []
    removed = []
    def collect(m):
        s = m.group(0)
        removed.append(s)
        return ""
    cleaned = URL_REGEX.sub(collect, text).strip()
    return cleaned if cleaned else None, removed

def is_duplicate_by_unique_id(file_unique_id: str) -> bool:
    return files_col.find_one({"file_unique_id": file_unique_id}) is not None

def mark_seen(file_unique_id: str, meta: dict):
    files_col.insert_one({"file_unique_id": file_unique_id, "meta": meta})

async def compute_hash_from_file(client, message: Message, file_field: str):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        file_path = await message.download(file_name=path)
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception:
        return None
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

def enqueue(message: Message):
    try:
        q.put_nowait(message)
    except Exception:
        pass

async def worker(client):
    loop = asyncio.get_event_loop()
    while True:
        try:
            message = q.get(timeout=1)
        except Empty:
            await asyncio.sleep(0.2)
            continue

        try:
            # determine file field and unique id
            file_unique_id = None
            file_field = None
            if message.video:
                file_unique_id = message.video.file_unique_id
                file_field = "video"
            elif message.document:
                file_unique_id = message.document.file_unique_id
                file_field = "document"
            elif message.animation:
                file_unique_id = message.animation.file_unique_id
                file_field = "animation"

            if not file_unique_id:
                q.task_done()
                continue

            # duplicate check by unique_id
            if is_duplicate_by_unique_id(file_unique_id):
                try:
                    # delete duplicate after optional delay
                    if DELETE_DELAY_SECONDS > 0:
                        await asyncio.sleep(DELETE_DELAY_SECONDS)
                    await client.delete_messages(chat_id=message.chat.id, message_ids=message.message_id)
                    log_action("deleted_duplicate", {"chat_id": message.chat.id, "msg_id": message.message_id, "file_unique_id": file_unique_id})
                except Exception as e:
                    log_action("delete_failed", {"error": str(e), "chat_id": message.chat.id, "msg_id": message.message_id})
                q.task_done()
                continue

            # optional hash check
            file_hash = None
            if USE_HASH_FOR_DUPLICATES:
                try:
                    file_hash = await compute_hash_from_file(client, message, file_field)
                    if file_hash and files_col.find_one({"file_hash": file_hash}):
                        if DELETE_DELAY_SECONDS > 0:
                            await asyncio.sleep(DELETE_DELAY_SECONDS)
                        try:
                            await client.delete_messages(chat_id=message.chat.id, message_ids=message.message_id)
                            log_action("deleted_duplicate_by_hash", {"chat_id": message.chat.id, "msg_id": message.message_id, "file_hash": file_hash})
                        except Exception as ex:
                            log_action("delete_failed_hash", {"error": str(ex), "chat_id": message.chat.id, "msg_id": message.message_id})
                        q.task_done()
                        continue
                except Exception:
                    pass

            # mark seen
            meta = {"chat_id": message.chat.id, "message_id": message.message_id, "type": file_field}
            if file_hash:
                meta["file_hash"] = file_hash
            mark_seen(file_unique_id, meta)

            # cleaning caption
            raw = message.caption or message.text or None
            cleaned_caption, removed_links = remove_urls_from_text(raw)

            # processing status message
            processing_msg = None
            try:
                processing_msg = await client.send_message(chat_id=message.chat.id, text=PROCESSING_MESSAGE, reply_to_message_id=message.message_id)
            except Exception:
                processing_msg = None

            # send cleaned media (use file_id to avoid reupload)
            try:
                if message.video:
                    sent = await client.send_video(chat_id=message.chat.id, video=message.video.file_id, caption=cleaned_caption)
                elif message.document:
                    sent = await client.send_document(chat_id=message.chat.id, document=message.document.file_id, caption=cleaned_caption)
                elif message.animation:
                    sent = await client.send_animation(chat_id=message.chat.id, animation=message.animation.file_id, caption=cleaned_caption)
                else:
                    sent = None
            except Exception as e:
                log_action("send_failed", {"error": str(e), "chat_id": message.chat.id, "msg_id": message.message_id})
                sent = None

            # delete original
            try:
                await client.delete_messages(chat_id=message.chat.id, message_ids=message.message_id)
            except Exception as e:
                log_action("delete_original_failed", {"error": str(e), "chat_id": message.chat.id, "msg_id": message.message_id})

            # finalize processing_msg
            try:
                if processing_msg:
                    await processing_msg.edit_text("✅ Processed. Links removed.")
                    await asyncio.sleep(2)
                    await client.delete_messages(chat_id=processing_msg.chat.id, message_ids=processing_msg.message_id)
            except Exception:
                pass

            # log
            log_action("processed", {"chat_id": message.chat.id, "original_msg_id": message.message_id, "sent_msg_id": sent.message_id if sent else None, "removed_links": removed_links})

        except Exception as exc:
            log_action("worker_exception", {"error": str(exc)})
        finally:
            q.task_done()
