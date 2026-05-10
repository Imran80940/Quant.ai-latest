"""Database initialization and connection management.

Single SQLite file holds all Phase 2 data — backtest signals, runs,
paper trades, scans, learning insights, and engine config.
"""

from __future__ import annotations

import os

import aiosqlite

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "quant_backtest.db"),
)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS backtest_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock TEXT NOT NULL,
    date TEXT NOT NULL,
    score REAL,
    rsi REAL,
    macd_hist REAL,
    macd_cross INTEGER,
    adx REAL,
    bb_squeeze INTEGER,
    ema_above_count INTEGER,
    obv_trend TEXT,
    volume_ratio REAL,
    supertrend_bullish INTEGER,
    vwap_above INTEGER,
    close_price REAL,
    forward_return_1d REAL,
    forward_return_5d REAL,
    forward_return_20d REAL
);
CREATE INDEX IF NOT EXISTS idx_signals_score ON backtest_signals(score);
CREATE INDEX IF NOT EXISTS idx_signals_date  ON backtest_signals(date);
CREATE INDEX IF NOT EXISTS idx_signals_stock ON backtest_signals(stock);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT,
    stocks_processed INTEGER DEFAULT 0,
    total_signals INTEGER DEFAULT 0,
    date_range_start TEXT,
    date_range_end TEXT,
    status TEXT DEFAULT 'running',
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id TEXT PRIMARY KEY,
    stock TEXT NOT NULL,
    trade_type TEXT DEFAULT 'LONG',
    entry_price REAL,
    entry_time TEXT,
    target_1 REAL,
    target_2 REAL,
    stop_loss REAL,
    horizon TEXT,
    ai_bias TEXT,
    ai_confidence INTEGER,
    ai_conviction TEXT,
    ai_reasons TEXT,
    score_at_entry REAL,
    indicators_at_entry TEXT,
    status TEXT DEFAULT 'ACTIVE',
    exit_price REAL,
    exit_time TEXT,
    exit_reason TEXT,
    result TEXT,
    pnl_pct REAL,
    created_date TEXT,
    sector TEXT,
    name TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_status      ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created     ON paper_trades(created_date);
CREATE INDEX IF NOT EXISTS idx_trades_exit_time   ON paper_trades(exit_time);

CREATE TABLE IF NOT EXISTS paper_trading_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_time TEXT,
    mode TEXT,
    candidates_found INTEGER,
    trades_placed INTEGER,
    stocks_scanned TEXT,
    reason_summary TEXT
);

CREATE TABLE IF NOT EXISTS learning_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_date TEXT,
    trades_analyzed INTEGER,
    win_rate REAL,
    avg_pnl REAL,
    confidence_ic REAL,
    ai_insight TEXT,
    threshold_before INTEGER,
    threshold_after INTEGER
);

CREATE TABLE IF NOT EXISTS engine_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

-- ── RULE 7: Rejection logging — every rejection is research data ──
CREATE TABLE IF NOT EXISTS scan_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock TEXT,
    scan_time TEXT,
    horizon TEXT,
    ai_confidence REAL,
    threshold_at_time INTEGER,
    reject_reason TEXT,
    score_at_rejection REAL,
    indicators_snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_rej_time   ON scan_rejections(scan_time);
CREATE INDEX IF NOT EXISTS idx_rej_stock  ON scan_rejections(stock);

-- ── Research Infrastructure: per-stock checkpointing ──────────────────
CREATE TABLE IF NOT EXISTS backtest_progress (
    run_id        TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    started_at    TEXT,
    completed_at  TEXT,
    signal_count  INTEGER DEFAULT 0,
    error         TEXT,
    PRIMARY KEY (run_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_bp_run_status ON backtest_progress(run_id, status);

-- ── Research Infrastructure: structured failure log ───────────────────
CREATE TABLE IF NOT EXISTS backtest_failures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    symbol      TEXT,
    stage       TEXT,
    traceback   TEXT,
    memory_mb   REAL,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_bf_run    ON backtest_failures(run_id);
CREATE INDEX IF NOT EXISTS idx_bf_stage  ON backtest_failures(stage);

-- ── Research Infrastructure: post-run validation report ───────────────
CREATE TABLE IF NOT EXISTS backtest_validation_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    passed      INTEGER,
    checks_json TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_bv_run ON backtest_validation_reports(run_id);
"""


# Migrations for older DBs that may already exist without the new columns.
MIGRATIONS_SQL = [
    "ALTER TABLE scan_rejections ADD COLUMN indicators_snapshot TEXT",
    "ALTER TABLE scan_rejections ADD COLUMN score_at_rejection REAL",
    "ALTER TABLE backtest_runs   ADD COLUMN run_id_external TEXT",
]


async def init_db() -> None:
    """Create all tables + run idempotent migrations + WAL pragma (RULE 5)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # RULE 5: WAL mode for concurrent read/write across async + threadpool
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=10000")
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()

        # Idempotent column-add migrations (older DBs)
        for sql in MIGRATIONS_SQL:
            try:
                await db.execute(sql)
            except Exception:  # noqa: BLE001
                pass  # column already exists
        await db.commit()

        defaults = [
            ("confidence_threshold", "65"),
            ("engine_status", "idle"),
            ("last_scan_time", ""),
            ("total_trades", "0"),
            ("total_wins", "0"),
            ("engine_running", "false"),
        ]
        for key, value in defaults:
            await db.execute(
                "INSERT OR IGNORE INTO engine_config (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, value),
            )
        await db.commit()


# ── RULE: Nightly integrity check ──────────────────────────────────────
async def run_nightly_integrity_check() -> list[str]:
    """Detect zombie active trades, invalid prices, broken stop-losses.
    Stores findings in engine_config so the research lab can surface them.
    """
    from datetime import datetime
    import pytz
    IST = pytz.timezone("Asia/Kolkata")

    issues: list[str] = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now_ist = datetime.now(IST)

        # 1. Zombie ACTIVE trades >8h old
        async with db.execute(
            "SELECT trade_id, stock, entry_time FROM paper_trades WHERE status='ACTIVE'"
        ) as cur:
            for row in await cur.fetchall():
                try:
                    entry_dt = datetime.fromisoformat(row["entry_time"])
                    if entry_dt.tzinfo is None:
                        entry_dt = IST.localize(entry_dt)
                    age_h = (now_ist - entry_dt).total_seconds() / 3600.0
                    if age_h > 8:
                        issues.append(f"ZOMBIE TRADE {row['stock']}: open {age_h:.1f}h")
                except Exception:  # noqa: BLE001
                    pass

        # 2. Corrupt entry prices
        async with db.execute("SELECT COUNT(*) FROM paper_trades WHERE entry_price <= 0") as cur:
            n = (await cur.fetchone())[0]
            if n: issues.append(f"CORRUPT TRADES: {n} with entry_price <= 0")

        # 3. Invalid stop loss (>= entry for LONG)
        async with db.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE stop_loss >= entry_price AND trade_type='LONG'"
        ) as cur:
            n = (await cur.fetchone())[0]
            if n: issues.append(f"INVALID SL: {n} LONG trades with SL >= entry")

        if issues:
            await db.execute(
                """INSERT INTO engine_config (key, value, updated_at) VALUES (?, ?, datetime('now'))
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (f"integrity_alert_{now_ist.strftime('%Y%m%d')}", "\n".join(issues)),
            )
        await db.commit()

    return issues


async def get_config(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT value FROM engine_config WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""


async def set_config(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO engine_config (key, value, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = excluded.updated_at""",
            (key, value),
        )
        await db.commit()
