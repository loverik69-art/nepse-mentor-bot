import math
from decimal import Decimal, ROUND_HALF_UP
import aiosqlite
from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    experience TEXT NOT NULL,
    trading_style TEXT NOT NULL,
    capital_npr REAL NOT NULL CHECK(capital_npr >= 0),
    risk_tolerance TEXT NOT NULL,
    max_risk_pct REAL NOT NULL CHECK(max_risk_pct > 0 AND max_risk_pct <= 5),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL,
    total_investment REAL NOT NULL,
    current_value REAL NOT NULL,
    holdings_count INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_id, snapshot_date)
);
CREATE TABLE IF NOT EXISTS stock_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ltp REAL NOT NULL CHECK(ltp > 0),
    volume REAL CHECK(volume IS NULL OR volume >= 0),
    turnover REAL CHECK(turnover IS NULL OR turnover >= 0),
    source_updated_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    UNIQUE(symbol, source_updated_at)
);
CREATE TABLE IF NOT EXISTS stock_price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    condition TEXT NOT NULL CHECK(condition IN ('above', 'below')),
    target_price REAL NOT NULL CHECK(target_price > 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'triggered', 'cancelled')),
    triggered_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    average_buy_price REAL NOT NULL CHECK(average_buy_price > 0),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_id, symbol)
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('buy', 'sell')),
    quantity REAL NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price > 0),
    fees REAL NOT NULL DEFAULT 0 CHECK(fees >= 0),
    realized_profit_loss REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_user_id
ON portfolio_transactions(telegram_id, id);

CREATE INDEX IF NOT EXISTS idx_alerts_user_id
ON stock_price_alerts(telegram_id, id);

CREATE INDEX IF NOT EXISTS idx_alerts_active_id
ON stock_price_alerts(id)
WHERE status = 'active';
"""

async def init_db() -> None:
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        await db.executescript(SCHEMA)

        cursor = await db.execute(
            "PRAGMA table_info(portfolio_transactions)"
        )
        columns = {row[1] for row in await cursor.fetchall()}

        for column in (
            "broker_commission",
            "sebon_fee",
            "dp_charge",
        ):
            if column not in columns:
                await db.execute(
                    f"ALTER TABLE portfolio_transactions "
                    f"ADD COLUMN {column} REAL"
                )

        await db.commit()

async def save_price_snapshot(stock: dict) -> bool:
    """Save a stock price snapshot once. Return False for duplicates."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO stock_price_history (
                symbol,
                ltp,
                volume,
                turnover,
                source_updated_at,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                stock["symbol"],
                stock["ltp"],
                stock.get("volume"),
                stock.get("turnover"),
                stock["last_updated"],
                stock["source"],
            ),
        )
        await db.commit()
        return cursor.rowcount == 1

