# Teleforward Bot

This repository contains a Telegram bot that:
- Forwards video/document/animation from multiple source channels to a target channel.
- Removes URLs from captions and inline buttons.
- Rewrites caption using a template.
- Logs forwarding data to MongoDB.
- Blocks duplicate media by file_unique_id.
- Provides admin commands: /start, /pause, /resume, /stats.
- Includes a small webserver for healthchecks (useful for Koyeb).

## Setup

1. Create a `.env` with the following keys:

```
BOT_TOKEN=...
API_ID=...
API_HASH=...
SOURCE_CHANNELS=-100111111111,-100222222222
TARGET_CHANNEL=-100333333333
MONGODB_URI=...
CAPTION_TEMPLATE={caption}\n\n— Shared by @source
PORT=8080
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Run:
```
python main.py
```

## Notes
- Auto-delete is intentionally NOT implemented.
- For Koyeb deploy, use Dockerfile and set environment variables in the Koyeb dashboard.
- Add admin Telegram IDs to `ADMINS` list in `main.py`.
