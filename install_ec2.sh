#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with: sudo bash install_ec2.sh" >&2
  exit 1
fi

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-ubuntu}"
SERVICE_NAME="game-load-bot"

if ! id "$APP_USER" >/dev/null 2>&1; then
  echo "Unable to find deployment user: $APP_USER" >&2
  exit 1
fi

if [[ ! -f "$APP_DIR/bot.py" || ! -f "$APP_DIR/setup.sh" ]]; then
  echo "Run this script from the cloned Shivamdh repository." >&2
  exit 1
fi

echo "[1/4] Installing Ubuntu packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-pip python3-venv

echo "[2/4] Creating the Python environment..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
sudo -u "$APP_USER" -H bash "$APP_DIR/setup.sh"

echo "[3/4] Configuring the private Telegram bot..."
read -rsp "Telegram BotFather token: " BOT_TOKEN
echo
read -rp "Allowed numeric Telegram ID (multiple: comma-separated): " CHAT_IDS
read -rp "Owned game-server IP/hostname (multiple: comma-separated): " TARGETS

if [[ ! "$BOT_TOKEN" =~ ^[0-9]+:.+ ]]; then
  echo "Invalid Telegram bot token format." >&2
  exit 1
fi
if [[ ! "$CHAT_IDS" =~ ^-?[0-9]+(,-?[0-9]+)*$ ]]; then
  echo "Telegram IDs must be numeric and comma-separated without spaces." >&2
  exit 1
fi
if [[ ! "$TARGETS" =~ ^[A-Za-z0-9.-]+(,[A-Za-z0-9.-]+)*$ ]]; then
  echo "Targets must be IPv4 addresses/hostnames, comma-separated without spaces." >&2
  exit 1
fi

ENV_FILE="$APP_DIR/.env"
install -o "$APP_USER" -g "$APP_USER" -m 600 /dev/null "$ENV_FILE"
printf 'TELEGRAM_BOT_TOKEN=%s\nALLOWED_CHAT_IDS=%s\nTARGET_ALLOWLIST=%s\n' \
  "$BOT_TOKEN" "$CHAT_IDS" "$TARGETS" > "$ENV_FILE"
chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset BOT_TOKEN

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Private Telegram Game Server Load Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/bot.py
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

echo "[4/4] Starting the bot service..."
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
sleep 2

if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Bot failed to start. Recent logs:" >&2
  journalctl -u "$SERVICE_NAME" -n 20 --no-pager >&2
  exit 1
fi

echo
echo "Installation complete. The bot is running."
echo "Open Telegram and send /start."
echo "Status: sudo systemctl status $SERVICE_NAME"
echo "Logs:   sudo journalctl -u $SERVICE_NAME -f"
