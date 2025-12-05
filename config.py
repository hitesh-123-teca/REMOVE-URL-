import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")

# multiple source channels (comma separated in .env)
SOURCE_CHANNELS = [x.strip() for x in os.getenv("SOURCE_CHANNELS", "").split(",") if x.strip()]
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL")

CAPTION_TEMPLATE = os.getenv("CAPTION_TEMPLATE", "{caption}\n\n— Shared by @source")
MONGODB_URI = os.getenv("MONGODB_URI")
PORT = int(os.getenv("PORT", 8080))
