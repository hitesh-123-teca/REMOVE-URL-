from flask import Flask
from config import PORT

app = Flask("bot-web")

@app.route("/")
def home():
    return "OK", 200

def run():
    app.run(host="0.0.0.0", port=PORT)
