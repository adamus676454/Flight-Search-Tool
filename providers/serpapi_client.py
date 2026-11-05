"""
providers/serpapi_client.py – SerpApi REST client for google_flights & google_travel_explore.

Uses GET https://serpapi.com/search with max_retries=0 and timeout=20.
All HTTP calls go through engine/safety.py circuit breaker.
"""

from __future__ import annotations

import math
from datetime import datetime

from config import CURRENCY, get_metro_group

SERPAPI_BASE_URL = "https://serpapi.com/search"


# ---------------------------------------------------------------------------
# Parameter builders
# ---------------------------------------------------------------------------

def build_google_flights_params(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    return_date: str | None = None,
    trip_type: int = 1,  # 1 = round-trip, 2 = one-way
    api_key: str = "",
    adults: int = 1,
    currency: str = CURRENCY,
    hl: str = "pl",
    gl: str = "pl",
    stops: int | None = None,
) -> dict:
    """Build query params dict for SerpApi google_flights engine.

    departure_id/arrival_id accept up to 6 IATA codes comma-separated.
    """
    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "currency": currency,
        "hl": hl,
        "gl": gl,
        "adults": adults,
        "api_key": api_key,
        "type": trip_type,
    }
    if return_date and trip_type == 1:
        params["return_date"] = return_date
    if stops is not None:
        params["stops"] = stops
    return params


def build_explore_params(
    departure_id: str,
    destination_kgmid: str,
    month: str,  # YYYY-MM format
    api_key: str = "",
    currency: str = CURRENCY,
    hl: str = "pl",
    gl: str = "pl",
    travel_duration: str | None = None,
) -> dict:
    """Build query params dict for SerpApi google_travel_explore engine."""
    params = {
        "engine": "google_travel_explore",
        "departure_id": departure_id,
        "destination_kgmid": destination_kgmid,
        "currency": currency,
        "hl": hl,
        "gl": gl,
        "api_key": api_key,
    }
    # Explore uses travel_start_date, travel_end_date for the month window
    try:
        dt = datetime.strptime(month, "%Y-%m")
        params["travel_start_date"] = dt.strftime("%Y-%m-%d")
        # End of month approximation
        if dt.month == 12:
            end = dt.replace(year=dt.year + 1, month=1)
        else:
            end = dt.replace(month=dt.month + 1)
        params["travel_end_date"] = end.strftime("%Y-%m-%d")
    except ValueError:
        pass

    if travel_duration:
        params["travel_duration"] = travel_duration  # e.g. "3" for weekend, "7", "14"

    return params


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def chunk_airports(airports: list[str], max_per_chunk: int = 6) -> list[list[str]]:
    """Split a list of airport codes into chunks of max 6 for google_flights."""
    return [
        airports[i: i + max_per_chunk]
        for i in range(0, len(airports), max_per_chunk)
    ]


