from zoneinfo import ZoneInfo
from datetime import datetime

import logging
import math

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database.db import (
    save_profile,
    get_profile,
    check_db,
    get_price_history,
    add_portfolio_holding,
    get_portfolio,
    remove_portfolio_holding,
    save_portfolio_daily_snapshot,
    get_portfolio_daily_snapshots,
    record_portfolio_transaction,
    get_portfolio_transactions,
    add_stock_price_alert,
    get_stock_price_alerts,
    remove_stock_price_alert,
)

from services.technical_analysis import get_technical_analysis
from services.signals import get_stock_signal
from services.backtesting import backtest_symbol
from services.chart_generator import generate_price_chart
from services.fundamental_data import (
    FundamentalDataError,
    get_company_financials,
)
from services.fundamental_analysis import (
    analyze_company_reports,
    calculate_pb_ratio,
)


EXPERIENCE, STYLE, CAPITAL, RISK, MAX_RISK = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["profile"] = {}
    await update.message.reply_text(
        "Welcome to NEPSE Mentor Bot 📊\n\n"
        "I'll help you build a risk-aware NEPSE research profile.\n"
        "First, choose your experience level: Beginner, Intermediate, or Advanced."
    )
    return EXPERIENCE

async def save_experience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip().title()
    if value not in {"Beginner", "Intermediate", "Advanced"}:
        await update.message.reply_text("Please enter Beginner, Intermediate, or Advanced.")
        return EXPERIENCE
    context.user_data["profile"]["experience"] = value
    await update.message.reply_text("Trading style? Enter Swing, Positional, or Long-term.")
    return STYLE

