
import logging
import math
from datetime import date

import httpx

from database.db import save_price_snapshots

logger = logging.getLogger(__name__)

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Shubhamnpk/yonepse/main/data/ltp"
)

SOURCE = "YONEPSE historical daily LTP dataset"


class HistoricalDataError(Exception):
    """Raised when historical market data is invalid."""


async def fetch_historical_month(year_month: str) -> dict:
    """Download and validate one historical monthly dataset."""

    try:
        year, month = map(int, year_month.split("-"))

        if (
            len(year_month) != 7
            or year < 2000
            or month < 1
            or month > 12
        ):
            raise ValueError

    except (ValueError, TypeError):
        raise HistoricalDataError(
            "Invalid month format; use YYYY-MM"
        )

    url = f"{BASE_URL}/monthly/{year_month}.json"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

    except (httpx.HTTPError, ValueError) as exc:
        raise HistoricalDataError(
            f"Unable to retrieve historical data for {year_month}"
        ) from exc

    if not isinstance(data, dict):
        raise HistoricalDataError("Invalid historical dataset")

    if data.get("version") != 1:
        raise HistoricalDataError("Unsupported dataset version")

    if data.get("market") != "NEPSE":
        raise HistoricalDataError("Unexpected market")

    if data.get("currency") != "NPR":
        raise HistoricalDataError("Unexpected currency")

    if data.get("columns") != [
        "dateIndex",
        "ltp",
        "volume",
        "turnover",
        "trades",
    ]:
        raise HistoricalDataError("Unexpected historical columns")

    if data.get("month") != year_month:
        raise HistoricalDataError("Historical month mismatch")

    dates = data.get("dates")
    series = data.get("series")

    if not isinstance(dates, list) or not isinstance(series, dict):
        raise HistoricalDataError("Invalid historical data structure")

    for trading_date in dates:
        try:
            parsed_date = date.fromisoformat(trading_date)
        except (TypeError, ValueError) as exc:
            raise HistoricalDataError("Invalid trading date") from exc

        if parsed_date.strftime("%Y-%m") != year_month:
            raise HistoricalDataError(
                "Trading date outside requested month"
            )

    return data


async def import_historical_month(year_month: str) -> dict:
    """Validate and batch-import one historical month."""

    data = await fetch_historical_month(year_month)

    stocks = []
    rejected = 0
    dates = data["dates"]

    for symbol, records in data["series"].items():

        if (
            not isinstance(symbol, str)
            or not symbol
            or not symbol.isascii()
            or not all(
                char.isalnum() or char == "/"
                for char in symbol
            )
        ):
            rejected += 1
            continue

        if not isinstance(records, list):
            rejected += 1
            continue

        for record in records:
            try:
                if (
                    not isinstance(record, list)
                    or len(record) not in (2, 3, 4, 5)
                ):
                    raise ValueError("Invalid record")

                if len(record) == 2:
                    date_index, ltp = record
                    volume = None
                    turnover = None
                    trades = None
                elif len(record) == 3:
                    date_index, ltp, volume = record
                    turnover = None
                    trades = None
                elif len(record) == 4:
                    date_index, ltp, volume, turnover = record
                    trades = None
                else:
                    date_index, ltp, volume, turnover, trades = record

                if (
                    isinstance(date_index, bool)
                    or not isinstance(date_index, int)
                    or date_index < 0
                    or date_index >= len(dates)
                ):
                    raise ValueError("Invalid date index")

                values = [ltp, volume, turnover, trades]

                if (
                    isinstance(ltp, bool)
                    or not isinstance(ltp, (int, float))
                    or not math.isfinite(ltp)
                    or ltp <= 0
                ):
                    raise ValueError("Invalid LTP")

                for value in values[1:]:
                    if value is not None and (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise ValueError("Invalid optional market data")

                if (
                    trades is not None
                    and not float(trades).is_integer()
                ):
                    raise ValueError("Invalid trade count")

                trading_date = dates[date_index]

                stocks.append({
                    "symbol": symbol,
                    "ltp": float(ltp),
                    "volume": (
                        float(volume) if volume is not None else None
                    ),
                    "turnover": (
                        float(turnover) if turnover is not None else None
                    ),
                    "last_updated": (
                        f"{trading_date}T15:00:00+05:45"
                    ),
                    "source": SOURCE,
                })

            except (ValueError, TypeError, KeyError):
                rejected += 1
                logger.warning(
                    "Rejected historical record for %s",
                    symbol,
                )

    inserted, duplicates = await save_price_snapshots(stocks)

    return {
        "month": year_month,
        "inserted": inserted,
        "duplicates": duplicates,
        "rejected": rejected,
    }
