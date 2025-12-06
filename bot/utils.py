# bot/utils.py
# Placeholder for helper functions. Add as needed.
def safe_get(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default
