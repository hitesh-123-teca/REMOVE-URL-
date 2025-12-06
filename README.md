# HITESH-AUTO-POSTER

Auto media processor that removes URLs from captions and replaces the original message with a cleaned one.

## Features
- Removes links from media captions (regex + safe)
- Stores seen files in MongoDB to prevent duplicates
- Deletes duplicate messages automatically
- Shows processing message while cleaning and replaces original with cleaned media
- Admin commands: /start, /pause, /resume, /stats

## Setup
1. Create folder `HITESH-AUTO-POSTER`
2. Place all files in correct structure (bot/ folder + top-level files)
3. Create `.env` from `.env.example` and fill secrets
4. Build and run:
   - Locally:
     ```
     pip install -r requirements.txt
     python -m bot.main
     python bot-web.py  # optional, web healthcheck
     ```
   - Docker:
     ```
     docker build -t hitesh-auto-poster .
     docker run -e BOT_TOKEN=... -e API_ID=... -e API_HASH=... -e MONGO_URI=... -p 8080:8080 hitesh-auto-poster
     ```
   - Koyeb: connect repo, set env vars in Koyeb dashboard, deploy from Dockerfile.

## Permissions
- Bot must be added to chats/groups and given:
  - Read/View messages
  - Post messages
  - Delete messages (required for auto-delete)

## Notes
- Keep `USE_HASH_FOR_DUPLICATES=false` by default for performance.
- If you enable hashing, bot will download media temporarily to compute SHA256.
