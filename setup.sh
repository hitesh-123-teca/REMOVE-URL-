#!/bin/bash

# Telegram Video Bot Setup Script
# Version: 2.0.0

set -e

echo ""
echo "🎬 TELEGRAM VIDEO FORWARD BOT SETUP"
echo "===================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored text
print_color() {
    echo -e "${2}${1}${NC}"
}

# Check Python
print_color "1. Checking Python version..." $BLUE
if ! command -v python3 &> /dev/null; then
    print_color "❌ Python3 is not installed" $RED
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
print_color "✅ Python $PYTHON_VERSION detected" $GREEN

# Check FFmpeg
print_color "\n2. Checking FFmpeg..." $BLUE
if ! command -v ffmpeg &> /dev/null; then
    print_color "⚠️ FFmpeg not found. Installing..." $YELLOW
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install ffmpeg
    else
        print_color "❌ Please install FFmpeg manually" $RED
        exit 1
    fi
fi
print_color "✅ FFmpeg installed" $GREEN

# Create virtual environment
print_color "\n3. Setting up virtual environment..." $BLUE
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_color "✅ Virtual environment created" $GREEN
else
    print_color "✅ Virtual environment already exists" $YELLOW
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
print_color "\n4. Upgrading pip..." $BLUE
pip install --upgrade pip
print_color "✅ pip upgraded" $GREEN

# Install dependencies
print_color "\n5. Installing dependencies..." $BLUE
pip install -r requirements.txt
print_color "✅ Dependencies installed" $GREEN

# Create .env file if not exists
print_color "\n6. Setting up configuration..." $BLUE
if [ ! -f .env ]; then
    cp .env.example .env
    print_color "✅ Created .env file from template" $GREEN
    print_color "⚠️ Please edit .env file with your credentials" $YELLOW
else
    print_color "✅ .env file already exists" $YELLOW
fi

# Create directories
print_color "\n7. Creating directories..." $BLUE
mkdir -p temp logs thumbnails processed
print_color "✅ Directories created" $GREEN

# Make scripts executable
print_color "\n8. Setting up scripts..." $BLUE
chmod +x setup.sh
print_color "✅ Scripts made executable" $GREEN

# Check MongoDB
print_color "\n9. Checking MongoDB connection..." $BLUE
if ! command -v mongod &> /dev/null; then
    print_color "⚠️ MongoDB not installed locally" $YELLOW
    print_color "You can use MongoDB Atlas (cloud) or install locally:" $YELLOW
    print_color "For Ubuntu: sudo apt install mongodb" $YELLOW
    print_color "For Mac: brew install mongodb-community" $YELLOW
else
    if systemctl is-active --quiet mongod || pgrep -x "mongod" > /dev/null; then
        print_color "✅ MongoDB is running" $GREEN
    else
        print_color "⚠️ MongoDB installed but not running" $YELLOW
    fi
fi

# Setup complete
echo ""
print_color "====================================" $BLUE
print_color "✅ SETUP COMPLETE!" $GREEN
print_color "====================================" $BLUE
echo ""
print_color "Next steps:" $BLUE
echo "1. Edit .env file with your bot token and MongoDB URI"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run the bot: python main.py"
echo ""
print_color "For Docker:" $BLUE
echo "docker-compose up -d"
echo ""
print_color "For Koyeb deployment:" $BLUE
echo "1. Push to GitHub"
echo "2. Create app on Koyeb"
echo "3. Add environment variables"
echo "4. Deploy!"
echo ""
print_color "Bot Commands:" $BLUE
echo "/start - Start bot"
echo "/set_source - Set source channel"
echo "/set_target - Set target channel"
echo "/stats - Show statistics"
echo "/help - Show help"
echo ""
