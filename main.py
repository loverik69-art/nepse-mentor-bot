import asyncio

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import settings
from database.db import init_db
from database.backup import create_database_backup, prune_database_backups
from services.price_alerts import check_price_alerts_job
from bot.handlers import (
    start,
    profile,
    help_command,
    ask_mentor,
    health,
    stock_command,
    history_command,
    chart_command,
    indicators_command,
    signal_command,
    tradeplan_command,
    backtest_command,
    compare_command,
    fundamentals_command,
    watchlist_command,
    watchadd_command,
    watchremove_command,
    addstock_command,
    buy_command,
    sell_command,
    transactions_command,
    portfolio_command,
    removestock_command,
    allocation_command,
    diversification_command,
    performance_command,
    alert_command,
    alerts_command,
    removealert_command,
    gainers_command,
    losers_command,
    data_status_command,
    cancel,
    save_experience,
    save_style,
    save_capital,
    save_risk,
    save_max_risk,
    EXPERIENCE,
    STYLE,
    CAPITAL,
    RISK,
    MAX_RISK,
)



BOT_COMMANDS = [
    BotCommand("start", "Start the bot and set up your profile"),
    BotCommand("cancel", "Cancel the current setup"),
    BotCommand("profile", "View your investor profile"),
    BotCommand("help", "View available commands"),
    BotCommand("health", "Check bot and database health"),
    BotCommand("stock", "Analyze a NEPSE stock"),
    BotCommand("gainers", "View top gaining stocks"),
    BotCommand("losers", "View top losing stocks"),
    BotCommand("data_status", "Check market data freshness"),
    BotCommand("history", "View historical stock prices"),
    BotCommand("chart", "Generate a stock chart"),
    BotCommand("indicators", "View technical indicators"),
    BotCommand("signal", "View technical trading signals"),
    BotCommand("tradeplan", "Generate a trading plan"),
    BotCommand("backtest", "Backtest a trading strategy"),
    BotCommand("compare", "Compare stocks"),
    BotCommand("fundamentals", "View fundamental analysis"),
    BotCommand("ask", "Ask your NEPSE mentor"),
    BotCommand("watchlist", "View your watchlist"),
    BotCommand("watchadd", "Add a stock to your watchlist"),
    BotCommand("watchremove", "Remove a stock from your watchlist"),
    BotCommand("addstock", "Add a portfolio holding"),
    BotCommand("buy", "Record a stock purchase"),
    BotCommand("sell", "Record a stock sale"),
    BotCommand("transactions", "View transaction history"),
    BotCommand("portfolio", "View your portfolio"),
    BotCommand("removestock", "Remove a portfolio holding"),
    BotCommand("allocation", "View portfolio allocation"),
    BotCommand("diversification", "Check portfolio diversification"),
    BotCommand("performance", "View portfolio performance"),
    BotCommand("alert", "Create a price alert"),
    BotCommand("alerts", "View your price alerts"),
    BotCommand("removealert", "Remove a price alert"),
]


def configure_logging():
    Path("logs").mkdir(exist_ok=True)

    handler = RotatingFileHandler(
        "logs/bot.log",
        maxBytes=1_000_000,
        backupCount=3,
    )

    logging.basicConfig(
        level=getattr(
            logging,
            settings.log_level.upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


async def automatic_database_backup(context):
    logger = logging.getLogger(__name__)
    backup_dir = Path("backups/automatic")

    try:
        backup_path = await asyncio.to_thread(
            create_database_backup,
            settings.database_path,
            backup_dir,
        )
        removed = await asyncio.to_thread(
            prune_database_backups,
            backup_dir,
            7,
        )
        logger.info(
            "Automatic database backup created: %s; "
            "old backups removed: %d",
            backup_path,
            len(removed),
        )
    except Exception:
        logger.exception("Automatic database backup failed")


async def global_error_handler(update, context):
    """Log unexpected errors raised while processing Telegram updates."""
    logger = logging.getLogger(__name__)
    error = context.error

    if error is None:
        logger.error("Unhandled Telegram update error without exception details")
        return

    logger.error(
        "Unhandled exception while processing a Telegram update",
        exc_info=(type(error), error, error.__traceback__),
    )


async def post_init(application):
    await init_db()

    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
        logging.getLogger(__name__).info(
            "Telegram command menu synchronized: %d commands",
            len(BOT_COMMANDS),
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to synchronize Telegram command menu"
        )


def build_application():
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(global_error_handler)

    onboarding = ConversationHandler(
        entry_points=[
            CommandHandler("start", start)
        ],
        states={
            EXPERIENCE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_experience,
                )
            ],
            STYLE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_style,
                )
            ],
            CAPITAL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_capital,
                )
            ],
            RISK: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_risk,
                )
            ],
            MAX_RISK: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_max_risk,
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True,
    )

    app.add_handler(onboarding)
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("stock", stock_command))
    app.add_handler(CommandHandler("gainers", gainers_command))
    app.add_handler(CommandHandler("losers", losers_command))
    app.add_handler(CommandHandler("data_status", data_status_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("chart", chart_command))
    app.add_handler(CommandHandler("indicators", indicators_command))
    app.add_handler(CommandHandler("signal", signal_command))
    app.add_handler(CommandHandler("tradeplan", tradeplan_command))
    app.add_handler(CommandHandler("backtest", backtest_command))
    app.add_handler(CommandHandler("compare", compare_command))
    app.add_handler(CommandHandler("fundamentals", fundamentals_command))
    app.add_handler(CommandHandler("ask", ask_mentor))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("watchadd", watchadd_command))
    app.add_handler(CommandHandler("watchremove", watchremove_command))
    app.add_handler(CommandHandler("addstock", addstock_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("sell", sell_command))
    app.add_handler(CommandHandler("transactions", transactions_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))
    app.add_handler(CommandHandler("removestock", removestock_command))
    app.add_handler(CommandHandler("allocation", allocation_command))
    app.add_handler(CommandHandler("diversification", diversification_command))
    app.add_handler(CommandHandler("performance", performance_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("alerts", alerts_command))
    app.add_handler(CommandHandler("removealert", removealert_command))

    if app.job_queue is None:
        raise RuntimeError("Telegram JobQueue is unavailable")
    app.job_queue.run_repeating(
        check_price_alerts_job,
        interval=300,
        first=30,
        name="price-alert-checker",
    )
    app.job_queue.run_repeating(
        automatic_database_backup,
        interval=24 * 60 * 60,
        first=60,
        name="automatic-database-backup",
    )
    return app


def main():
    configure_logging()

    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not settings.telegram_bot_token:
        raise SystemExit(
            "Missing TELEGRAM_BOT_TOKEN. "
            "Copy .env.example to .env and add your BotFather token."
        )

    app = build_application()

    logging.info("Starting NEPSE Mentor Bot in polling mode")

    app.run_polling(
        allowed_updates=["message", "callback_query"]
    )


if __name__ == "__main__":
    main()
