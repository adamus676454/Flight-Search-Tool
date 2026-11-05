"""
engine/db.py – SQLite cache and flight storage.

Tables:
  - flights:      individual flight legs (one-way segments)
  - query_cache:  hash-based cache tracking per query
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "flights.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Return a connection to the local SQLite database, creating tables if needed."""
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS flights (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            provider        TEXT    NOT NULL,           -- 'serpapi_gf' | 'kiwi_mcp' | 'mock'
            direction       TEXT    NOT NULL,           -- 'outbound' | 'inbound' | 'roundtrip'
            orig_airport    TEXT    NOT NULL,
            dest_airport    TEXT    NOT NULL,
            orig_metro_group TEXT   NOT NULL,
            dest_metro_group TEXT   NOT NULL,
            flight_date     TEXT    NOT NULL,           -- ISO date YYYY-MM-DD
            departure_time  TEXT,                        -- HH:MM
            arrival_time    TEXT,                        -- HH:MM
            airline         TEXT,
            flight_no       TEXT,
            price_eur       REAL    NOT NULL,
            currency        TEXT    NOT NULL DEFAULT 'EUR',
            stops           INTEGER NOT NULL DEFAULT 0,
            duration_min    INTEGER,
            booking_token   TEXT,
            raw_json        TEXT,
            query_hash      TEXT    NOT NULL,
            fetched_at      TEXT    NOT NULL,           -- ISO datetime UTC
            is_mock         INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_flights_query_hash ON flights(query_hash);
        CREATE INDEX IF NOT EXISTS idx_flights_direction  ON flights(direction);
        CREATE INDEX IF NOT EXISTS idx_flights_date       ON flights(flight_date);
        CREATE INDEX IF NOT EXISTS idx_flights_metro      ON flights(dest_metro_group, orig_metro_group);

        CREATE TABLE IF NOT EXISTS query_cache (
            query_hash   TEXT    PRIMARY KEY,
            provider     TEXT    NOT NULL,
            params_json  TEXT    NOT NULL,
            result_count INTEGER NOT NULL DEFAULT 0,
            fetched_at   TEXT    NOT NULL,
            is_mock      INTEGER NOT NULL DEFAULT 0
        );
    """)
    try:
        conn.execute("ALTER TABLE flights ADD COLUMN raw_json TEXT")
    except Exception:
        pass
    conn.commit()


# ---------------------------------------------------------------------------
# Cache key generation
# ---------------------------------------------------------------------------
ADAPTER_VERSION = "v1"


def compute_query_hash(provider: str, params: dict) -> str:
    """Deterministic hash from provider name + sorted params + currency + adapter version."""
    canonical = json.dumps(
        {"provider": provider, "params": params, "currency": "EUR", "adapter": ADAPTER_VERSION},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Cache lookup
# ---------------------------------------------------------------------------
def is_cache_valid(conn: sqlite3.Connection, query_hash: str, ttl_hours: int = 24) -> bool:
    """Check if a cached result exists and is younger than *ttl_hours*."""
    row = conn.execute(
        "SELECT fetched_at FROM query_cache WHERE query_hash = ?",
        (query_hash,),
    ).fetchone()
    if row is None:
        return False
    fetched_at = datetime.fromisoformat(row[0])
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at < timedelta(hours=ttl_hours)


def get_cached_flights(conn: sqlite3.Connection, query_hash: str) -> list[dict]:
    """Return cached flight rows as dicts (may be empty list)."""
    cur = conn.execute(
        "SELECT * FROM flights WHERE query_hash = ?",
        (query_hash,),
    )
    columns = [desc[0] for desc in cur.description]
    results = []
    for row in cur.fetchall():
        row_dict = dict(zip(columns, row))
        raw_val = row_dict.get("raw_json")
        if raw_val:
            try:
                extra = json.loads(raw_val)
                if isinstance(extra, dict):
                    row_dict = {**row_dict, **extra}
            except Exception:
                pass
        results.append(row_dict)
    return results


# ---------------------------------------------------------------------------
# Storing results
# ---------------------------------------------------------------------------
def store_flights(
    conn: sqlite3.Connection,
    provider: str,
    params: dict,
    flights: list[dict],
    is_mock: bool = False,
):
    """Persist a list of flight dicts and update the query_cache entry.

    IMPORTANT: Never cache errors or empty results caused by network failures.
    The caller must NOT call this function with error/empty data – this function
    only stores valid flight results.
    """
    query_hash = compute_query_hash(provider, params)
    now_utc = datetime.now(timezone.utc).isoformat()

    # Delete old data for this hash before inserting fresh
    conn.execute("DELETE FROM flights WHERE query_hash = ?", (query_hash,))
    conn.execute("DELETE FROM query_cache WHERE query_hash = ?", (query_hash,))

    for f in flights:
        raw_val = f.get("raw_json")
        if raw_val is None:
            raw_json_str = json.dumps(f)
        elif isinstance(raw_val, str):
            raw_json_str = raw_val
        else:
            raw_json_str = json.dumps(raw_val)

        conn.execute(
            """INSERT INTO flights (
                provider, direction, orig_airport, dest_airport,
                orig_metro_group, dest_metro_group,
                flight_date, departure_time, arrival_time,
                airline, flight_no, price_eur, currency,
                stops, duration_min, booking_token, raw_json,
                query_hash, fetched_at, is_mock
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f.get("provider", provider),
                f.get("direction", "outbound"),
                f["orig_airport"],
                f["dest_airport"],
                f.get("orig_metro_group", ""),
                f.get("dest_metro_group", ""),
                f.get("flight_date") or f.get("outbound_date", ""),
                f.get("departure_time") or f.get("outbound_dep_time"),
                f.get("arrival_time") or f.get("outbound_arr_time"),
                f.get("airline") or f.get("outbound_airline"),
                f.get("flight_no") or f.get("outbound_flight_no"),
                f["price_eur"],
                f.get("currency", "EUR"),
                f.get("stops", 0),
                f.get("duration_min"),
                f.get("booking_token"),
                raw_json_str,
                query_hash,
                now_utc,
                1 if is_mock else 0,
            ),
        )

    conn.execute(
        """INSERT INTO query_cache (query_hash, provider, params_json, result_count, fetched_at, is_mock)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (query_hash, provider, json.dumps(params, sort_keys=True), len(flights), now_utc, 1 if is_mock else 0),
    )
    conn.commit()


def clear_cache(conn: sqlite3.Connection):
    """Remove all cached data."""
    conn.execute("DELETE FROM flights")
    conn.execute("DELETE FROM query_cache")
    conn.commit()
