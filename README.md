# 🤖 Telegram Auto Forward Bot

Automatically forwards videos from one Telegram channel to another with URL removal and MongoDB tracking.

## ✨ Features

- ✅ Auto-forward videos between channels
- ✅ Remove URLs/mentions from captions
- ✅ MongoDB integration for tracking
- ✅ Duplicate prevention
- ✅ Rate limiting
- ✅ Health monitoring
- ✅ Web dashboard
- ✅ Admin notifications

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.7+
- MongoDB (Local or Atlas)
- Telegram Bot Token
- Telegram API Credentials

### 2. Installation
```bash
# Clone repository
git clone https://github.com/yourusername/telegram-forward-bot.git
cd telegram-forward-bot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
