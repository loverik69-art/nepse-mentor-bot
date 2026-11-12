
import httpx
import math
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from database.db import save_price_snapshot

logger = logging.getLogger(__name__)

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Shubhamnpk/yonepse/main"
)

MARKET_DATA_URL = f"{BASE_URL}/data/nepse_data.json"

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")


class MarketDataError(Exception):
    """Raised when market data cannot be safely retrieved."""


def parse_timestamp(value):
    if not value:
        raise MarketDataError("Missing source timestamp")

    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise MarketDataError("Invalid source timestamp") from exc

    # Source timestamps without timezone are treated as Nepal time.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=NEPAL_TZ)

    return timestamp.astimezone(NEPAL_TZ)


def normalize_stock(row):
    required = ["symbol", "name", "ltp", "last_updated"]

    if not isinstance(row, dict):
        raise MarketDataError("Invalid stock record")

    if any(row.get(field) is None for field in required):
        raise MarketDataError("Incomplete stock record")


    symbol = str(row["symbol"]).strip().upper()
    name = str(row["name"]).strip()

    if not symbol or not name:
        raise MarketDataError("Blank stock symbol or name")

    if (
        not symbol.isascii()
        or not all(
            char.isalnum() or char == "/"
            for char in symbol
        )
        or symbol.startswith("/")
        or symbol.endswith("/")
        or "//" in symbol
        or (
            "/" in symbol
            and not symbol.split("/", 1)[1].isdigit()
        )
    ):
        raise MarketDataError("Invalid stock symbol format")
    try:
        ltp = float(row["ltp"])
    except (TypeError, ValueError) as exc:
        raise MarketDataError("Invalid stock price") from exc

    if not math.isfinite(ltp) or ltp <= 0:
        raise MarketDataError("Stock price must be finite and positive")


    numeric_fields = [
        "previous_close",
        "change",
        "percent_change",
        "high",
        "low",
        "volume",
        "turnover",
        "trades",
        "market_cap",
    ]

    validated = {}

    for field in numeric_fields:
        value = row.get(field)

        if value is None:
            validated[field] = None
            continue

        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise MarketDataError(
                f"Invalid {field} value"
            ) from exc

        if not math.isfinite(number):
            raise MarketDataError(
                f"Non-finite {field} value"
            )

        if field in ("volume", "turnover", "trades", "market_cap") and number < 0:
            raise MarketDataError(
                f"Negative {field} value"
            )

        if field in ("previous_close", "high", "low") and number < 0:
            raise MarketDataError(
                f"Negative {field} value"
            )

        validated[field] = number
        if field in ("volume", "trades") and not number.is_integer():
            raise MarketDataError(
                f"Invalid {field}: must be a whole number"
            )
    high = validated.get("high")
    low = validated.get("low")

    previous_close = validated.get("previous_close")
    change = validated.get("change")
    percent_change = validated.get("percent_change")

    if previous_close is not None and previous_close > 0:
        expected_change = ltp - previous_close

        if change is not None and not math.isclose(
            change, expected_change, rel_tol=0.0, abs_tol=0.02
        ):
            raise MarketDataError("Inconsistent price change")

        expected_percent = (expected_change / previous_close) * 100

        if percent_change is not None and not math.isclose(
            percent_change, expected_percent, rel_tol=0.0, abs_tol=0.02
        ):
            raise MarketDataError("Inconsistent percentage change")

    if high is not None and low is not None and high < low:
        raise MarketDataError("Daily high cannot be lower than daily low")

    if high is not None and ltp > high:
        raise MarketDataError("Last traded price cannot exceed daily high")

    if low is not None and ltp < low:
        raise MarketDataError("Last traded price cannot be below daily low")

    timestamp = parse_timestamp(row["last_updated"])
    now = datetime.now(NEPAL_TZ)

    if timestamp > now + timedelta(minutes=5):
        raise MarketDataError("Source timestamp is in the future")

    age_minutes = int((now - timestamp).total_seconds() / 60)

    return {
        "symbol": symbol,
        "name": name,
        "ltp": ltp,
        **validated,
        "last_updated": timestamp.isoformat(),
        "age_minutes": age_minutes,
        "is_stale": age_minutes > 24 * 60,
        "source": "YONEPSE community data feed",
    }

async def fetch_market_data():
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(MARKET_DATA_URL)
            response.raise_for_status()
            payload = response.json()

    except (httpx.HTTPError, ValueError) as exc:
        logger.error(
            "Failed to retrieve NEPSE market data"
        )
        raise MarketDataError(
            "Unable to retrieve NEPSE market data"
        ) from exc
    if not isinstance(payload, list):
        logger.error(
            "Unexpected market-data format received"
        )
        raise MarketDataError("Unexpected market-data format")

    stocks = []
    rejected_count = 0

    for row in payload:
        try:
            stocks.append(normalize_stock(row))
        except MarketDataError as exc:
            rejected_count += 1
            logger.warning(
                "Rejected market-data record: %s",
                str(exc),
            )
            continue

    if not stocks:
        logger.error(
            "NEPSE market-data feed returned no records"
        )
        raise MarketDataError("No valid stock records received")

    # Keep only the newest record for each stock symbol.
    unique_stocks = {}

    for stock in stocks:
        symbol = stock["symbol"]
        existing = unique_stocks.get(symbol)

        if existing is None or stock["last_updated"] > existing["last_updated"]:
            unique_stocks[symbol] = stock

    final_stocks = list(unique_stocks.values())

    duplicate_count = len(stocks) - len(final_stocks)
    fresh_count = sum(
        1 for stock in final_stocks
        if not stock["is_stale"]
    )
    stale_count = len(final_stocks) - fresh_count

    logger.info(
        "NEPSE feed processed: received=%d valid=%d "
        "rejected=%d duplicates_removed=%d "
        "fresh=%d stale=%d",
        len(payload),
        len(stocks),
        rejected_count,
        duplicate_count,
        fresh_count,
        stale_count,
    )

    for stock in final_stocks:
        if stock["is_stale"]:
            continue

        try:
            await save_price_snapshot(stock)
        except Exception:
            logger.exception(
                "Failed to save price snapshot for %s",
                stock["symbol"],
            )

    return final_stocks

async def get_stock(symbol):
    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Please provide a stock symbol")

    stocks = await fetch_market_data()

    for stock in stocks:
        if stock["symbol"] == symbol:
            return stock

    return None

async def get_market_movers(direction="gainers", limit=10):
    if direction not in ("gainers", "losers"):
        raise ValueError("Direction must be 'gainers' or 'losers'")

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("Limit must be a positive integer")

    stocks = await fetch_market_data()

    movers = []

    for stock in stocks:
        percent_change = stock.get("percent_change")

        if percent_change is None:
            continue

        if direction == "gainers" and percent_change > 0:
            movers.append(stock)

        elif direction == "losers" and percent_change < 0:
            movers.append(stock)

    if direction == "gainers":
        movers.sort(
            key=lambda stock: stock["percent_change"],
            reverse=True,
        )
    else:
        movers.sort(
            key=lambda stock: stock["percent_change"]
        )

    return movers[:limit]

