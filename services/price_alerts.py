import logging

from database.db import (
    get_all_active_stock_price_alerts,
    trigger_stock_price_alert,
)
from services.nepse_data import fetch_market_data

logger = logging.getLogger(__name__)


async def check_price_alerts_job(context) -> None:
    """Check active alerts against fresh market-feed prices."""
    try:
        stocks = await fetch_market_data()

        fresh_prices = {
            stock["symbol"]: stock
            for stock in stocks
            if not stock.get("is_stale", True)
        }

        alerts = await get_all_active_stock_price_alerts()

        for alert in alerts:
            stock = fresh_prices.get(alert["symbol"])

            if stock is None:
                continue

            current_price = float(stock["ltp"])
            target_price = float(alert["target_price"])

            triggered = (
                alert["condition"] == "above"
                and current_price >= target_price
            ) or (
                alert["condition"] == "below"
                and current_price <= target_price
            )

            if not triggered:
                continue

            message = (
                f"🔔 STOCK PRICE ALERT\n\n"
                f"Stock: {alert['symbol']}\n"
                f"Current LTP: NPR {current_price:,.2f}\n"
                f"Condition: {alert['condition'].upper()}\n"
                f"Target: NPR {target_price:,.2f}\n\n"
                "Your price target has been reached.\n"
                "Data source: YONEPSE community feed, "
                "not a verified live exchange quote."
            )

            try:
                await context.bot.send_message(
                    chat_id=alert["telegram_id"],
                    text=message,
                )
            except Exception:
                logger.exception(
                    "Failed to send price alert %s to user %s",
                    alert["id"],
                    alert["telegram_id"],
                )

                continue

            updated = await trigger_stock_price_alert(alert["id"])

            if not updated:
                logger.warning(
                    "Alert %s was delivered but could not be marked triggered",
                    alert["id"],
                )

    except Exception:
        logger.exception("Price alert checker failed")
