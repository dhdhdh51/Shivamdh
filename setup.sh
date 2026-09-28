#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

command -v python3 >/dev/null || {
  echo "Python 3 is required. On Ubuntu: sudo apt install python3 python3-venv" >&2
  exit 1
}

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

python3 <<'PY'
from pathlib import Path
import secrets

path = Path('.env')
lines = path.read_text().splitlines()
values = {
    line.split('=', 1)[0]: line.split('=', 1)[1]
    for line in lines
    if '=' in line and not line.lstrip().startswith('#')
}
secret = values.get('VERIFICATION_SECRET', '')
if len(secret) < 32 or secret == 'replace-with-a-long-random-secret':
    generated = secrets.token_urlsafe(32)
    for index, line in enumerate(lines):
        if line.startswith('VERIFICATION_SECRET='):
            lines[index] = f'VERIFICATION_SECRET={generated}'
            break
    else:
        lines.extend(['', f'VERIFICATION_SECRET={generated}'])
if not any(line.startswith('VERIFIER_PORT=') for line in lines):
    lines.append('VERIFIER_PORT=39001')
path.write_text('\n'.join(lines) + '\n')
PY

chmod 600 .env
echo "Environment ready. Add your bot token and Telegram ID; copy the verification secret to each game server."
echo "Setup complete. Run the bot: .venv/bin/python bot.py"