async def save_style(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip().title()
    if value not in {"Swing", "Positional", "Long-Term"}:
        await update.message.reply_text("Please enter Swing, Positional, or Long-term.")
        return STYLE
    context.user_data["profile"]["trading_style"] = value
    await update.message.reply_text("What is your trading capital in NPR? Enter a number, e.g. 200000.")
    return CAPITAL

async def save_capital(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = float(update.message.text.replace(",", "").strip())
        if value < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Enter a valid non-negative NPR amount, e.g. 200000.")
        return CAPITAL
    context.user_data["profile"]["capital_npr"] = value
    await update.message.reply_text("Risk tolerance? Enter Low, Medium, or High.")
    return RISK

async def save_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip().title()
    if value not in {"Low", "Medium", "High"}:
        await update.message.reply_text("Please enter Low, Medium, or High.")
        return RISK
    context.user_data["profile"]["risk_tolerance"] = value
    await update.message.reply_text("Maximum risk per trade in percent? Enter 0.5, 1, or 1.5 (maximum 5).")
    return MAX_RISK

async def save_max_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        value = float(update.message.text.strip().replace("%", ""))
        if not 0 < value <= 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Enter a number greater than 0 and no more than 5.")
        return MAX_RISK

    profile = context.user_data["profile"]
    profile["max_risk_pct"] = value
    user = update.effective_user
    await save_profile(user.id, user.username, profile)
    context.user_data.pop("profile", None)
    await update.message.reply_text(
        "✅ Your profile has been saved.\n\n"
        f"Experience: {profile['experience']}\n"
        f"Style: {profile['trading_style']}\n"
        f"Capital: NPR {profile['capital_npr']:,.2f}\n"
        f"Risk tolerance: {profile['risk_tolerance']}\n"
        f"Max risk/trade: {value:g}%\n\n"
        "Next: /profile to view it, /help for commands.\n"
        "Market analysis commands will be added in the next build phase."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("profile", None)
    await update.message.reply_text("Onboarding cancelled. Send /start when you're ready.")
    return ConversationHandler.END

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await get_profile(update.effective_user.id)
    if not data:
        await update.message.reply_text("No profile saved yet. Send /start to set it up.")
        return
    await update.message.reply_text(
        "👤 Your NEPSE Mentor profile\n"
        f"Experience: {data['experience']}\n"
        f"Trading style: {data['trading_style']}\n"
        f"Capital: NPR {data['capital_npr']:,.2f}\n"
        f"Risk tolerance: {data['risk_tolerance']}\n"
        f"Maximum risk per trade: {data['max_risk_pct']:g}%"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📊 NEPSE Mentor Bot — Commands\n\n"
        "👤 PROFILE\n"
        "/start — create or update your profile\n"
        "/profile — view saved profile\n\n"
        "📈 MARKET ANALYSIS\n"
        "/stock SYMBOL — stock information\n"
        "/history SYMBOL — historical prices\n"
        "/indicators SYMBOL — technical indicators\n"
        "/gainers — top gaining stocks\n"
        "/losers — top losing stocks\n"
        "/chart SYMBOL [LIMIT] — technical chart\n"
        "/compare SYMBOL1 SYMBOL2 — compare stocks\n"
        "/fundamentals SYMBOL — financial reports and ratios\n\n"
        "🎯 TRADING SIGNALS & BACKTESTING\n"
        "/signal SYMBOL — current technical trading signal\n"
        "/backtest SYMBOL — historical signal performance\n\n"
        "💼 PORTFOLIO\n"
        "/addstock — add a portfolio holding\n"
        "/buy SYMBOL QUANTITY PRICE — record a purchase\n"
        "/sell SYMBOL QUANTITY PRICE — record a sale\n"
        "/transactions [LIMIT] — view transaction history\n"
        "/portfolio — view your portfolio\n"
        "/removestock SYMBOL — remove a holding\n"
        "/allocation — view portfolio allocation\n"
        "/diversification — check portfolio concentration\n"
        "/performance — track portfolio performance\n\n"
        "🔔 PRICE ALERTS\n"
        "/alert SYMBOL above|below PRICE — create an alert\n"
        "/alerts — view active alerts\n"
        "/removealert ID — cancel an alert\n\n"
        "🛠️ SYSTEM\n"
        "/health — check bot status\n"
        "/data_status — check market-data freshness\n"
        "/help — show available commands\n\n"
        "⚠️ Educational research only, not financial advice. "
        "Market-feed prices are not verified live exchange quotes."
    )

async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["🏥 NEPSE Mentor System Health", ""]

    # Telegram process
    lines.append("✅ Telegram bot: Responding")

    # SQLite database
    try:
        db_ok = await check_db()

        if db_ok:
            lines.append("✅ SQLite database: Connected")
        else:
            lines.append("❌ SQLite database: Failed")

    except Exception:
        logging.exception("Database health check failed")
        lines.append("❌ SQLite database: Error")

    # NEPSE market-data provider
    try:
        stocks = await fetch_market_data()
        fresh_count = sum(1 for stock in stocks if not stock["is_stale"])
        stale_count = len(stocks) - fresh_count
        stale_percentage = stale_count / len(stocks) * 100
        fresh_count = sum(1 for stock in stocks if not stock["is_stale"])
        stale_count = len(stocks) - fresh_count
        stale_percentage = stale_count / len(stocks) * 100

        newest = min(
            stocks,
            key=lambda stock: stock["age_minutes"],
        )

        age = newest["age_minutes"]
        timestamp = newest["last_updated"]
        source = newest["source"]

        lines.append("")

        if newest["is_stale"]:
            lines.append("⚠️ NEPSE feed: Reachable, but stale")
        else:
            lines.append("✅ NEPSE feed: Reachable and fresh")

        lines.append(f"📊 Valid stock records: {len(stocks)}")
        lines.append(f"🕒 Newest update: {timestamp}")
        lines.append(f"⌛ Data age: {age} minutes")
        lines.append(f"📡 Source: {source}")
        lines.append(f"Fresh stock records: {fresh_count}")
        lines.append(f"Stale stock records: {stale_count}")
        lines.append(f"Stale data percentage: {stale_percentage:.1f}%")
   
    except MarketDataError as exc:
        logging.warning("NEPSE feed health check failed: %s", exc)
        lines.append("")
        lines.append("❌ NEPSE feed: Unavailable or invalid")
        lines.append(f"Reason: {exc}")

    except Exception:
        logging.exception("Unexpected NEPSE feed health error")
        lines.append("")
        lines.append("❌ NEPSE feed: Error")

    lines.append("")
    lines.append(
        "⚠️ Educational analysis only — not financial advice. "
        "NEPSE is volatile; trade at your own risk."
    )

    await update.message.reply_text("\n".join(lines))
from services.nepse_data import (
    get_stock,
    get_market_movers,
    fetch_market_data,
    MarketDataError,
)

async def stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    disclaimer = (
        "\n\n⚠️ Educational analysis only — not financial advice. "
        "NEPSE is volatile; trade at your own risk."
    )

    if not context.args:
        await update.message.reply_text(
            "Usage: /stock SYMBOL\nExample: /stock NABIL" + disclaimer
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Please use a valid symbol, e.g. NABIL."
            + disclaimer
        )
        return

    try:
        stock = await get_stock(symbol)

    except MarketDataError as exc:
        await update.message.reply_text(
            f"⚠️ Market data unavailable: {exc}\n"
            "Please try again later."
            + disclaimer
        )
        return

    except Exception:
        logging.exception("Unexpected error retrieving stock %s", symbol)
        await update.message.reply_text(
            "⚠️ Something went wrong while retrieving stock data."
            + disclaimer
        )
        return

    if stock is None:
        await update.message.reply_text(
            f"Stock symbol {symbol} was not found in the data feed."
            + disclaimer
        )
        return
    if stock is None:
        await update.message.reply_text(
            f"Stock symbol {symbol} was not found in the data feed." + disclaimer
        )
        return

    def show(value, suffix=""):
        if value is None:
            return "N/A"
        try:
            number = float(value)
            if not math.isfinite(number):
                return "N/A"
            return f"{number:,.2f}{suffix}"
        except (TypeError, ValueError):
            return "N/A"

    status = (
        "⚠️ STALE DATA — do not treat this as a current market quote."
        if stock["is_stale"]
        else "✅ Data is within the 24-hour freshness threshold."
    )

    message = (
        f"📊 {stock['name']} ({stock['symbol']})\n\n"
	f"{status}\n\n"
        f"Last traded price: NPR {show(stock['ltp'])}\n"
        f"Previous close: NPR {show(stock['previous_close'])}\n"
        f"Change: NPR {show(stock['change'])}\n"
        f"Change %: {show(stock['percent_change'], '%')}\n"
        f"High: NPR {show(stock['high'])}\n"
        f"Low: NPR {show(stock['low'])}\n"
        f"Volume: {show(stock['volume'])}\n"
        f"Turnover: NPR {show(stock['turnover'])}\n"
        f"Trades: {show(stock.get('trades'))}\n\n"
        f"Last updated: {stock['last_updated']}\n"
        f"Data age: {stock['age_minutes']} minutes\n"
        f"Source: {stock['source']}\n\n"
        "⚠️ Educational analysis only — not financial advice. "
        "NEPSE is volatile; trade at your own risk."
    )

    await update.message.reply_text(message)


async def market_movers_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    direction: str,
) -> None:
    disclaimer = (
        "\n\n⚠️ Educational analysis only — not financial advice. "
        "NEPSE is volatile; trade at your own risk."
    )

    title = "📈 TOP GAINERS" if direction == "gainers" else "📉 TOP LOSERS"

    try:
        stocks = await get_market_movers(direction, limit=10)

    except MarketDataError as exc:
        await update.message.reply_text(
            f"⚠️ Market data unavailable: {exc}\n"
            "Please try again later."
            + disclaimer
        )
        return

    except Exception:
        logging.exception("Failed to retrieve %s", direction)
        await update.message.reply_text(
            "⚠️ Something went wrong retrieving market movers."
            + disclaimer
        )
        return

    if not stocks:
        await update.message.reply_text(
            f"No {direction} found in the available market data."
            + disclaimer
        )
        return


    lines = [title]

    if any(stock["is_stale"] for stock in stocks):
        lines.append(
            "⚠️ STALE DATA: These may not represent today's market movers."
        )

    lines.extend([
        "Source: YONEPSE community data feed",
        "",
    ])

    for index, stock in enumerate(stocks, start=1):
        status = " ⚠️ STALE" if stock["is_stale"] else ""

        age_minutes = stock["age_minutes"]
        age_hours = int(age_minutes // 60)
        age_days, remaining_hours = divmod(age_hours, 24)

        if age_days:
            age_label = f"{age_days}d {remaining_hours}h"
        elif age_hours:
            age_label = f"{age_hours}h {int(age_minutes % 60)}m"
        else:
            age_label = f"{int(age_minutes)}m"

        lines.append(
            f"{index}. {stock['symbol']}\n"
            f"   Price: NPR {stock['ltp']:,.2f}\n"
            f"   Change: {stock['percent_change']:+.2f}%\n"
            f"   Updated: {stock['last_updated']}\n"
            f"   Data age: {age_label}{status}"
        )

    await update.message.reply_text(
        "\n".join(lines) + disclaimer
    )

async def gainers_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await market_movers_command(update, context, "gainers")

async def losers_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await market_movers_command(update, context, "losers")

async def data_status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        stocks = await fetch_market_data()

        fresh_count = sum(1 for stock in stocks if not stock['is_stale'])
        stale_count = len(stocks) - fresh_count
        stale_percentage = stale_count / len(stocks) * 100

        newest = min(
            stocks,
            key=lambda stock: stock["age_minutes"],
        )

        age = newest["age_minutes"]
        hours = age // 60
        minutes = age % 60

        if newest["is_stale"]:
            status = "⚠️ STALE"
            recommendation = (
                "Do not treat these prices as live. "
                "Wait for refreshed market data."
            )
        else:
            status = "✅ FRESH"
            recommendation = (
                "Data is within the 24-hour freshness threshold. "
                "Verify the timestamp before making decisions."
            )

        message = (
            "📡 NEPSE Market Data Status\n\n"
            f"Provider: {newest['source']}\n"
            f"Status: {status}\n\n"
            f"Valid stock records: {len(stocks)}\n"
            f"Fresh stock records: {fresh_count}\n"
	    f"Stale stock records: {stale_count}\n"
	    f"Stale data percentage: {stale_percentage:.1f}%\n"
	    f"Newest update: {newest['last_updated']}\n"
            f"Data age: {hours} hours, {minutes} minutes\n\n"
            f"Recommendation:\n{recommendation}\n\n"
            "⚠️ Educational analysis only — not financial advice. "
            "NEPSE is volatile; trade at your own risk."
        )

    except MarketDataError as exc:
        logging.warning("Data status check failed: %s", exc)
        message = (
            "📡 NEPSE Market Data Status\n\n"
            "❌ Provider: Unavailable or invalid data\n"
            f"Reason: {exc}\n\n"
            "Do not rely on unverified market prices.\n\n"
            "⚠️ Educational analysis only — not financial advice. "
            "NEPSE is volatile; trade at your own risk."
        )

    except Exception:
        logging.exception("Unexpected data status error")
        message = (
            "📡 NEPSE Market Data Status\n\n"
            "❌ Unable to check the market-data provider.\n\n"
            "⚠️ Educational analysis only — not financial advice. "
            "NEPSE is volatile; trade at your own risk."
        )
    await update.message.reply_text(message)

async def history_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    disclaimer = (
        "\n\n⚠️ Historical prices are for educational research only, "
        "not financial advice."
    )

    if not context.args:
        await update.message.reply_text(
            "Usage: /history SYMBOL [LIMIT]\n"
            "Examples: /history NABIL\n"
            "/history NABIL 30\n"
            "/history NABIL 100"
            + disclaimer
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Please use a valid symbol, e.g. NABIL."
            + disclaimer
        )
        return

    limit = 10

    if len(context.args) > 2:
        await update.message.reply_text(
            "Usage: /history SYMBOL [LIMIT]" + disclaimer
        )
        return

    if len(context.args) == 2:
        try:
            limit = int(context.args[1])
        except ValueError:
            await update.message.reply_text(
                "Limit must be a whole number. Example: /history NABIL 30"
                + disclaimer
            )
            return

        if limit < 1 or limit > 100:
            await update.message.reply_text(
                "Limit must be between 1 and 100."
                + disclaimer
            )
            return

    try:
        records = await get_price_history(symbol, limit=limit)

    except Exception:
        logging.exception(
            "Failed to retrieve price history for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Unable to retrieve historical prices right now."
            + disclaimer
        )
        return

    if not records:
        await update.message.reply_text(
            f"No historical data found for {symbol} yet.\n"
            "Fresh price snapshots will appear here once collected."
            + disclaimer
        )
        return

    lines = [
        f"📈 Historical Prices — {symbol}",
        "",
        f"Showing {len(records)} most recent stored records:",
        "",
    ]

    for record in records:
        ltp = record.get("ltp")
        try:
            price = float(ltp)
            price_text = (
                f"{price:,.2f}"
                if math.isfinite(price)
                else "N/A"
            )
        except (TypeError, ValueError):
            price_text = "N/A"

        lines.append(
            f"📅 {record.get('source_updated_at', 'Unknown date')}\n"
            f"Price: NPR {price_text}"
        )

        for field, label in (
            ("volume", "Volume"),
            ("turnover", "Turnover"),
        ):
            value = record.get(field)
            if value is not None:
                try:
                    number = float(value)
                    if math.isfinite(number):
                        lines.append(f"{label}: {number:,.2f}")
                except (TypeError, ValueError):
                    pass

        lines.append("")

    lines.append(
        "⚠️ Historical data is not a live quote."
        + disclaimer
    )

    message = "\n".join(lines)

    for offset in range(0, len(message), 4000):
        await update.message.reply_text(message[offset:offset + 4000])


async def chart_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not context.args or len(context.args) > 2:
        await update.message.reply_text(
            "Usage: /chart SYMBOL [LIMIT]\n"
            "Examples:\n"
            "/chart NABIL\n"
            "/chart NABIL 60\n"
            "/chart NABIL 90\n"
            "/chart NABIL 180\n"
            "Limit: 1-250 observations."
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Example: /chart NABIL"
        )
        return

    limit = 30

    if len(context.args) == 2:
        try:
            limit = int(context.args[1])
        except ValueError:
            await update.message.reply_text(
                "Invalid limit. Please enter a number from 1 to 250."
            )
            return

    if not 1 <= limit <= 250:
        await update.message.reply_text(
            "Chart limit must be between 1 and 250."
        )
        return

    try:
        records = await get_price_history(symbol, limit=limit)

        if not records:
            await update.message.reply_text(
                f"No historical data found for {symbol}."
            )
            return

        chart = generate_price_chart(records, symbol)
        chart.name = f"{symbol}_historical_ltp.png"

        await update.message.reply_photo(
            photo=chart,
            caption=(
                f"📈 {symbol} — Historical LTP\n"
                f"Showing {len(records)} recent stored observations.\n"
                "Historical data is not a live quote or verified "
                "official closing-price series.\n"
                "For educational research only, not financial advice."
            ),
        )

    except Exception:
        logging.exception(
            "Failed to generate historical chart for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Unable to generate the historical chart right now."
        )


async def indicators_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    disclaimer = (
        "\n\n⚠️ Based on latest daily snapshots, not verified "
        "official closing prices. Educational research only — "
        "not financial advice."
    )

    if not context.args:
        await update.message.reply_text(
            "Usage: /indicators SYMBOL\n"
            "Example: /indicators NABIL"
            + disclaimer
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Please use a valid symbol, e.g. NABIL."
            + disclaimer
        )
        return

    try:
        result = await get_technical_analysis(symbol)

    except Exception:
        logging.exception(
            "Failed to calculate technical indicators for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Unable to calculate technical indicators right now."
            + disclaimer
        )
        return

    indicators = result["indicators"]
    observations = result["observations"]

    def format_value(value):
        if value is None:
            return "Insufficient history"
        return f"{value:.2f}"

    macd = indicators["macd"]

    if macd is None:
        macd_value = "Insufficient history"
        signal_value = "Insufficient history"
        histogram_value = "Insufficient history"
    else:
        macd_value = format_value(macd["macd"])
        signal_value = format_value(macd["signal"])
        histogram_value = format_value(macd["histogram"])

    lines = [
        f"📊 Technical Indicators — {symbol}",
        "",
        f"Daily observations: {observations}",
        "",
        f"SMA 20: {format_value(indicators['sma_20'])}",
        f"SMA 50: {format_value(indicators['sma_50'])}",
        f"EMA 20: {format_value(indicators['ema_20'])}",
        f"EMA 50: {format_value(indicators['ema_50'])}",
        f"RSI 14: {format_value(indicators['rsi_14'])}",
        f"MACD: {macd_value}",
        f"Signal: {signal_value}",
        f"Histogram: {histogram_value}",
    ]

    if observations == 0:
        lines.extend([
            "",
            "No daily price history is available yet.",
        ])

    lines.append(disclaimer)

    await update.message.reply_text("\n".join(lines))




async def compare_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    disclaimer = (
        "\n\n⚠️ Based on historical daily snapshots, not verified "
        "official closing prices. Educational research only — "
        "not financial advice."
    )

    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /compare SYMBOL1 SYMBOL2\n"
            "Example: /compare NABIL NICA"
            + disclaimer
        )
        return

    symbol1 = context.args[0].strip().upper()
    symbol2 = context.args[1].strip().upper()

    if not symbol1.isalnum() or not symbol2.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Use valid symbols such as NABIL and NICA."
            + disclaimer
        )
        return

    if symbol1 == symbol2:
        await update.message.reply_text(
            "Please enter two different stock symbols."
            + disclaimer
        )
        return

    try:
        result1 = await get_technical_analysis(symbol1)
        result2 = await get_technical_analysis(symbol2)

        history1 = await get_price_history(symbol1, limit=30)
        history2 = await get_price_history(symbol2, limit=30)

    except Exception:
        logging.exception(
            "Failed to compare %s and %s",
            symbol1,
            symbol2,
        )
        await update.message.reply_text(
            "⚠️ Unable to compare these stocks right now."
            + disclaimer
        )
        return

    def format_value(value):
        if value is None:
            return "Insufficient history"
        return f"{value:.2f}"

    def calculate_performance(records):
        if len(records) < 2:
            return None

        latest = float(records[0]["ltp"])
        starting = float(records[-1]["ltp"])

        if starting <= 0:
            return None

        change = latest - starting
        percentage = (change / starting) * 100

        return {
            "starting": starting,
            "latest": latest,
            "change": change,
            "percentage": percentage,
            "observations": len(records),
        }

    def format_performance(records):
        performance = calculate_performance(records)

        if performance is None:
            return "30-observation performance: Insufficient history"

        return (
            f"Performance ({performance['observations']} observations):\n"
            f"Starting LTP: NPR {performance['starting']:.2f}\n"
            f"Latest LTP: NPR {performance['latest']:.2f}\n"
            f"Change: NPR {performance['change']:+.2f}\n"
            f"Change: {performance['percentage']:+.2f}%"
        )

    def format_stock(result, history):
        indicators = result["indicators"]
        macd = indicators["macd"]

        if macd is None:
            macd_text = (
                "MACD: Insufficient history\n"
                "Signal: Insufficient history\n"
                "Histogram: Insufficient history"
            )
        else:
            macd_text = (
                f"MACD: {format_value(macd['macd'])}\n"
                f"Signal: {format_value(macd['signal'])}\n"
                f"Histogram: {format_value(macd['histogram'])}"
            )

        return (
            f"📊 {result['symbol']}\n"
            f"Observations: {result['observations']}\n"
            f"SMA 20: {format_value(indicators['sma_20'])}\n"
            f"SMA 50: {format_value(indicators['sma_50'])}\n"
            f"RSI 14: {format_value(indicators['rsi_14'])}\n"
            f"{macd_text}\n\n"
            f"{format_performance(history)}"
        )

    performance1 = calculate_performance(history1)
    performance2 = calculate_performance(history2)

    summary = ""

    if performance1 is not None and performance2 is not None:
        if performance1["percentage"] > performance2["percentage"]:
            winner = symbol1
        elif performance2["percentage"] > performance1["percentage"]:
            winner = symbol2
        else:
            winner = None

        if winner:
            summary = (
                f"\n\n🏆 Better historical performer: {winner}"
            )
        else:
            summary = "\n\nBoth stocks have equal percentage performance."

    message = (
        f"📈 STOCK COMPARISON\n\n"
        f"{format_stock(result1, history1)}\n\n"
        f"--------------------\n\n"
        f"{format_stock(result2, history2)}"
        f"{summary}"
        + disclaimer
    )

    await update.message.reply_text(message)




async def fundamentals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    disclaimer = (
        "\n\n⚠️ Source-reported financial information. "
        "Educational research only — not financial advice."
    )

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /fundamentals SYMBOL\n"
            "Example: /fundamentals NABIL"
            + disclaimer
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol or not all(c.isalnum() or c == "/" for c in symbol):
        await update.message.reply_text(
            "Invalid stock symbol. Use a symbol such as NABIL or NICA."
            + disclaimer
        )
        return

    try:
        company = await get_company_financials(symbol)
    except FundamentalDataError:
        logging.exception(
            "Unable to retrieve fundamental data for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Fundamental financial data is temporarily unavailable. "
            "Please try again later."
            + disclaimer
        )
        return
    except Exception:
        logging.exception(
            "Unexpected fundamental-data error for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Unable to retrieve financial information right now."
            + disclaimer
        )
        return

    if company is None:
        await update.message.reply_text(
            f"No fundamental financial data found for {symbol}."
            + disclaimer
        )
        return

    reports = company.get("reports", [])

    if not reports:
        await update.message.reply_text(
            f"No financial reports are available for {symbol}."
            + disclaimer
        )
        return

    quarter_order = {
        "Fourth Quarter": 4,
        "Third Quarter": 3,
        "Second Quarter": 2,
        "First Quarter": 1,
        None: 0,
    }

    reports = sorted(
        reports,
        key=lambda report: (
            report.get("fy", ""),
            quarter_order.get(report.get("quarter"), -1),
            report.get("type", ""),
        ),
        reverse=True,
    )[:5]

    def format_value(value):
        if value is None:
            return "Not reported"
        return f"{value:,.2f}"

    lines = [
        f"📑 FUNDAMENTAL REPORTS — {symbol}",
        "",
        f"Available reports: {len(company.get('reports', []))}",
        "Latest 5 reports:",
    ]

    for report in reports:
        period = report.get("fy", "Unknown fiscal year")
        quarter = report.get("quarter")

        if quarter:
            period += f" — {quarter}"

        lines.extend([
            "",
            f"{report.get('type', 'Financial Report')} | {period}",
        ])

        if report.get("status") == "ambiguous":
            lines.append(
                "⚠️ Conflicting source records — figures are unverified."
            )

        lines.extend([
            f"P/E: {format_value(report.get('pe'))}",
            f"EPS: {format_value(report.get('eps'))}",
            f"Profit: {format_value(report.get('profit'))}",
            f"Paid-up capital: {format_value(report.get('paid_up_capital'))}",
            f"Net worth per share: {format_value(report.get('net_worth_per_share'))}",
        ])

        documents = report.get("documents", [])
        for document in documents[:2]:
            url = document.get("url")
            submitted = document.get("submitted_date", "date unavailable")
            if url:
                lines.append(f"📄 Document ({submitted}): {url}")

    report_analysis = analyze_company_reports(company)
    latest_comparison_report = report_analysis["latest_report"]

    lines.extend([
        "",
        "📈 YEAR-OVER-YEAR COMPARISON",
    ])

    if latest_comparison_report is None:
        lines.append("No verified reports available for comparison.")
    else:
        comparison_period = latest_comparison_report.get(
            "fy", "Unknown fiscal year"
        )
        comparison_quarter = latest_comparison_report.get("quarter")

        if comparison_quarter:
            comparison_period += f" — {comparison_quarter}"

        lines.append(f"Latest verified period: {comparison_period}")

        comparison_labels = {
            "eps": "EPS",
            "profit": "Profit",
            "net_worth_per_share": "Net worth per share",
        }

        for field, label in comparison_labels.items():
            comparison = report_analysis["comparisons"][field]
            status = comparison["status"]

            if status == "insufficient_data":
                lines.append(
                    f"{label}: Insufficient comparable history."
                )
            elif status == "missing_values":
                lines.append(
                    f"{label}: Current or previous value not reported."
                )
            elif status == "ambiguous_period":
                lines.append(
                    f"{label}: Ambiguous reporting period; comparison withheld."
                )
            elif status == "comparison_unverified":
                lines.append(
                    f"{label}: {format_value(comparison['current'])} vs "
                    f"{format_value(comparison['previous'])} "
                    "(growth not calculated; quarterly figures may be cumulative)."
                )
            elif status == "compared":
                change = comparison["change_percent"]
                lines.append(
                    f"{label}: {format_value(comparison['current'])} vs "
                    f"{format_value(comparison['previous'])} "
                    f"({change:+.2f}%)."
                )
            else:
                lines.append(
                    f"{label}: Percentage change is not meaningful."
                )

    lines.extend([
        "",
        "💰 VALUATION METRICS",
    ])

    if (
        latest_comparison_report is None
        or latest_comparison_report.get("status") != "verified"
    ):
        lines.append("Valuation withheld: no latest verified financial report.")
    else:
        latest_pe = latest_comparison_report.get("pe")
        lines.append(
            f"Source-reported P/E: {format_value(latest_pe)}"
        )

        try:
            stock = await get_stock(symbol)

            if stock is None:
                lines.append(
                    "Market price unavailable; indicative P/B not calculated."
                )
            else:
                market_price = stock.get("ltp")
                price_timestamp = stock.get(
                    "last_updated", "timestamp unavailable"
                )

                if stock.get("is_stale"):
                    lines.append(
                        f"Last recorded LTP: {format_value(market_price)} "
                        f"(STALE — {price_timestamp})."
                    )
                    lines.append(
                        "Indicative P/B withheld because market data is stale."
                    )
                elif market_price is None:
                    lines.append(
                        "Market price unavailable; indicative P/B not calculated."
                    )
                else:
                    lines.append(
                        f"Market LTP: NPR {format_value(market_price)} "
                        f"({price_timestamp})."
                    )

                    book_value = latest_comparison_report.get(
                        "net_worth_per_share"
                    )
                    pb_ratio = calculate_pb_ratio(
                        market_price,
                        book_value,
                    )

                    if pb_ratio is None:
                        lines.append(
                            "Indicative P/B unavailable: positive net worth "
                            "per share was not reported."
                        )
                    else:
                        lines.append(
                            f"Indicative P/B: {pb_ratio:.2f}x "
                            "(LTP ÷ reported net worth per share)."
                        )

        except MarketDataError:
            logging.exception(
                "Unable to retrieve market price for valuation of %s",
                symbol,
            )
            lines.append(
                "Market data unavailable; indicative P/B not calculated."
            )
        except Exception:
            logging.exception(
                "Unexpected valuation error for %s",
                symbol,
            )
            lines.append(
                "Valuation could not be completed because market data "
                "could not be processed."
            )

    lines.append(
        "P/B is indicative only; reported net worth per share may not "
        "match independently verified book value per share."
    )

    lines.append(
        "\nFigures are displayed as reported by the source; "
        "units and accounting definitions are not independently verified."
    )
    lines.append(disclaimer.strip())

    message = "\n".join(lines)

    if len(message) > 4000:
        message = message[:3950] + "\n\nOutput shortened."

    await update.message.reply_text(message)


async def addstock_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if len(context.args) != 3:
        await update.message.reply_text(
            "Usage: /addstock SYMBOL QUANTITY BUY_PRICE\n"
            "Example: /addstock NABIL 10 500"
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text("Invalid stock symbol.")
        return

    try:
        quantity = float(context.args[1])
        buy_price = float(context.args[2])

        if (
            not math.isfinite(quantity)
            or not math.isfinite(buy_price)
            or quantity <= 0
            or buy_price <= 0
        ):
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "Quantity and buying price must be positive numbers."
        )
        return

    telegram_id = update.effective_user.id

    try:
        await add_portfolio_holding(
            telegram_id,
            symbol,
            quantity,
            buy_price,
        )
    except Exception:
        logging.exception("Failed to save portfolio holding")
        await update.message.reply_text(
            "Unable to save this holding right now."
        )
        return

    await update.message.reply_text(
        f"✅ Portfolio holding saved.\n\n"
        f"Stock: {symbol}\n"
        f"Quantity: {quantity:g}\n"
        f"Average buying price: NPR {buy_price:.2f}\n"
        f"Total investment: NPR {quantity * buy_price:,.2f}"
    )




async def portfolio_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    telegram_id = update.effective_user.id

    try:
        holdings = await get_portfolio(telegram_id)

        if not holdings:
            await update.message.reply_text(
                "Your portfolio is empty.\n\n"
                "Add a holding using:\n"
                "/addstock NABIL 10 500"
            )
            return

        lines = ["📊 YOUR NEPSE PORTFOLIO\n"]
        total_investment = 0.0
        priced_investment = 0.0
        total_current_value = 0.0

        for holding in holdings:
            symbol = holding["symbol"]
            quantity = float(holding["quantity"])
            buy_price = float(holding["average_buy_price"])

            investment = quantity * buy_price
            total_investment += investment

            history = await get_price_history(symbol, limit=1)

            if not history:
                lines.append(
                    f"📌 {symbol}\n"
                    f"Quantity: {quantity:g}\n"
                    f"Average buy price: NPR {buy_price:.2f}\n"
                    f"Investment: NPR {investment:,.2f}\n"
                    "Latest LTP: Unavailable\n"
                )
                continue

            latest_ltp = float(history[0]["ltp"])
            current_value = quantity * latest_ltp
            profit_loss = current_value - investment
            percentage = (profit_loss / investment) * 100

            priced_investment += investment
            total_current_value += current_value

            lines.append(
                f"📌 {symbol}\n"
                f"Quantity: {quantity:g}\n"
                f"Average buy price: NPR {buy_price:.2f}\n"
                f"Latest LTP: NPR {latest_ltp:.2f}\n"
                f"Investment: NPR {investment:,.2f}\n"
                f"Current value: NPR {current_value:,.2f}\n"
                f"P/L: NPR {profit_loss:+,.2f} "
                f"({percentage:+.2f}%)\n"
            )

        lines.append(
            "--------------------\n"
            f"Total investment: NPR {total_investment:,.2f}"
        )

        if priced_investment > 0:
            total_profit_loss = total_current_value - priced_investment
            total_percentage = (
                total_profit_loss / priced_investment
            ) * 100

            lines.append(
                f"Priced holdings investment: "
                f"NPR {priced_investment:,.2f}\n"
                f"Current value of priced holdings: "
                f"NPR {total_current_value:,.2f}\n"
                f"Portfolio P/L: NPR {total_profit_loss:+,.2f} "
                f"({total_percentage:+.2f}%)"
            )

        lines.append(
            "\n⚠️ Values use the latest available historical LTP "
            "snapshots, not verified live quotes. "
            "Educational research only — not financial advice."
        )

        await update.message.reply_text("\n".join(lines))

    except Exception:
        logging.exception("Failed to calculate portfolio")
        await update.message.reply_text(
            "Unable to retrieve your portfolio right now."
        )


async def removestock_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /removestock SYMBOL\n"
            "Example: /removestock NABIL"
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text("Invalid stock symbol.")
        return

    try:
        removed = await remove_portfolio_holding(
            update.effective_user.id,
            symbol,
        )
    except Exception:
        logging.exception("Failed to remove portfolio holding")
        await update.message.reply_text(
            "Unable to remove this holding right now."
        )
        return

    if removed:
        await update.message.reply_text(
            f"✅ {symbol} removed from your portfolio."
        )
    else:
        await update.message.reply_text(
            f"{symbol} was not found in your portfolio."
        )


async def allocation_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        holdings = await get_portfolio(update.effective_user.id)

        if not holdings:
            await update.message.reply_text(
                "Your portfolio is empty.\n"
                "Use /addstock to add a holding."
            )
            return

        values = []
        total_value = 0.0

        for holding in holdings:
            symbol = holding["symbol"]
            quantity = float(holding["quantity"])

            history = await get_price_history(symbol, limit=1)

            if not history:
                continue

            latest_ltp = float(history[0]["ltp"])
            current_value = quantity * latest_ltp

            values.append((symbol, current_value))
            total_value += current_value

        if not values or total_value <= 0:
            await update.message.reply_text(
                "No usable historical prices are available "
                "for your portfolio."
            )
            return

        lines = ["📊 PORTFOLIO ALLOCATION\n"]

        values.sort(key=lambda item: item[1], reverse=True)

        for symbol, current_value in values:
            percentage = current_value / total_value * 100

            lines.append(
                f"📌 {symbol}\n"
                f"Current value: NPR {current_value:,.2f}\n"
                f"Allocation: {percentage:.2f}%\n"
            )

        lines.append(
            f"Total portfolio value: NPR {total_value:,.2f}"
        )

        lines.append(
            "\n⚠️ Based on historical LTP snapshots, not verified "
            "live quotes. Educational research only — "
            "not financial advice."
        )

        await update.message.reply_text("\n".join(lines))

    except Exception:
        logging.exception("Failed to calculate portfolio allocation")
        await update.message.reply_text(
            "Unable to calculate portfolio allocation right now."
        )


async def diversification_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        holdings = await get_portfolio(update.effective_user.id)

        if not holdings:
            await update.message.reply_text(
                "Your portfolio is empty.\n"
                "Use /addstock to add holdings."
            )
            return

        values = []

        for holding in holdings:
            symbol = holding["symbol"]
            quantity = float(holding["quantity"])

            history = await get_price_history(symbol, limit=1)

            if not history:
                continue

            latest_ltp = float(history[0]["ltp"])
            current_value = quantity * latest_ltp

            if current_value > 0:
                values.append((symbol, current_value))

        if not values:
            await update.message.reply_text(
                "No usable historical prices are available."
            )
            return

        values.sort(key=lambda item: item[1], reverse=True)

        total_value = sum(value for _, value in values)

        largest_symbol, largest_value = values[0]
        largest_percentage = largest_value / total_value * 100

        top_two_value = sum(value for _, value in values[:2])
        top_two_percentage = top_two_value / total_value * 100

        lines = [
            "🛡️ PORTFOLIO DIVERSIFICATION REPORT\n",
            f"Priced stocks: {len(values)}",
            f"Total current value: NPR {total_value:,.2f}",
            "",
            f"Largest holding: {largest_symbol}",
            f"Largest holding weight: {largest_percentage:.2f}%",
            f"Top two holdings weight: {top_two_percentage:.2f}%",
            "",
        ]

        if largest_percentage > 50:
            lines.append(
                "⚠️ High concentration: one stock represents "
                "more than 50% of your portfolio."
            )
        elif top_two_percentage > 80:
            lines.append(
                "⚠️ High concentration: your top two stocks "
                "represent more than 80% of your portfolio."
            )
        else:
            lines.append(
                "No concentration warning under these simple thresholds."
            )

        lines.append(
            "\n⚠️ Based on historical LTP snapshots, not verified "
            "live quotes. This is a simple concentration check, "
            "not a complete risk assessment."
        )

        await update.message.reply_text("\n".join(lines))

    except Exception:
        logging.exception("Failed to calculate diversification")
        await update.message.reply_text(
            "Unable to calculate diversification right now."
        )


async def performance_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        telegram_id = update.effective_user.id
        today = datetime.now(
            ZoneInfo("Asia/Kathmandu")
        ).date().isoformat()

        holdings = await get_portfolio(telegram_id)

        if not holdings:
            await update.message.reply_text(
                "Your portfolio is empty.\n"
                "Use /addstock to add holdings."
            )
            return

        total_investment = 0.0
        current_value = 0.0
        priced_count = 0
        lines = ["📈 PORTFOLIO PERFORMANCE\n"]

        for holding in holdings:
            symbol = holding["symbol"]
            quantity = float(holding["quantity"])
            buy_price = float(holding["average_buy_price"])

            history = await get_price_history(symbol, limit=1)

            if not history:
                lines.append(
                    f"{symbol}: Historical price unavailable\n"
                )
                continue

            latest_ltp = float(history[0]["ltp"])
            investment = quantity * buy_price
            value = quantity * latest_ltp
            profit_loss = value - investment
            percentage = profit_loss / investment * 100

            total_investment += investment
            current_value += value
            priced_count += 1

            lines.append(
                f"📌 {symbol}\n"
                f"Investment: NPR {investment:,.2f}\n"
                f"Current value: NPR {value:,.2f}\n"
                f"P/L: NPR {profit_loss:+,.2f} "
                f"({percentage:+.2f}%)\n"
            )

        if priced_count == 0 or total_investment <= 0:
            await update.message.reply_text(
                "No usable historical prices are available "
                "for your portfolio."
            )
            return

        total_profit_loss = current_value - total_investment
        total_percentage = (
            total_profit_loss / total_investment
        ) * 100

        previous_snapshots = await get_portfolio_daily_snapshots(
            telegram_id,
            limit=30,
        )

        previous_snapshot = next(
            (
                snapshot
                for snapshot in previous_snapshots
                if snapshot["snapshot_date"] < today
            ),
            None,
        )

        await save_portfolio_daily_snapshot(
            telegram_id,
            today,
            total_investment,
            current_value,
            priced_count,
        )

        lines.extend([
            "--------------------",
            f"Snapshot date: {today}",
            f"Priced holdings: {priced_count}",
            f"Total investment: NPR {total_investment:,.2f}",
            f"Current value: NPR {current_value:,.2f}",
            f"Portfolio P/L: NPR {total_profit_loss:+,.2f} "
            f"({total_percentage:+.2f}%)",
        ])

        if previous_snapshot:
            previous_value = float(
                previous_snapshot["current_value"]
            )
            change = current_value - previous_value
            change_percentage = (
                change / previous_value * 100
                if previous_value > 0 else 0.0
            )

            lines.append(
                f"\nChange since {previous_snapshot['snapshot_date']}:\n"
                f"NPR {change:+,.2f} "
                f"({change_percentage:+.2f}%)"
            )
        else:
            lines.append(
                "\nFirst daily snapshot saved. "
                "Run /performance on a later day to compare."
            )

        lines.append(
            "\n⚠️ Uses historical LTP snapshots, not verified "
            "live quotes. Tracking starts from the first saved "
            "snapshot. Educational research only — not financial advice."
        )

        await update.message.reply_text("\n".join(lines))

    except Exception:
        logging.exception("Failed to calculate portfolio performance")
        await update.message.reply_text(
            "Unable to calculate portfolio performance right now."
        )


async def alert_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Create an above or below stock price alert."""
    import math

    if len(context.args) != 3:
        await update.message.reply_text(
            "Usage: /alert SYMBOL above|below PRICE\n"
            "Example: /alert NABIL above 600"
        )
        return

    symbol = context.args[0].strip().upper()
    condition = context.args[1].strip().lower()

    if not symbol.isalnum():
        await update.message.reply_text("Invalid stock symbol.")
        return

    if condition not in ("above", "below"):
        await update.message.reply_text(
            "Condition must be 'above' or 'below'."
        )
        return

    try:
        target_price = float(context.args[2])
    except (TypeError, ValueError):
        await update.message.reply_text("Enter a valid target price.")
        return

    if not math.isfinite(target_price) or target_price <= 0:
        await update.message.reply_text(
            "Target price must be a positive number."
        )
        return

    try:
        alert_id = await add_stock_price_alert(
            update.effective_user.id,
            symbol,
            condition,
            target_price,
        )
        await update.message.reply_text(
            f"✅ Price alert created.\n"
            f"ID: {alert_id}\n"
            f"Stock: {symbol}\n"
            f"Condition: {condition.upper()}\n"
            f"Target: NPR {target_price:,.2f}"
        )
    except Exception:
        logging.exception("Failed to create stock price alert")
        await update.message.reply_text(
            "Unable to create the alert right now."
        )


async def alerts_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Show the user's active stock price alerts."""
    try:
        alerts = await get_stock_price_alerts(
            update.effective_user.id
        )

        if not alerts:
            await update.message.reply_text(
                "You have no active price alerts.\n"
                "Example: /alert NABIL above 600"
            )
            return

        lines = ["🔔 YOUR ACTIVE PRICE ALERTS\n"]

        for alert in alerts:
            lines.append(
                f"ID: {alert['id']} | {alert['symbol']}\n"
                f"Condition: {alert['condition'].upper()}\n"
                f"Target: NPR {alert['target_price']:,.2f}\n"
            )

        lines.append("Remove an alert with /removealert ID")

        await update.message.reply_text("\n".join(lines))

    except Exception:
        logging.exception("Failed to retrieve stock price alerts")
        await update.message.reply_text(
            "Unable to retrieve your alerts right now."
        )


async def removealert_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Cancel one of the user's active price alerts."""
    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /removealert ID\n"
            "Example: /removealert 1"
        )
        return

    try:
        alert_id = int(context.args[0])
        if alert_id <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Alert ID must be a positive integer."
        )
        return

    try:
        removed = await remove_stock_price_alert(
            update.effective_user.id,
            alert_id,
        )

        if removed:
            await update.message.reply_text(
                f"✅ Alert #{alert_id} cancelled."
            )
        else:
            await update.message.reply_text(
                "Active alert not found. Check its ID with /alerts."
            )

    except Exception:
        logging.exception("Failed to remove stock price alert")
        await update.message.reply_text(
            "Unable to remove the alert right now."
        )


