#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "      🚀 NovaUnzip Autonomous Deployment Setup           "
echo "=========================================================="

# Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root or with sudo."
  exit 1
fi

echo "[+] Updating apt repositories..."
apt-get update -y
apt-get install -y --no-install-recommends \
    p7zip-full p7zip-rar unrar tar xz-utils bzip2 zstd ffmpeg python3 python3-pip python3-venv git

echo "[+] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[+] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "[!] No .env file found. Copying .env.example..."
  cp .env.example .env
  echo "[!] Please edit .env with your BOT_TOKEN and API credentials before launching!"
fi

echo "[+] Creating systemd service unit..."
cat << 'EOF' > /etc/systemd/system/nova-unzip.service
[Unit]
Description=NovaUnzip Telegram Bot Engine
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python3 $(pwd)/ultra_unzip_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "[+] Setup complete! Run: systemctl enable --now nova-unzip"
