from pymongo import MongoClient
from config import MONGODB_URI

client = MongoClient(MONGODB_URI)
db = client["telebot_db"]
forwards_col = db["forwards"]
state_col = db["state"]
dup_col = db["duplicates"]
