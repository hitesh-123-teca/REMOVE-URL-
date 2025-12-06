# bot-web.py
# Healthcheck / entrypoint for Koyeb (imports bot so bot runs in same process)

from flask import Flask
import os
from dotenv import load_dotenv

load_dotenv()

FLASK_PORT = int(os.getenv("PORT", 8080))

app = Flask("hitesh-auto-poster-web")

@app.route("/")
def index():
    return "HITESH-AUTO-POSTER Bot is alive ✅", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=FLASK_PORT)
