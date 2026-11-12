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
"""

async def init_db() -> None:
    async with aiosqlite.connect(settings.database_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def save_price_snapshot(stock: dict) -> bool:
    """Save a stock price snapshot once. Return False for duplicates."""
    async with aiosqlite.connect(settings.database_path) as db:
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

    async with aiosqlite.connect(settings.database_path) as db:
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

    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
        async with aiosqlite.connect(settings.database_path) as db:
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

    async with aiosqlite.connect(settings.database_path) as db:
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



async def add_portfolio_holding(
    telegram_id: int,
    symbol: str,
    quantity: float,
    average_buy_price: float,
) -> None:
    """Add a holding or update an existing holding."""
    async with aiosqlite.connect(settings.database_path) as db:
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
                symbol.strip().upper(),
                quantity,
                average_buy_price,
            ),
        )
        await db.commit()


async def get_portfolio(telegram_id: int) -> list[dict]:
    """Return all stock holdings belonging to one Telegram user."""
    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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

    async with aiosqlite.connect(settings.database_path) as db:
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

    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
    async with aiosqlite.connect(settings.database_path) as db:
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
