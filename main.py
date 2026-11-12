
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import settings
from database.db import init_db
from services.price_alerts import check_price_alerts_job
from bot.handlers import (
    start,
    profile,
    help_command,
    health,
    stock_command,
    history_command,
    chart_command,
    indicators_command,
    compare_command,
    addstock_command,
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


async def post_init(application):
    await init_db()


def build_application():
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )

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
    app.add_handler(CommandHandler("compare", compare_command))
    app.add_handler(CommandHandler("addstock", addstock_command))
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
