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


# ---------------------------------------------------------------------------
# Subset & Range Coverage Optimization (Set Inclusion Cache)
# ---------------------------------------------------------------------------
def get_covered_kiwi_dates(
    conn: sqlite3.Connection,
    orig: str,
    dest: str,
    req_nmin: int,
    req_nmax: int,
    ttl_hours: int = 24,
    is_mock: bool = False,
) -> set[str]:
    """Zwraca zbiór dat YYYY-MM-DD, które są już pokryte w ważnym cache dla danej trasy Kiwi."""
    cur = conn.execute(
        "SELECT params_json, fetched_at FROM query_cache WHERE provider = ? AND is_mock = ?",
        ("mock" if is_mock else "kiwi_mcp", 1 if is_mock else 0),
    )
    now_utc = datetime.now(timezone.utc)
    covered: set[str] = set()

    for params_str, fetched_str in cur.fetchall():
        try:
            fetched_dt = datetime.fromisoformat(fetched_str)
            if fetched_dt.tzinfo is None:
                fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
            if now_utc - fetched_dt >= timedelta(hours=ttl_hours):
                continue
            p = json.loads(params_str)
            if p.get("flyFrom") != orig or p.get("flyTo") != dest:
                continue
            c_nmin = int(p.get("nmin", 1))
            c_nmax = int(p.get("nmax", 14))
            # Pokrycie nocy: zapisany zakres nocy musi pokrywać lub być równy żądanemu
            if c_nmin > req_nmin or c_nmax < req_nmax:
                continue
            d_from = datetime.strptime(p["date_from"], "%Y-%m-%d").date()
            d_to = datetime.strptime(p["date_to"], "%Y-%m-%d").date()
            curr = d_from
            while curr <= d_to:
                covered.add(curr.strftime("%Y-%m-%d"))
                curr += timedelta(days=1)
        except Exception:
            continue
    return covered


def compute_uncovered_kiwi_range(
    conn: sqlite3.Connection,
    orig: str,
    dest: str,
    date_from: str,
    date_to: str,
    nmin: int,
    nmax: int,
    ttl_hours: int = 24,
    is_mock: bool = False,
) -> tuple[str, str] | None:
    """
    Oblicza z różnicy zbiorów, o jaki podprzedział dat trzeba jeszcze dopytać Kiwi MCP.
    - Jeśli cały przedział [date_from, date_to] jest już w cache -> zwraca None (0 zapytań!).
    - Jeśli brakuje tylko części (np. 5-7 lutego jest w cache, a szukamy 5-8 lutego) ->
      zwraca ("2027-02-08", "2027-02-08").
    """
    covered = get_covered_kiwi_dates(conn, orig, dest, nmin, nmax, ttl_hours, is_mock)
    d1 = datetime.strptime(date_from, "%Y-%m-%d").date()
    d2 = datetime.strptime(date_to, "%Y-%m-%d").date()
    req_dates: list[str] = []
    curr = d1
    while curr <= d2:
        req_dates.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    missing = [d for d in req_dates if d not in covered]
    if not missing:
        return None
    return (min(missing), max(missing))


def query_flights_by_criteria(
    conn: sqlite3.Connection,
    origins: list[str],
    dests: list[str],
    direction: str | None = None,
    provider: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_mock: bool | None = None,
) -> list[dict]:
    """Pobiera loty z tabeli flights po lotniskach i zakresie dat (rozpakowując raw_json)."""
    if not origins or not dests:
        return []
    orig_ph = ",".join("?" for _ in origins)
    dest_ph = ",".join("?" for _ in dests)
    conds = [f"orig_airport IN ({orig_ph})", f"dest_airport IN ({dest_ph})"]
    params: list = [*origins, *dests]

    if direction:
        conds.append("direction = ?")
        params.append(direction)
    if provider:
        conds.append("provider = ?")
        params.append(provider)
    if date_from:
        conds.append("flight_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("flight_date <= ?")
        params.append(date_to)
    if is_mock is not None:
        conds.append("is_mock = ?")
        params.append(1 if is_mock else 0)

    sql = f"SELECT * FROM flights WHERE {' AND '.join(conds)} ORDER BY price_eur ASC"
    cur = conn.execute(sql, params)
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
