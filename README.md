# Game Server Load Bot

A private Telegram bot for bounded UDP load simulation against game servers you control. It provides button-driven target setup, live countdown/status, real cancellation, and completion results.

## Safety model

- Only Telegram IDs in `ALLOWED_CHAT_IDS` can operate the bot.
- New servers must prove control using `verifier_agent.py` and a shared secret.
- Optional static servers may be listed in `TARGET_ALLOWLIST`.
- Traffic is capped at 200 packets/second for 120 seconds.
- Only one test can run at a time.
- Packets contain the recognizable marker `GAME_LOAD_TEST_V1`.

This is intended for controlled validation, not denial-of-service testing. Confirm your cloud provider's load-testing policy before use.

## 1. Install the Telegram bot on EC2

Ubuntu 22.04/24.04 LTS with a free-tier micro instance is sufficient.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
git clone --branch feature/telegram-load-tester --single-branch https://github.com/dhdhdh51/Shivamdh.git
cd Shivamdh
bash setup.sh
nano .env
```

Set your bot token and numeric Telegram ID. `setup.sh` generates the verification secret automatically:

```dotenv
TELEGRAM_BOT_TOKEN=token-from-BotFather
ALLOWED_CHAT_IDS=your-numeric-telegram-id
TARGET_ALLOWLIST=
VERIFICATION_SECRET=generated-secret
VERIFIER_PORT=39001
```

Start the bot:

```bash
.venv/bin/python bot.py
```

Telegram polling needs only outbound HTTPS; do not expose an inbound web port for the bot.

## 2. Install the verifier on your game server

Clone the same branch and run setup on the game server:

```bash
git clone --branch feature/telegram-load-tester --single-branch https://github.com/dhdhdh51/Shivamdh.git
cd Shivamdh
bash setup.sh
nano .env
```

Copy the exact `VERIFICATION_SECRET` from the bot server's `.env` into this server's `.env`, then start:

```bash
.venv/bin/python verifier_agent.py
```

Allow inbound UDP port `39001` on the game server **only from the bot EC2 instance's public IP**. The game UDP port must also accept traffic from the bot server.

## 3. Telegram flow

1. Send `/start`.
2. Tap **Add server** and enter its IP/hostname.
3. The verifier proves control; the bot stores the server locally.
4. Tap **Start UDP test**.
5. Enter the verified server, game UDP port, desired PPS, and duration.
6. Review the values and tap **Run test**.
7. Use **Status** for elapsed/remaining time or **Stop** to cancel.

Buttons are available only to configured Telegram operators. Commands: `/start`, `/targets`, `/status`, `/stop`, `/cancel`.

## Update an existing EC2 checkout

```bash
cd ~/Shivamdh
git pull origin feature/telegram-load-tester
bash setup.sh
sudo systemctl restart game-load-bot 2>/dev/null || true
```
