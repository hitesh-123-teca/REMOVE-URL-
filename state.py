from db import state_col, dup_col

def get_forward_state():
    doc = state_col.find_one({"_id": "bot"})
    if not doc:
        state_col.insert_one({"_id": "bot", "paused": False})
        return False
    return doc.get("paused", False)

def pause_forward():
    state_col.update_one({"_id": "bot"}, {"$set": {"paused": True}}, upsert=True)

def resume_forward():
    state_col.update_one({"_id": "bot"}, {"$set": {"paused": False}}, upsert=True)

def check_duplicate(file_unique_id):
    return dup_col.find_one({"file_unique_id": file_unique_id}) is not None

def add_duplicate(file_unique_id):
    dup_col.insert_one({"file_unique_id": file_unique_id})