async def _portfolio_transaction_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    transaction_type: str,
) -> None:
    if len(context.args) != 3:
        await update.message.reply_text(
            f"Usage: /{transaction_type} SYMBOL QUANTITY PRICE\n"
            f"Example: /{transaction_type} NABIL 10 500"
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text("Invalid stock symbol.")
        return

    try:
        quantity = float(context.args[1])
        price = float(context.args[2])

        result = await record_portfolio_transaction(
            telegram_id=update.effective_user.id,
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
        )

    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    except Exception:
        logging.exception("Failed to record portfolio transaction")
        await update.message.reply_text(
            "Unable to record this transaction right now."
        )
        return

    fees = result["fee_breakdown"]
    trade_value = fees["trade_value"]

    message = (
        f"✅ {transaction_type.upper()} transaction recorded.\n\n"
        f"Stock: {result['symbol']}\n"
        f"Quantity: {quantity:g}\n"
        f"Price: NPR {price:,.2f}\n"
        f"Trade value: NPR {trade_value:,.2f}\n\n"
        f"Broker commission: NPR {fees['broker_commission']:,.2f}\n"
        f"SEBON fee: NPR {fees['sebon_fee']:,.2f}\n"
        f"DP charge: NPR {fees['dp_charge']:,.2f}\n"
        f"Total charges: NPR {fees['total_fees']:,.2f}"
    )

    if transaction_type == "buy":
        message += (
            f"\nTotal buy cost: "
            f"NPR {trade_value + fees['total_fees']:,.2f}"
        )
    else:
        message += (
            f"\nNet sale proceeds: "
            f"NPR {trade_value - fees['total_fees']:,.2f}"
        )
        pnl = result["realized_profit_loss"]
        message += f"\nRealized P&L: NPR {pnl:+,.2f}"

    await update.message.reply_text(message)


async def buy_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _portfolio_transaction_command(update, context, "buy")


async def sell_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _portfolio_transaction_command(update, context, "sell")


async def transactions_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if len(context.args) > 1:
        await update.message.reply_text(
            "Usage: /transactions [LIMIT]\nExample: /transactions 10"
        )
        return

    try:
        limit = int(context.args[0]) if context.args else 10

        if not 1 <= limit <= 50:
            raise ValueError

        transactions = await get_portfolio_transactions(
            update.effective_user.id,
            limit=limit,
        )

    except ValueError:
        await update.message.reply_text("Limit must be between 1 and 50.")
        return
    except Exception:
        logging.exception("Failed to retrieve transaction history")
        await update.message.reply_text(
            "Unable to retrieve transactions right now."
        )
        return

    if not transactions:
        await update.message.reply_text(
            "No transactions found.\n\n"
            "Record your first purchase using:\n"
            "/buy NABIL 10 500"
        )
        return

    entries = []

    for item in transactions:
        action = item["transaction_type"].upper()
        entry = (
            f"{action} {item['symbol']}\n"
            f"Quantity: {item['quantity']:g}\n"
            f"Price: NPR {item['price']:,.2f}\n"
            f"Trade value: NPR "
            f"{item['quantity'] * item['price']:,.2f}"
        )

        if item["broker_commission"] is not None:
            entry += (
                f"\nBroker commission: "
                f"NPR {item['broker_commission']:,.2f}"
                f"\nSEBON fee: NPR {item['sebon_fee']:,.2f}"
                f"\nDP charge: NPR {item['dp_charge']:,.2f}"
            )
        else:
            entry += "\nFee breakdown: Unavailable (historical record)"

        entry += f"\nTotal fees: NPR {item['fees']:,.2f}"

        if item['realized_profit_loss'] is not None:
            entry += (
                f"\nRealized P&L: "
                f"NPR {item['realized_profit_loss']:+,.2f}"
            )

        entry += f"\nDate: {item['created_at']}"
        entries.append(entry)

    heading = "📒 YOUR TRANSACTION HISTORY"
    messages = []
    current_message = heading

    for entry in entries:
        addition = "\n\n" + entry

        if len(current_message) + len(addition) > 3500:
            messages.append(current_message)
            current_message = heading + addition
        else:
            current_message += addition

    if current_message:
        messages.append(current_message)

    for message in messages:
        await update.message.reply_text(message)


async def signal_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    disclaimer = (
        "\n\n⚠️ Based on latest market data and historical daily "
        "snapshots, not verified official closing prices. "
        "Educational research only — not financial advice. "
        "Signals are not guaranteed predictions."
    )

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /signal SYMBOL\n"
            "Example: /signal NABIL"
            + disclaimer
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Please use a valid symbol, e.g. NABIL."
            + disclaimer
        )
        return

    try:
        result = await get_stock_signal(symbol)

    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ {exc}" + disclaimer
        )
        return

    except Exception:
        logging.exception(
            "Failed to generate trading signal for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Unable to generate a trading signal right now."
            + disclaimer
        )
        return

    signal = result["signal"]
    score = result["score"]
    score_text = f"{score:+d}/4"

    if signal == "BUY":
        heading = "🟢 BUY"
    elif signal == "SELL":
        heading = "🔴 SELL"
    elif signal == "HOLD":
        heading = "🟡 HOLD"
    elif signal == "STALE_DATA":
        heading = "⚠️ STALE DATA — NO ACTIONABLE SIGNAL"
    else:
        heading = "⚠️ INSUFFICIENT DATA — NO ACTIONABLE SIGNAL"

    lines = [
        f"📊 Trading Signal — {result['symbol']}",
        "",
        f"Signal: {heading}",
        f"Score: {score_text}",
        f"Strength: {result['strength']}",
        f"LTP snapshot: NPR {result['ltp']:.2f}",
        f"Data age: {result['age_minutes']:.0f} minutes",
        f"Last updated: {result['last_updated']}",
        f"Daily observations: {result['observations']}",
        "",
        "Analysis:",
    ]

    lines.extend(f"• {reason}" for reason in result["reasons"])
    lines.append(disclaimer)

    await update.message.reply_text("\n".join(lines))


