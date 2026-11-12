# NEPSE Mentor Bot — Phase 1

Android-first Telegram bot starter. Phase 1 implements Telegram polling, onboarding, profile persistence in SQLite, `/profile`, `/help`, and `/health`.

## Termux setup

Install Termux from F-Droid or the official GitHub release. Then:

```bash
pkg update && pkg upgrade -y
pkg install python git clang make pkg-config libffi openssl -y
mkdir -p ~/nepse_mentor_bot
cd ~/nepse_mentor_bot
```

Extract the project ZIP into this directory, then:

```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Add the token from Telegram's official `@BotFather` to `TELEGRAM_BOT_TOKEN`. Keep `.env` private.

Run:

```bash
python main.py
```

Open your bot in Telegram and send `/start`.

## Commands in Phase 1

- `/start` — onboarding
- `/profile` — view saved profile
- `/help` — command list
- `/health` — process health

## Notes

- This phase does not fetch NEPSE prices and does not generate trade recommendations.
- No market data is fabricated. Provider integration comes in a later phase.
- SQLite database is created automatically at first startup.
- Keep Termux open while testing. Android battery optimization can stop background processes.
- For a long-running session, install Termux:Boot from the same trusted distribution if you later configure boot startup. Do not assume Android guarantees continuous execution.
- Back up `nepse.db` regularly.

## Security

Never share your Telegram bot token. If exposed, revoke it using BotFather and create a replacement.
