"""One-shot repair: deduplicate backtest signals, mark the latest run
COMPLETE with the correct counts so the UI can read its stats, and
clear stale zombie 'running' rows from previous backend restarts.

Run from the backend directory:
    python repair_backtest_state.py
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB = os.environ.get("DB_PATH", str(Path(__file__).parent / "backtest" / "quant_backtest.db"))


def main() -> None:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=WAL")
    c = con.cursor()

    print("=" * 70)
    print("BEFORE")
    print("=" * 70)
    total = c.execute("SELECT COUNT(*) FROM backtest_signals").fetchone()[0]
    distinct = c.execute("SELECT COUNT(DISTINCT stock) FROM backtest_signals").fetchone()[0]
    dups = c.execute(
        "SELECT COUNT(*) FROM (SELECT stock, date FROM backtest_signals GROUP BY stock, date HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    print(f"  total signals: {total:,}")
    print(f"  distinct stocks: {distinct}")
    print(f"  duplicate (stock,date) groups: {dups:,}")

    print("  recent runs:")
    for r in c.execute(
        "SELECT id, status, run_id_external, total_signals FROM backtest_runs ORDER BY id DESC LIMIT 5"
    ).fetchall():
        print(f"    {r}")

    # ── Step 1: deduplicate signals — keep the highest rowid (most recent) per (stock,date)
    print()
    print("Step 1: deduplicating signals...")
    c.execute(
        """DELETE FROM backtest_signals
           WHERE id NOT IN (
             SELECT MAX(id) FROM backtest_signals GROUP BY stock, date
           )"""
    )
    removed = c.rowcount
    print(f"  removed {removed:,} duplicate signal rows")
    con.commit()

    # ── Step 2: cancel zombie 'running' run rows from previous restarts
    print()
    print("Step 2: cancelling zombie 'running' runs...")
    c.execute("UPDATE backtest_runs SET status = 'cancelled' WHERE status = 'running'")
    print(f"  cancelled {c.rowcount} zombie run rows")
    con.commit()

    # ── Step 3: identify the run with the most completed stocks; mark it COMPLETE
    print()
    print("Step 3: marking the most-completed run as COMPLETE...")
    row = c.execute(
        """SELECT run_id, COUNT(*) AS done
             FROM backtest_progress
            WHERE status = 'completed'
            GROUP BY run_id
            ORDER BY done DESC
            LIMIT 1"""
    ).fetchone()
    if not row:
        print("  no completed-stock data in backtest_progress; nothing to mark")
    else:
        winning_run_id, done = row
        signal_count = c.execute("SELECT COUNT(*) FROM backtest_signals").fetchone()[0]
        date_min, date_max = c.execute("SELECT MIN(date), MAX(date) FROM backtest_signals").fetchone()
        print(f"  winning run_id: {winning_run_id}  (completed {done} stocks, {signal_count:,} signals after dedupe)")
        print(f"  date range: {date_min} -> {date_max}")

        # Update existing run row if present, else insert one for this run_id
        existing = c.execute(
            "SELECT id FROM backtest_runs WHERE run_id_external = ? LIMIT 1",
            (winning_run_id,),
        ).fetchone()
        if existing:
            c.execute(
                """UPDATE backtest_runs SET
                     stocks_processed = ?,
                     total_signals    = ?,
                     status           = 'complete',
                     date_range_start = ?,
                     date_range_end   = ?
                   WHERE run_id_external = ?""",
                (done, signal_count, date_min, date_max, winning_run_id),
            )
            print(f"  updated existing backtest_runs row")
        else:
            c.execute(
                """INSERT INTO backtest_runs
                     (run_date, stocks_processed, total_signals, date_range_start,
                      date_range_end, status, duration_seconds, run_id_external)
                   VALUES (datetime('now'), ?, ?, ?, ?, 'complete', NULL, ?)""",
                (done, signal_count, date_min, date_max, winning_run_id),
            )
            print(f"  inserted new backtest_runs row")
    con.commit()

    print()
    print("=" * 70)
    print("AFTER")
    print("=" * 70)
    total2 = c.execute("SELECT COUNT(*) FROM backtest_signals").fetchone()[0]
    distinct2 = c.execute("SELECT COUNT(DISTINCT stock) FROM backtest_signals").fetchone()[0]
    dups2 = c.execute(
        "SELECT COUNT(*) FROM (SELECT stock, date FROM backtest_signals GROUP BY stock, date HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    print(f"  total signals: {total2:,}")
    print(f"  distinct stocks: {distinct2}")
    print(f"  duplicate (stock,date) groups: {dups2}")
    print("  most recent runs:")
    for r in c.execute(
        "SELECT id, status, run_id_external, total_signals, date_range_start, date_range_end FROM backtest_runs ORDER BY id DESC LIMIT 5"
    ).fetchall():
        print(f"    {r}")

    print()
    print("Reclaiming free space (VACUUM)...")
    con.commit()
    con.execute("VACUUM")
    print("  done")
    con.close()
    print()
    print("RESTART the backend so the in-memory full-results cache is cleared.")


if __name__ == "__main__":
    main()
