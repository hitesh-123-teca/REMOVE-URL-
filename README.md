# Telegram Video Forward Bot 🎬

A powerful Telegram bot that automatically forwards videos between channels with advanced processing features.

## ✨ Features

### ✅ Core Features
- **MongoDB Database** - All data stored in MongoDB
- **Unlimited File Forwarding** - No restrictions on file size or count
- **Admin-Only Setup** - No manual ID entry required
- **Duplicate Auto-Detection & Delete** - Using file hash comparison
- **URL Removal from Captions** - Clean captions automatically
- **Auto Thumbnail Generation** - Extracts frame at 3-5 seconds
- **Basic Watermark Removal** - Optional watermark removal
- **Welcome Message** - Professional start message
- **Koyeb Ready** - Easy cloud deployment

### ⚡ Advanced Features
- **Multi-format Support** - MP4, MOV, AVI, MKV
- **Progress Tracking** - Real-time progress updates
- **Statistics Dashboard** - Detailed analytics
- **Admin Controls** - Remote management
- **Health Checks** - Automatic monitoring
- **Error Handling** - Comprehensive error recovery

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8+
- MongoDB (Local or Atlas)
- FFmpeg
- Telegram Bot Token

### 2. Installation

```bash
# Clone or create project
mkdir telegram-video-bot
cd telegram-video-bot

# Make setup script executable
chmod +x setup.sh

# Run setup
./setup.sh

# Edit environment file
nano .env