async def save_price_snapshots(stocks: list[dict]) -> tuple[int, int]:
    """Save multiple price snapshots using one database connection."""

    if not stocks:
        return 0, 0

    records = [
        (
            stock["symbol"],
            stock["ltp"],
            stock.get("volume"),
            stock.get("turnover"),
            stock["last_updated"],
            stock["source"],
        )
        for stock in stocks
    ]

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        cursor = await db.executemany(
            """
            INSERT OR IGNORE INTO stock_price_history (
                symbol,
                ltp,
                volume,
                turnover,
                source_updated_at,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            records,
        )

        inserted = cursor.rowcount
        await db.commit()

    duplicates = len(records) - inserted

    return inserted, duplicates

async def get_price_history(
    symbol: str,
    limit: int = 30,
) -> list[dict]:
    """Return the newest historical price snapshots for a stock."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT
                symbol,
                ltp,
                volume,
                turnover,
                source_updated_at,
                recorded_at,
                source
            FROM stock_price_history
            WHERE symbol = ?
            ORDER BY source_updated_at DESC, id DESC
            LIMIT ?
            """,
            (symbol.upper(), limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
async def save_profile(telegram_id: int, username: str | None, profile: dict) -> None:
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        await db.execute("""
            INSERT INTO user_profiles
            (telegram_id, username, experience, trading_style, capital_npr, risk_tolerance, max_risk_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
              username=excluded.username,
              experience=excluded.experience,
              trading_style=excluded.trading_style,
              capital_npr=excluded.capital_npr,
              risk_tolerance=excluded.risk_tolerance,
              max_risk_pct=excluded.max_risk_pct,
              updated_at=CURRENT_TIMESTAMP
        """, (
            telegram_id, username, profile["experience"], profile["trading_style"],
            profile["capital_npr"], profile["risk_tolerance"], profile["max_risk_pct"]
        ))
        await db.commit()

async def get_profile(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT experience, trading_style, capital_npr, risk_tolerance, max_risk_pct "
            "FROM user_profiles WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def check_db() -> bool:
    """Return True when SQLite can execute a basic query."""
    try:
        async with aiosqlite.connect(settings.database_path, timeout=30) as db:
            async with db.execute("SELECT 1") as cursor:
                row = await cursor.fetchone()
                return row == (1,)
    except aiosqlite.Error:
        return False

async def get_indicator_prices(
    symbol: str,
    limit: int = 250,
) -> list[float]:
    """Return one latest daily snapshot per date, oldest first."""

    if limit < 1:
        raise ValueError("limit must be at least 1")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        async with db.execute(
            """
            SELECT ltp
            FROM (
                SELECT
                    ltp,
                    DATE(source_updated_at) AS trading_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY DATE(source_updated_at)
                        ORDER BY source_updated_at DESC, id DESC
                    ) AS row_number
                FROM stock_price_history
                WHERE symbol = ?
            )
            WHERE row_number = 1
            ORDER BY trading_date DESC
            LIMIT ?
            """,
            (symbol.strip().upper(), limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [row[0] for row in reversed(rows)]



async def get_daily_price_history(
    symbol: str,
    limit: int = 5000,
) -> list[dict]:
    """Return dated latest daily snapshots, oldest first."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        async with db.execute(
            """
            SELECT trading_date, ltp
            FROM (
                SELECT
                    DATE(source_updated_at) AS trading_date,
                    ltp,
                    ROW_NUMBER() OVER (
                        PARTITION BY DATE(source_updated_at)
                        ORDER BY source_updated_at DESC, id DESC
                    ) AS row_number
                FROM stock_price_history
                WHERE symbol = ?
            )
            WHERE row_number = 1
            ORDER BY trading_date DESC
            LIMIT ?
            """,
            (symbol.strip().upper(), limit),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {"trading_date": row[0], "ltp": row[1]}
        for row in reversed(rows)
    ]


async def add_portfolio_holding(
    telegram_id: int,
    symbol: str,
    quantity: float,
    average_buy_price: float,
) -> None:
    """Add a holding or update an existing holding."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")

    normalized_symbol = symbol.strip().upper()

    for name, value in (
        ("quantity", quantity),
        ("average_buy_price", average_buy_price),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a finite positive number")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        await db.execute(
            """
            INSERT INTO portfolio (
                telegram_id, symbol, quantity, average_buy_price
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id, symbol) DO UPDATE SET
                quantity = excluded.quantity,
                average_buy_price = excluded.average_buy_price,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                telegram_id,
                normalized_symbol,
                quantity,
                average_buy_price,
            ),
        )
        await db.commit()


