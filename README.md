# Game Server Load Bot

A private Telegram bot for bounded UDP simulation against a game server you own. It includes button-driven setup, live countdown/status, real cancellation, and completion results.

## Safety model

- Only Telegram IDs in `ALLOWED_CHAT_IDS` can use the bot.
- Only exact IPs/hostnames manually listed in `TARGET_ALLOWLIST` can be tested.
- UDP traffic is capped at 200 packets/second for 120 seconds.
- One test may run at a time.
- Packets carry the recognizable marker `GAME_LOAD_TEST_V1`.

This is for controlled validation, not denial-of-service testing. Confirm your cloud provider's load-testing policy before use.

## Automatic EC2 installation — four steps

Use Ubuntu Server 22.04/24.04 LTS. After connecting to the EC2 instance:

### 1. Install Git

```bash
sudo apt update && sudo apt install -y git
```

### 2. Clone the project branch

```bash
git clone --branch feature/telegram-load-tester --single-branch https://github.com/dhdhdh51/Shivamdh.git
```

### 3. Open the project directory

```bash
cd Shivamdh
```

### 4. Run the automatic installer

```bash
sudo bash install_ec2.sh
```

The installer automatically:

- installs Python and required Ubuntu packages;
- creates the virtual environment and installs dependencies;
- asks privately for the BotFather token;
- asks for allowed Telegram IDs and owned targets;
- creates the protected `.env` file;
- installs, enables, and starts the `game-load-bot` systemd service.

Enter multiple IDs or targets with commas and no spaces:

```text
Allowed IDs: 123456789,-100123456789
Owned targets: 203.0.113.10,game.example.com
```

`TARGET_ALLOWLIST` contains only IPs/hostnames—not ports. The game UDP port is entered in Telegram for each test. Telegram polling needs outbound HTTPS; no inbound bot port is required.

## Telegram flow

1. Send `/start`.
2. Tap **Start UDP test**.
3. Enter an IP/hostname configured during installation.
4. Enter the game UDP port, desired PPS, and duration.
5. Review the values and tap **Run test**.
6. Use **Status** for elapsed/remaining time or **Stop** to cancel.

Commands: `/start`, `/status`, `/stop`, `/cancel`.

## Service commands

```bash
sudo systemctl status game-load-bot
sudo journalctl -u game-load-bot -f
sudo systemctl restart game-load-bot
sudo systemctl stop game-load-bot
```

## Fix or update an existing installation

```bash
cd ~/Shivamdh
git pull origin feature/telegram-load-tester
bash setup.sh
sudo systemctl restart game-load-bot
sudo systemctl status game-load-bot --no-pager
```

This upgrades `python-telegram-bot` to the Python 3.13-compatible release pinned by the project. If startup still fails, inspect logs:

```bash
sudo journalctl -u game-load-bot -n 50 --no-pager
```

To change allowed users or targets later:

```bash
cd ~/Shivamdh
nano .env
sudo systemctl restart game-load-bot
```
