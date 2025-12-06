# bot/db.py
from pymongo import MongoClient, ASCENDING
from .config import MONGODB_URI
import datetime

client = MongoClient(MONGODB_URI)
db = client["hitesh_auto_poster"]

files_col = db["files"]         # stores seen files
logs_col = db["action_logs"]    # logs for admin (kept minimal per your choice)
state_col = db["state"]         # paused/running etc

# try to create TTL index for logs (7 days default, optional)
try:
    logs_col.create_index([("ts", ASCENDING)], expireAfterSeconds=7 * 24 * 3600)
except Exception:
    pass

def log_action(action: str, details: dict):
    try:
        doc = {"action": action, "details": details, "ts": datetime.datetime.utcnow()}
        logs_col.insert_one(doc)
    except Exception:
        pass