async def get_portfolio(telegram_id: int) -> list[dict]:
    """Return all stock holdings belonging to one Telegram user."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT symbol, quantity, average_buy_price
            FROM portfolio
            WHERE telegram_id = ?
            ORDER BY symbol
            """,
            (telegram_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def remove_portfolio_holding(
    telegram_id: int,
    symbol: str,
) -> bool:
    """Remove one holding belonging to one Telegram user."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        cursor = await db.execute(
            """
            DELETE FROM portfolio
            WHERE telegram_id = ? AND symbol = ?
            """,
            (telegram_id, symbol.strip().upper()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def save_portfolio_daily_snapshot(
    telegram_id: int,
    snapshot_date: str,
    total_investment: float,
    current_value: float,
    holdings_count: int,
) -> None:
    """Save or update one user's daily portfolio snapshot."""
    for name, value in (
        ("total_investment", total_investment),
        ("current_value", current_value),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{name} must be a finite non-negative number")

    if (
        isinstance(holdings_count, bool)
        or not isinstance(holdings_count, int)
        or holdings_count < 0
    ):
        raise ValueError("holdings_count must be a non-negative integer")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        await db.execute(
            """
            INSERT INTO portfolio_daily_snapshots (
                telegram_id,
                snapshot_date,
                total_investment,
                current_value,
                holdings_count
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id, snapshot_date) DO UPDATE SET
                total_investment = excluded.total_investment,
                current_value = excluded.current_value,
                holdings_count = excluded.holdings_count,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                telegram_id,
                snapshot_date,
                total_investment,
                current_value,
                holdings_count,
            ),
        )
        await db.commit()


async def get_portfolio_daily_snapshots(
    telegram_id: int,
    limit: int = 30,
) -> list[dict]:
    """Return the user's latest daily portfolio snapshots."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT
                snapshot_date,
                total_investment,
                current_value,
                holdings_count
            FROM portfolio_daily_snapshots
            WHERE telegram_id = ?
            ORDER BY snapshot_date DESC
            LIMIT ?
            """,
            (telegram_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_stock_price_alert(
    telegram_id: int,
    symbol: str,
    condition: str,
    target_price: float,
) -> int:
    """Create a stock price alert and return its ID."""
    if condition not in ("above", "below"):
        raise ValueError("Condition must be above or below")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        cursor = await db.execute(
            """
            INSERT INTO stock_price_alerts (
                telegram_id, symbol, condition, target_price
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                telegram_id,
                symbol.strip().upper(),
                condition,
                target_price,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_stock_price_alerts(
    telegram_id: int,
    active_only: bool = True,
) -> list[dict]:
    """Retrieve alerts belonging to one Telegram user."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row

        if active_only:
            query = """
                SELECT id, symbol, condition, target_price,
                       status, created_at
                FROM stock_price_alerts
                WHERE telegram_id = ? AND status = 'active'
                ORDER BY id DESC
            """
        else:
            query = """
                SELECT id, symbol, condition, target_price,
                       status, created_at
                FROM stock_price_alerts
                WHERE telegram_id = ?
                ORDER BY id DESC
            """

        async with db.execute(query, (telegram_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def trigger_stock_price_alert(alert_id: int) -> bool:
    """Mark an active alert as triggered exactly once."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        cursor = await db.execute(
            """
            UPDATE stock_price_alerts
            SET status = 'triggered',
                triggered_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'active'
            """,
            (alert_id,),
        )
        await db.commit()
        return cursor.rowcount == 1


async def remove_stock_price_alert(
    telegram_id: int,
    alert_id: int,
) -> bool:
    """Cancel an alert belonging to its owner."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        cursor = await db.execute(
            """
            UPDATE stock_price_alerts
            SET status = 'cancelled'
            WHERE id = ? AND telegram_id = ? AND status = 'active'
            """,
            (alert_id, telegram_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def get_all_active_stock_price_alerts() -> list[dict]:
    """Retrieve all active alerts for the background checker."""
    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT id, telegram_id, symbol, condition, target_price
            FROM stock_price_alerts
            WHERE status = 'active'
            ORDER BY id ASC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]




def calculate_equity_transaction_fees(
    quantity: float,
    price: float,
    transaction_type: str,
) -> dict:
    """Estimate NEPSE equity transaction charges."""
    if transaction_type not in ("buy", "sell"):
        raise ValueError("Transaction type must be buy or sell.")

    for name, value in (("quantity", quantity), ("price", price)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a positive finite number.")

    trade_value = Decimal(str(quantity)) * Decimal(str(price))

    if trade_value <= 50_000:
        rate = Decimal("0.0036")
    elif trade_value <= 500_000:
        rate = Decimal("0.0033")
    elif trade_value <= 2_000_000:
        rate = Decimal("0.0031")
    elif trade_value <= 10_000_000:
        rate = Decimal("0.0027")
    else:
        rate = Decimal("0.0024")

    round_money = lambda amount: amount.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    commission = max(Decimal("10"), trade_value * rate)
    sebon_fee = trade_value * Decimal("0.00015")
    dp_charge = Decimal("25") if transaction_type == "sell" else Decimal("0")

    commission = round_money(commission)
    sebon_fee = round_money(sebon_fee)
    dp_charge = round_money(dp_charge)

    total_fees = commission + sebon_fee + dp_charge

    return {
        "trade_value": float(round_money(trade_value)),
        "broker_commission": float(commission),
        "sebon_fee": float(sebon_fee),
        "dp_charge": float(dp_charge),
        "total_fees": float(total_fees),
    }

async def record_portfolio_transaction(
    telegram_id: int,
    symbol: str,
    transaction_type: str,
    quantity: float,
    price: float,
    fees: float | None = None,
) -> dict:
    """Record a buy or sell and update the holding atomically."""
    if (
        isinstance(telegram_id, bool)
        or not isinstance(telegram_id, int)
        or telegram_id <= 0
    ):
        raise ValueError("Telegram ID must be a positive integer.")

    if not isinstance(symbol, str) or not symbol.strip() or not symbol.strip().isalnum():
        raise ValueError("Invalid stock symbol.")

    symbol = symbol.strip().upper()

    if transaction_type not in ("buy", "sell"):
        raise ValueError("Transaction type must be buy or sell.")

    for name, value in (("quantity", quantity), ("price", price)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a positive finite number.")

    if fees is not None and (
        isinstance(fees, bool)
        or not isinstance(fees, (int, float))
        or not math.isfinite(fees)
        or fees < 0
    ):
        raise ValueError("Fees must be a non-negative finite number.")

    quantity = float(quantity)
    price = float(price)

    fee_breakdown = calculate_equity_transaction_fees(
        quantity, price, transaction_type
    ) if fees is None else {
        "trade_value": quantity * price,
        "broker_commission": float(fees),
        "sebon_fee": 0.0,
        "dp_charge": 0.0,
        "total_fees": float(fees),
    }
    fees = fee_breakdown["total_fees"]

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        await db.execute("BEGIN IMMEDIATE")

        try:
            async with db.execute(
                """
                SELECT quantity, average_buy_price
                FROM portfolio
                WHERE telegram_id = ? AND symbol = ?
                """,
                (telegram_id, symbol),
            ) as cursor:
                holding = await cursor.fetchone()

            realized_profit_loss = None

            if transaction_type == "buy":
                old_quantity = holding[0] if holding else 0.0
                old_average = holding[1] if holding else 0.0

                new_quantity = old_quantity + quantity
                new_average = (
                    old_quantity * old_average + quantity * price + fees
                ) / new_quantity

                await db.execute(
                    """
                    INSERT INTO portfolio (
                        telegram_id, symbol, quantity, average_buy_price
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(telegram_id, symbol)
                    DO UPDATE SET
                        quantity = excluded.quantity,
                        average_buy_price = excluded.average_buy_price,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (telegram_id, symbol, new_quantity, new_average),
                )

            else:
                if holding is None:
                    raise ValueError("You do not own this stock.")

                old_quantity, average_price = holding

                if quantity > old_quantity and not math.isclose(
                    quantity, old_quantity, rel_tol=1e-12, abs_tol=1e-12
                ):
                    raise ValueError("You cannot sell more shares than you own.")

                remaining = max(0.0, old_quantity - quantity)

                realized_profit_loss = (
                    quantity * price - fees - quantity * average_price
                )

                if math.isclose(remaining, 0.0, abs_tol=1e-12):
                    await db.execute(
                        """
                        DELETE FROM portfolio
                        WHERE telegram_id = ? AND symbol = ?
                        """,
                        (telegram_id, symbol),
                    )
                else:
                    await db.execute(
                        """
                        UPDATE portfolio
                        SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE telegram_id = ? AND symbol = ?
                        """,
                        (remaining, telegram_id, symbol),
                    )

            await db.execute(
                """
                INSERT INTO portfolio_transactions (
                    telegram_id, symbol, transaction_type,
                    quantity, price, fees,
                    broker_commission, sebon_fee, dp_charge,
                    realized_profit_loss
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    symbol,
                    transaction_type,
                    quantity,
                    price,
                    fees,
                    fee_breakdown["broker_commission"],
                    fee_breakdown["sebon_fee"],
                    fee_breakdown["dp_charge"],
                    realized_profit_loss,
                ),
            )

            await db.commit()

            return {
                "symbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "fee_breakdown": fee_breakdown,
                "realized_profit_loss": realized_profit_loss,
            }

        except Exception:
            await db.rollback()
            raise


async def get_portfolio_transactions(
    telegram_id: int,
    limit: int = 20,
) -> list[dict]:
    """Retrieve the latest transactions belonging to one user."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Limit must be a positive integer.")

    async with aiosqlite.connect(settings.database_path, timeout=30) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT id, symbol, transaction_type, quantity, price,
                   fees, broker_commission, sebon_fee, dp_charge,
                   realized_profit_loss, created_at
            FROM portfolio_transactions
            WHERE telegram_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (telegram_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
