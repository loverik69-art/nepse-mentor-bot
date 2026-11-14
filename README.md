# NEPSE Mentor Bot

An Android/Termux-friendly Telegram bot for NEPSE stock research, technical and fundamental analysis, trading education, and portfolio tracking.

## Features

### Market research
- Stock information and historical prices
- Technical indicators and charts
- Top gainers and losers
- Stock comparison
- Company financial reports and fundamental analysis

### Trading research
- Technical trading signals
- Risk-aware trade plans
- Historical backtesting
- Rule-based NEPSE stock mentor using `/ask`

### Portfolio management
- Portfolio holdings and allocation
- Buy and sell transaction records
- Automatic NEPSE transaction-fee calculations
- Transaction history and performance
- Diversification analysis

### Watchlist and alerts
- Add, view, and remove watchlist stocks
- Above-price and below-price alerts

### Reliability
- SQLite database storage
- Automatic daily database backups
- Backup integrity verification
- Telegram error logging
- Market-data health and freshness checks

## Telegram commands

### Market analysis
- `/stock SYMBOL` — stock information
- `/history SYMBOL` — historical prices
- `/indicators SYMBOL` — technical indicators
- `/gainers` and `/losers` — market leaders
- `/chart SYMBOL [LIMIT]` — technical chart
- `/compare SYMBOL1 SYMBOL2` — stock comparison
- `/fundamentals SYMBOL` — company financial analysis
- `/ask QUESTION` — ask the NEPSE stock mentor

### Trading research
- `/signal SYMBOL` — technical signal
- `/tradeplan SYMBOL` — risk-aware trade plan
- `/backtest SYMBOL` — historical backtesting

### Portfolio management
- `/addstock` — add a portfolio holding
- `/buy SYMBOL QUANTITY PRICE` — record a purchase
- `/sell SYMBOL QUANTITY PRICE` — record a sale
- `/transactions [LIMIT]` — transaction history
- `/portfolio` — view portfolio
- `/removestock SYMBOL` — remove a holding
- `/allocation` — portfolio allocation
- `/diversification` — concentration analysis
- `/performance` — portfolio performance

### Watchlist and alerts
- `/watchadd SYMBOL` — add a stock
- `/watchlist` — view saved stocks
- `/watchremove SYMBOL` — remove a stock
- `/alert SYMBOL above|below PRICE` — create a price alert
- `/alerts` — view active alerts
- `/removealert ID` — remove an alert

### System commands
- `/start` — start the bot
- `/profile` — view your profile
- `/health` — check bot health
- `/data_status` — check market-data freshness
- `/help` — show available commands

## Installation on Termux

1. Install Python and Git:
   `pkg install python git`

2. Clone the repository:
   `git clone https://github.com/loverik69-art/nepse-mentor-bot.git`

3. Enter the project directory:
   `cd nepse-mentor-bot`

4. Create and activate a virtual environment:
   `python -m venv venv`
   `source venv/bin/activate`

5. Install dependencies:
   `pip install -r requirements.txt`

6. Create your environment file:
   `cp .env.example .env`

7. Edit `.env` using a text editor and add your Telegram bot token from BotFather.

8. Start the bot:
   `python main.py`

## Environment variables

Configure these values in `.env`:

- `TELEGRAM_BOT_TOKEN` — Telegram bot token (required)
- `ADMIN_CHAT_ID` — optional administrator chat ID
- `DATABASE_PATH` — SQLite database path (default: `nepse.db`)
- `LOG_LEVEL` — logging level (default: `INFO`)
- `DATA_CACHE_SECONDS` — market-data cache duration
- `MAX_RISK_DEFAULT` — default risk setting

## Market-data notes

- Market data is retrieved from the YONEPSE community data feed.
- Historical data is used for technical indicators and backtesting.
- Feed availability and freshness can vary.
- Use `/data_status` to check whether market data is fresh or stale.
- Prices are not guaranteed to be live exchange quotes.
- Verify important prices independently before making trading decisions.

## Database and backups

- Portfolio and profile information is stored in SQLite.
- Automatic database backups are scheduled daily.
- Backups are integrity-checked.
- Automatic backups are retained in `backups/automatic/`.
- Application logs are stored in `logs/bot.log`.

## Testing

Run the complete test suite:

`python -m pytest -q`

Check Python syntax:

`python -m py_compile main.py`

## Security

- Never commit `.env` or expose your Telegram bot token.
- Keep database backups private.
- Do not share portfolio database files publicly.
- Keep dependencies updated.

## Disclaimer

Educational analysis only — not financial advice. NEPSE is volatile; trade at your own risk. Market-feed prices may not be verified live exchange quotes.

## Android runtime notes

- Keep Termux running while the bot is operating.
- Android battery optimization may stop background processes.
- Configure Termux battery settings appropriately for longer-running sessions.
- Android does not guarantee uninterrupted bot operation.
