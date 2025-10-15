#!/bin/bash
# Manager Max Discord Bot - One-Click Setup
# Usage: ./setup.sh

set -e

clear
cat << "EOF"
╔═══════════════════════════════════════════╗
║   Manager Max Discord Bot - Setup        ║
╚═══════════════════════════════════════════╝
EOF

# Colors
G='\033[0;32m' # Green
Y='\033[1;33m' # Yellow
R='\033[0;31m' # Red
NC='\033[0m'   # No Color

# Get current directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo -e "\n${G}[1/7] Checking system...${NC}"
if ! command -v apt-get &> /dev/null; then
    echo -e "${R}Error: Ubuntu/Debian required${NC}"
    exit 1
fi

echo -e "${G}[2/7] Installing Python...${NC}"
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv > /dev/null 2>&1

echo -e "${G}[3/7] Creating virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo -e "${G}[4/7] Creating data directories...${NC}"
mkdir -p tools/data img

# Create data files
for file in activity_manager task_manager review_manager post_manager; do
    echo '{"instances": []}' > "tools/data/${file}.json"
done

echo -e "${G}[5/7] Configuring bot token...${NC}"
if [ ! -f "config.json" ] || grep -q "YOUR_BOT_TOKEN_HERE" config.json 2>/dev/null; then
    echo -e "${Y}Enter your Discord bot token:${NC}"
    read -p "Token: " BOT_TOKEN

    cat > config.json << CONF
{
  "token": "$BOT_TOKEN",
  "allowed_user_ids": [1428084017114124449, 690283716823613461],
  "bot_settings": {
    "status": "online",
    "activity": "Manage le serveur."
  }
}
CONF
    echo -e "${G}Token saved!${NC}"
else
    echo -e "${G}Using existing config.json${NC}"
fi

echo -e "${G}[6/7] Setting up systemd service...${NC}"
USER=$(whoami)
SERVICE_FILE="/tmp/manager-max-bot.service"

cat > "$SERVICE_FILE" << SERV
[Unit]
Description=Manager Max Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DIR
Environment="PATH=$DIR/venv/bin:/usr/bin:/bin"
ExecStart=$DIR/venv/bin/python3 $DIR/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=manager-max-bot
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERV

sudo cp "$SERVICE_FILE" /etc/systemd/system/manager-max-bot.service
sudo chmod 644 /etc/systemd/system/manager-max-bot.service
sudo systemctl daemon-reload
sudo systemctl enable manager-max-bot.service

echo -e "${G}[7/7] Starting bot...${NC}"
sudo systemctl start manager-max-bot
sleep 2

# Check status
if systemctl is-active --quiet manager-max-bot.service; then
    echo -e "\n${G}╔═══════════════════════════════════════════╗"
    echo -e "║     ✅ Installation Complete! ✅         ║"
    echo -e "╚═══════════════════════════════════════════╝${NC}\n"

    echo -e "${G}Bot is running!${NC}\n"
    echo "Useful commands:"
    echo "  Status:  ${Y}sudo systemctl status manager-max-bot${NC}"
    echo "  Logs:    ${Y}sudo journalctl -u manager-max-bot -f${NC}"
    echo "  Stop:    ${Y}sudo systemctl stop manager-max-bot${NC}"
    echo "  Restart: ${Y}sudo systemctl restart manager-max-bot${NC}"
    echo ""
else
    echo -e "${R}❌ Bot failed to start. Check logs:${NC}"
    echo "  sudo journalctl -u manager-max-bot -n 50"
    exit 1
fi