def count_serpapi_queries(
    origin_airports: list[str],
    dest_airports: list[str],
    mode: str = "roundtrip",
    n_date_pairs: int = 1,
) -> int:
    """Calculate how many SerpApi calls are needed for google_flights.

    google_flights supports up to 6 airports per departure_id and arrival_id.
    """
    origin_chunks = math.ceil(len(origin_airports) / 6)
    dest_chunks = math.ceil(len(dest_airports) / 6)
    base = origin_chunks * dest_chunks

    if mode == "oneway_pair":
        return base * 2 * n_date_pairs  # outbound + inbound per date pair
    return base * n_date_pairs


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_google_flights_response(
    data: dict,
    direction: str = "outbound",
    query_date: str = "",
) -> list[dict]:
    """Parse google_flights SerpApi response into normalised flight dicts.

    Parameters
    ----------
    data : dict
        Raw JSON response from SerpApi.
    direction : str
        'outbound', 'inbound', or 'roundtrip'.
    query_date : str
        The outbound_date used in the query (for context).

    Returns list of flight dicts ready for DB storage.
    """
    flights = []

    # google_flights returns best_flights + other_flights
    all_results = data.get("best_flights", []) + data.get("other_flights", [])

    for result in all_results:
        legs = result.get("flights", [])
        if not legs:
            continue

        # Extract endpoints
        first_leg = legs[0]
        last_leg = legs[-1]

        orig = first_leg.get("departure_airport", {}).get("id", "")
        dest = last_leg.get("arrival_airport", {}).get("id", "")

        # Departure/arrival times
        dep_time_full = first_leg.get("departure_airport", {}).get("time", "")
        arr_time_full = last_leg.get("arrival_airport", {}).get("time", "")

        # Date from departure info
        dep_date = ""
        if dep_time_full and len(dep_time_full) >= 10:
            dep_date = dep_time_full[:10]  # YYYY-MM-DD
        dep_time = dep_time_full[11:16] if len(dep_time_full) > 11 else ""
        arr_time = arr_time_full[11:16] if len(arr_time_full) > 11 else ""

        if not dep_date:
            dep_date = query_date

        # Airline info (first segment)
        airline = first_leg.get("airline", "")
        flight_no = first_leg.get("flight_number", "")

        # Price
        price = result.get("price", 0)

        # Stops
        stops = len(legs) - 1

        # Duration
        duration_min = result.get("total_duration", 0)

        flight = {
            "provider": "serpapi_gf",
            "direction": direction,
            "orig_airport": orig,
            "dest_airport": dest,
            "orig_metro_group": get_metro_group(orig),
            "dest_metro_group": get_metro_group(dest),
            "flight_date": dep_date,
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "airline": airline,
            "flight_no": f"{airline} {flight_no}" if flight_no else airline,
            "price_eur": float(price),
            "currency": "EUR",
            "stops": stops,
            "duration_min": duration_min,
            "booking_token": None,
            "raw_json": result,
            "is_mock": False,
        }

        # For round-trip results, also extract return leg info
        if direction == "roundtrip":
            ret_flights = result.get("return_flights", [])
            if ret_flights:
                ret_first = ret_flights[0]
                ret_last = ret_flights[-1]
                flight["return_orig"] = ret_first.get("departure_airport", {}).get("id", "")
                flight["return_dest"] = ret_last.get("arrival_airport", {}).get("id", "")
                ret_dep = ret_first.get("departure_airport", {}).get("time", "")
                ret_arr = ret_last.get("arrival_airport", {}).get("time", "")
                flight["return_date"] = ret_dep[:10] if len(ret_dep) >= 10 else ""
                flight["return_dep_time"] = ret_dep[11:16] if len(ret_dep) > 11 else ""
                flight["return_arr_time"] = ret_arr[11:16] if len(ret_arr) > 11 else ""
                flight["return_airline"] = ret_first.get("airline", "")
                flight["return_flight_no"] = ret_first.get("flight_number", "")
                flight["return_stops"] = len(ret_flights) - 1

        flights.append(flight)

    return flights


def parse_explore_response(data: dict, origin_airport: str) -> list[dict]:
    """Parse google_travel_explore SerpApi response into a list of destination dicts.

    Returns a list with destination info, price, dates, etc.
    """
    results = []
    destinations = data.get("destinations", [])

    for dest in destinations:
        airport_codes = dest.get("airports", [])
        # airports is a list of dicts with 'id' key
        if isinstance(airport_codes, list) and airport_codes:
            if isinstance(airport_codes[0], dict):
                dest_code = airport_codes[0].get("id", "")
            else:
                dest_code = str(airport_codes[0])
        else:
            dest_code = ""

        price = dest.get("price", {})
        if isinstance(price, dict):
            price_val = price.get("value", 0)
        else:
            price_val = float(price) if price else 0

        results.append({
            "destination_airport": dest_code,
            "destination_city": dest.get("city", dest_code),
            "destination_country": dest.get("country", ""),
            "price_eur": float(price_val),
            "outbound_date": dest.get("departure_date", ""),
            "return_date": dest.get("return_date", ""),
            "airline": dest.get("airlines", [""])[0] if dest.get("airlines") else "",
            "source": "google_travel_explore",
            "is_mock": False,
        })

    return sorted(results, key=lambda x: x["price_eur"])
