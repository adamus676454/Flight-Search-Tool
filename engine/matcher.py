"""
engine/matcher.py – SQL-based matcher that JOINs outbound and inbound one-way
                    flight legs from SQLite into combined round-trip offers.

Matching rules:
  1. dest_metro_group(outbound) == orig_metro_group(inbound)
     E.g. land at FCO, return from CIA (both ROME) ✓
          land at CTA, return from CIY (both SICILY_EAST) ✓
          land at BGY, return from FCO ✗ (MILAN ≠ ROME)

  2. Return airport in Poland:
     a) Same airport:  out.orig_airport == ret.dest_airport
     b) Flexible (checkbox): ret.dest_airport IN (user's origin group)

  3. Nights = julianday(ret.flight_date) - julianday(out.flight_date)
     must be between min_nights and max_nights (inclusive).

  4. Both legs must have currency = 'EUR'.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

WEEKDAY_MAP = {0: "Pn", 1: "Wt", 2: "Śr", 3: "Cz", 4: "Pt", 5: "Sb", 6: "Nd"}
WEEKDAY_INDEX_MAP = {
    "Pn": 0, "Wt": 1, "Śr": 2, "Cz": 3, "Pt": 4, "Sb": 5, "Nd": 6,
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6,
}


def match_roundtrips(
    conn: sqlite3.Connection,
    origin_airports: list[str],
    min_nights: int = 2,
    max_nights: int = 14,
    allow_different_return_airport: bool = False,
    max_price_eur: float | None = None,
    direct_only: bool = False,
    airlines_filter: list[str] | None = None,
    query_hashes_outbound: list[str] | None = None,
    query_hashes_inbound: list[str] | None = None,
    out_date_from: str | None = None,
    out_date_to: str | None = None,
    ret_date_from: str | None = None,
    ret_date_to: str | None = None,
    out_weekdays: list[str] | None = None,
    ret_weekdays: list[str] | None = None,
    dest_airports: list[str] | None = None,
    is_mock: bool | None = None,
) -> list[dict]:
    """Run the SQL JOIN matcher and return combined round-trip results.

    Parameters
    ----------
    conn : sqlite3.Connection
    origin_airports : list[str]
        The set of origin airports the user selected (e.g. ["KRK", "KTW"]).
    min_nights, max_nights : int
        Acceptable stay length in nights.
    allow_different_return_airport : bool
        If True, the return can land at any airport in *origin_airports*.
        If False, return must land at the same airport the outbound departed from.
    max_price_eur : float | None
        Total price cap (outbound + inbound).
    direct_only : bool
        If True, both legs must have stops = 0.
    airlines_filter : list[str] | None
        If set, at least one leg must match one of these airline names (substring).
    query_hashes_outbound / query_hashes_inbound : list[str] | None
        Restrict matching to specific cached queries.
    """

    # Build WHERE fragments with isolated parameter lists
    conditions_out = ["o.direction = 'outbound'", "o.currency = 'EUR'"]
    conditions_ret = ["r.direction = 'inbound'", "r.currency = 'EUR'"]
    params_out: list = []
    params_ret: list = []

    # Origin airports for outbound
    placeholders_orig = ",".join("?" for _ in origin_airports)
    conditions_out.append(f"o.orig_airport IN ({placeholders_orig})")
    params_out.extend(origin_airports)

    # Return destination
    if allow_different_return_airport:
        conditions_ret.append(f"r.dest_airport IN ({placeholders_orig})")
        params_ret.extend(origin_airports)
    # else: handled via JOIN condition (o.orig_airport = r.dest_airport)

    # Direct only
    if direct_only:
        conditions_out.append("o.stops = 0")
        conditions_ret.append("r.stops = 0")

    # Query hash filters
    if query_hashes_outbound:
        ph = ",".join("?" for _ in query_hashes_outbound)
        conditions_out.append(f"o.query_hash IN ({ph})")
        params_out.extend(query_hashes_outbound)

    if query_hashes_inbound:
        ph = ",".join("?" for _ in query_hashes_inbound)
        conditions_ret.append(f"r.query_hash IN ({ph})")
        params_ret.extend(query_hashes_inbound)

    # Destination airports filter in SQL (applied before LIMIT 500)
    if dest_airports:
        ph_dest = ",".join("?" for _ in dest_airports)
        conditions_out.append(f"o.dest_airport IN ({ph_dest})")
        params_out.extend(dest_airports)
        conditions_ret.append(f"r.orig_airport IN ({ph_dest})")
        params_ret.extend(dest_airports)

    # Date range filters in SQL (applied before LIMIT 500)
    if out_date_from:
        conditions_out.append("o.flight_date >= ?")
        params_out.append(out_date_from)
    if out_date_to:
        conditions_out.append("o.flight_date <= ?")
        params_out.append(out_date_to)
    if ret_date_from:
        conditions_ret.append("r.flight_date >= ?")
        params_ret.append(ret_date_from)
    if ret_date_to:
        conditions_ret.append("r.flight_date <= ?")
        params_ret.append(ret_date_to)

    # Mock mode filter in SQL (applied before LIMIT 500)
    if is_mock is not None:
        conditions_out.append("o.is_mock = ?")
        params_out.append(1 if is_mock else 0)
        conditions_ret.append("r.is_mock = ?")
        params_ret.append(1 if is_mock else 0)

    # Combine params strictly in the order of SQL placeholders:
    # 1. conditions_out params, 2. conditions_ret params, 3. min_nights, 4. max_nights
    params = params_out + params_ret + [min_nights, max_nights]

    origin_join = (
        ""  # flexible: already filtered in WHERE
        if allow_different_return_airport
        else "AND o.orig_airport = r.dest_airport"
    )

    sql = f"""
        SELECT
            o.price_eur + r.price_eur                     AS total_eur,
            o.price_eur                                    AS price_out_eur,
            r.price_eur                                    AS price_ret_eur,
            o.orig_airport                                 AS out_orig,
            o.dest_airport                                 AS out_dest,
            o.flight_date                                  AS out_date,
            o.departure_time                               AS out_dep_time,
            o.arrival_time                                 AS out_arr_time,
            o.airline                                      AS out_airline,
            o.flight_no                                    AS out_flight_no,
            o.stops                                        AS out_stops,
            o.dest_metro_group                             AS out_dest_metro,
            r.orig_airport                                 AS ret_orig,
            r.dest_airport                                 AS ret_dest,
            r.flight_date                                  AS ret_date,
            r.departure_time                               AS ret_dep_time,
            r.arrival_time                                 AS ret_arr_time,
            r.airline                                      AS ret_airline,
            r.flight_no                                    AS ret_flight_no,
            r.stops                                        AS ret_stops,
            r.orig_metro_group                             AS ret_orig_metro,
            CAST(julianday(r.flight_date) - julianday(o.flight_date) AS INTEGER) AS nights,
            o.is_mock OR r.is_mock                         AS is_mock,
            o.provider                                     AS out_provider,
            r.provider                                     AS ret_provider,
            o.fetched_at                                   AS out_fetched_at,
            r.fetched_at                                   AS ret_fetched_at
        FROM flights o
        JOIN flights r
          ON  o.dest_metro_group = r.orig_metro_group
          {origin_join}
        WHERE {' AND '.join(conditions_out)}
          AND {' AND '.join(conditions_ret)}
          AND CAST(julianday(r.flight_date) - julianday(o.flight_date) AS INTEGER) >= ?
          AND CAST(julianday(r.flight_date) - julianday(o.flight_date) AS INTEGER) <= ?
        ORDER BY total_eur ASC
        LIMIT 500
    """

    cur = conn.execute(sql, params)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    # Post-SQL filters: Weekdays (supporting both PL and EN weekday names)
    if out_weekdays:
        allowed_out = {WEEKDAY_INDEX_MAP[wd] for wd in out_weekdays if wd in WEEKDAY_INDEX_MAP}
        valid_rows = []
        for r in rows:
            try:
                wd_idx = datetime.strptime(r["out_date"], "%Y-%m-%d").weekday()
                if wd_idx in allowed_out:
                    valid_rows.append(r)
            except (ValueError, TypeError):
                valid_rows.append(r)
        rows = valid_rows

    if ret_weekdays:
        allowed_ret = {WEEKDAY_INDEX_MAP[wd] for wd in ret_weekdays if wd in WEEKDAY_INDEX_MAP}
        valid_rows = []
        for r in rows:
            try:
                wd_idx = datetime.strptime(r["ret_date"], "%Y-%m-%d").weekday()
                if wd_idx in allowed_ret:
                    valid_rows.append(r)
            except (ValueError, TypeError):
                valid_rows.append(r)
        rows = valid_rows

    # Post-SQL filters: Price cap
    if max_price_eur is not None:
        rows = [r for r in rows if r["total_eur"] <= max_price_eur]

    # Post-SQL filters: Airlines
    if airlines_filter:
        lower_filters = [a.lower() for a in airlines_filter]
        rows = [
            r
            for r in rows
            if any(
                af in (r.get("out_airline") or "").lower()
                or af in (r.get("ret_airline") or "").lower()
                for af in lower_filters
            )
        ]

    return rows
