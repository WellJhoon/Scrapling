import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "data" / "exchange_rates.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                date TEXT PRIMARY KEY,               -- Formato YYYY-MM-DD
                source TEXT NOT NULL,                -- 'BCRD' o 'DGII'
                currency TEXT NOT NULL DEFAULT 'USD',-- 'USD', 'EUR'
                purchase_rate REAL NOT NULL,         -- Tasa Compra
                selling_rate REAL NOT NULL,          -- Tasa Venta
                purchase_delta_interanual REAL,      -- Variación interanual compra %
                selling_delta_interanual REAL,       -- Variación interanual venta %
                created_at TEXT NOT NULL             -- Timestamp de inserción
            )
        """)
        conn.commit()

def upsert_rate(
    date_str: str,
    purchase_rate: float,
    selling_rate: float,
    source: str = "BCRD",
    currency: str = "USD",
    purchase_delta_interanual: Optional[float] = None,
    selling_delta_interanual: Optional[float] = None,
) -> bool:
    now_iso = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exchange_rates (
                date, source, currency, purchase_rate, selling_rate,
                purchase_delta_interanual, selling_delta_interanual, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                purchase_rate = excluded.purchase_rate,
                selling_rate = excluded.selling_rate,
                purchase_delta_interanual = excluded.purchase_delta_interanual,
                selling_delta_interanual = excluded.selling_delta_interanual,
                created_at = excluded.created_at
        """, (
            date_str, source, currency, purchase_rate, selling_rate,
            purchase_delta_interanual, selling_delta_interanual, now_iso
        ))
        conn.commit()
        return True

def get_latest_rate(currency: str = "USD") -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM exchange_rates
            WHERE currency = ?
            ORDER BY date DESC
            LIMIT 1
        """, (currency,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_rate_by_date(date_str: str, currency: str = "USD") -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM exchange_rates
            WHERE date = ? AND currency = ?
            LIMIT 1
        """, (date_str, currency))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_rates_history(from_date: Optional[str] = None, to_date: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM exchange_rates WHERE 1=1"
        params = []
        if from_date:
            query += " AND date >= ?"
            params.append(from_date)
        if to_date:
            query += " AND date <= ?"
            params.append(to_date)
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