async def backtest_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    disclaimer = (
        "\n\n⚠️ Historical research only — not financial advice. "
        "Past performance does not guarantee future results."
    )

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /backtest SYMBOL\n"
            "Example: /backtest NABIL"
            + disclaimer
        )
        return

    symbol = context.args[0].strip().upper()

    if not symbol.isalnum():
        await update.message.reply_text(
            "Invalid stock symbol. Please use a valid symbol, e.g. NABIL."
            + disclaimer
        )
        return

    try:
        result = await backtest_symbol(symbol)

    except ValueError as exc:
        await update.message.reply_text(
            f"⚠️ {exc}" + disclaimer
        )
        return

    except Exception:
        logging.exception(
            "Failed to backtest historical signals for %s",
            symbol,
        )
        await update.message.reply_text(
            "⚠️ Unable to run historical backtesting right now."
            + disclaimer
        )
        return

    if result.get("message"):
        await update.message.reply_text(
            f"📊 Historical Backtest — {result['symbol']}\n\n"
            f"Daily observations: {result['observations']}\n"
            f"⚠️ {result['message']}"
            + disclaimer
        )
        return

    signals = result["signals"]

    lines = [
        f"📊 Historical Backtest — {result['symbol']}",
        "",
        f"Daily observations: {result['observations']}",
        f"Period: {result['first_date']} to {result['last_date']}",
        "",
        "Historical signal counts:",
        f"🟢 BUY: {signals['BUY']}",
        f"🔴 SELL: {signals['SELL']}",
        f"🟡 HOLD: {signals['HOLD']}",
        "",
        "Forward performance:",
    ]

    for horizon, summary in result["results"].items():
        win_rate = summary["win_rate_pct"]
        average_return = summary["average_return_pct"]

        win_text = (
            f"{win_rate:.2f}%"
            if win_rate is not None
            else "N/A"
        )
        average_text = (
            f"{average_return:+.2f}%"
            if average_return is not None
            else "N/A"
        )

        lines.extend([
            "",
            f"📅 {horizon}-observation horizon",
            f"Completed trades: {summary['trades']}",
            f"BUY trades: {summary['buy_trades']}",
            f"SELL trades: {summary['sell_trades']}",
            f"Wins / Losses: {summary['wins']} / {summary['losses']}",
            f"Win rate: {win_text}",
            f"Average directional return: {average_text}",
        ])

    lines.extend([
        "",
        "Methodology:",
        "• Entry: Next available daily observation after signal.",
        "• Exit: After the selected number of additional observations.",
        "• Fees and slippage: Excluded.",
        "• Prices: Historical daily LTP snapshots, not verified official closes.",
        "• Signals use only data available on their signal dates.",
        disclaimer,
    ])

    await update.message.reply_text("\n".join(lines))
