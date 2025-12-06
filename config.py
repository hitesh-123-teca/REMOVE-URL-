# bot/config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")

# ADMIN_IDS as comma separated in .env, e.g. 123456789,987654321
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

MONGODB_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")

# behavior flags
DELETE_DUPLICATES = os.getenv("DELETE_DUPLICATES", "true").lower() in ("1","true","yes")
USE_HASH_FOR_DUPLICATES = os.getenv("USE_HASH_FOR_DUPLICATES", "false").lower() in ("1","true","yes")

# messages & tunables
CAPTION_TEMPLATE = os.getenv("CAPTION_TEMPLATE", "{caption}")
PROCESSING_MESSAGE = os.getenv("PROCESSING_MESSAGE", "⏳ Processing media... removing links...")
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS", "0"))
QUEUE_MAX_SIZE = int(os.getenv("QUEUE_MAX_SIZE", "1000"))
PORT = int(os.getenv("PORT", "8080"))
