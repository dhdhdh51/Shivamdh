# Game Server Load Bot

A Telegram-controlled, bounded UDP load simulator for testing a game server you own. It provides button-driven setup, a live countdown/status screen, real cancellation, and completion results.

## Safety model

- Only Telegram IDs in `ALLOWED_CHAT_IDS` can use the bot.
- Only exact targets in `TARGET_ALLOWLIST` can be tested.
- UDP traffic is capped at 200 packets/second for 120 seconds.
- One test may run at a time.
- Packets carry the recognizable marker `GAME_LOAD_TEST_V1`.

This is intended for controlled validation, not denial-of-service testing. Confirm your cloud provider's load-testing policy before running it.

## EC2 setup

Ubuntu 22.04/24.04 LTS with a free-tier micro instance is enough for the bot and bounded simulator.

```bash
git clone https://github.com/dhdhdh51/Shivamdh.git
cd Shivamdh
git checkout feature/telegram-load-tester
bash setup.sh
nano .env
.venv/bin/python bot.py
```

In `.env`, set:

```dotenv
TELEGRAM_BOT_TOKEN=token-from-BotFather
ALLOWED_CHAT_IDS=your-numeric-telegram-id
TARGET_ALLOWLIST=your-game-server-ip-or-hostname
```

Do not open inbound ports for this bot. Telegram polling only needs outbound HTTPS. The UDP destination port must be accepted by your game server.

## Telegram flow

1. Send `/start`.
2. Tap **Start UDP test**.
3. Send the allowlisted server IP/hostname.
4. Send the UDP port, desired PPS, and duration when prompted.
5. Tap **Run test** after reviewing the values.
6. Tap **Status** for elapsed/remaining time or **Stop** to cancel.

Commands: `/start`, `/status`, `/stop`, `/cancel`.
