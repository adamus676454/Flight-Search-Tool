"""
providers/mock_provider.py – Realistic test data generator for MOCK_MODE.

Generates deterministic, clearly-labelled MOCK flights in EUR covering:
  - Milan (BGY/MXP), Rome (FCO/CIA), Sicily East (CTA/CIY),
    Georgia (KUT), Barcelona (BCN/GRO), and more.
  - Both outbound and inbound legs for matcher testing.

ALL prices are in EUR. Every record is flagged is_mock=True.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from config import get_metro_group


def _mock_flight(
    direction: str,
    orig: str,
    dest: str,
    date: str,
    dep_time: str,
    arr_time: str,
    airline: str,
    flight_no: str,
    price: float,
    stops: int = 0,
    duration_min: int = 150,
) -> dict:
    return {
        "provider": "mock",
        "direction": direction,
        "orig_airport": orig,
        "dest_airport": dest,
        "orig_metro_group": get_metro_group(orig),
        "dest_metro_group": get_metro_group(dest),
        "flight_date": date,
        "departure_time": dep_time,
        "arrival_time": arr_time,
        "airline": f"[MOCK] {airline}",
        "flight_no": f"MOCK-{flight_no}",
        "price_eur": price,
        "currency": "EUR",
        "stops": stops,
        "duration_min": duration_min,
        "booking_token": None,
        "raw_json": None,
        "is_mock": True,
    }


def generate_mock_flights(
    origin_airports: list[str],
    dest_airports: list[str],
    outbound_date: str,
    return_date: str | None = None,
    direction: str = "outbound",
) -> list[dict]:
    """Generate a set of realistic mock flights.

    Parameters
    ----------
    origin_airports : list[str]
        E.g. ["KRK", "KTW"]
    dest_airports : list[str]
        E.g. ["BGY", "MXP", "FCO", "CIA", "CTA", "CIY", "KUT"]
    outbound_date : str
        ISO date for outbound flights.
    return_date : str | None
        ISO date for inbound flights (if generating round-trip legs).
    direction : str
        'outbound', 'inbound', or 'both'.
    """
    flights: list[dict] = []
    rng = random.Random(42)  # deterministic

    mock_airlines = [
        ("Ryanair", "FR"),
        ("Wizz Air", "W6"),
        ("easyJet", "U2"),
        ("Vueling", "VY"),
        ("Transavia", "HV"),
        ("Pegasus", "PC"),
    ]

    dep_times = ["06:15", "07:30", "09:45", "11:20", "14:00", "16:30", "19:10", "21:40"]
    arr_offsets = [120, 135, 150, 165, 180, 210, 240, 300]  # minutes

    counter = 1000

    def _make_legs(dir_label: str, origins: list[str], dests: list[str], date: str):
        nonlocal counter
        result = []
        for orig in origins:
            for dest in dests:
                if orig == dest:
                    continue
                # 1-3 flights per route
                n_flights = rng.randint(1, 3)
                for _ in range(n_flights):
                    airline_name, airline_code = rng.choice(mock_airlines)
                    dep = rng.choice(dep_times)
                    dur = rng.choice(arr_offsets)
                    dep_dt = datetime.strptime(f"{date} {dep}", "%Y-%m-%d %H:%M")
                    arr_dt = dep_dt + timedelta(minutes=dur)
                    price = round(rng.uniform(15.0, 120.0), 2)
                    stops = rng.choices([0, 1], weights=[85, 15])[0]
                    counter += 1
                    result.append(
                        _mock_flight(
                            direction=dir_label,
                            orig=orig,
                            dest=dest,
                            date=date,
                            dep_time=dep,
                            arr_time=arr_dt.strftime("%H:%M"),
                            airline=airline_name,
                            flight_no=f"{airline_code}{counter}",
                            price=price,
                            stops=stops,
                            duration_min=dur,
                        )
                    )
        return result

    if direction in ("outbound", "both"):
        flights.extend(_make_legs("outbound", origin_airports, dest_airports, outbound_date))

    if direction in ("inbound", "both") and return_date:
        # For inbound: origins become destinations and vice-versa
        flights.extend(_make_legs("inbound", dest_airports, origin_airports, return_date))

    return flights


def generate_mock_explore(origin_airport: str, country_name: str, month: str) -> list[dict]:
    """Generate mock Explore results (cheapest destinations in a country).

    Returns a list of dicts with destination, price, dates.
    """
    rng = random.Random(hash(f"{origin_airport}{country_name}{month}"))

    # Pick some airports depending on country
    country_airports = {
        "Włochy": ["BGY", "FCO", "NAP", "CTA", "PMO", "BLQ"],
        "Hiszpania": ["BCN", "MAD", "AGP", "PMI", "TFS", "ALC"],
        "Grecja": ["ATH", "SKG", "CHQ", "HER", "RHO", "CFU"],
        "Portugalia": ["LIS", "OPO", "FAO", "FNC"],
        "Turcja": ["SAW", "IST", "AYT", "DLM", "ADB"],
        "Maroko": ["RAK", "AGA", "FEZ", "TNG", "CMN"],
        "Gruzja": ["KUT", "TBS", "BUS"],
        "Chorwacja": ["ZAD", "SPU", "DBV", "PUY"],
    }

    airports = country_airports.get(country_name, ["ATH", "BCN", "FCO"])
    results = []
    for apt in airports:
        price = round(rng.uniform(18.0, 95.0), 2)
        # generate random dates in the given month
        try:
            year_month = datetime.strptime(month, "%Y-%m")
        except ValueError:
            year_month = datetime.now().replace(day=1)
        day_out = rng.randint(1, 28)
        day_ret = day_out + rng.randint(3, 14)
        if day_ret > 28:
            day_ret = 28
        out_date = year_month.replace(day=day_out).strftime("%Y-%m-%d")
        ret_date = year_month.replace(day=day_ret).strftime("%Y-%m-%d")

        results.append({
            "destination_airport": apt,
            "destination_city": apt,  # will be resolved by UI from config
            "price_eur": price,
            "outbound_date": out_date,
            "return_date": ret_date,
            "airline": f"[MOCK] Ryanair",
            "source": "MOCK google_travel_explore",
            "is_mock": True,
        })

    return sorted(results, key=lambda x: x["price_eur"])


def generate_mock_kiwi_flights(
    origin_airport: str,
    dest_airport: str,
    date_from: str,
    date_to: str,
    return_from: str | None = None,
    return_to: str | None = None,
    nights_in_dst_from: int = 2,
    nights_in_dst_to: int = 14,
) -> list[dict]:
    """Generate mock Kiwi-style round-trip offers respecting date and night bounds."""
    seed_val = sum(c * (idx + 1) for idx, c in enumerate(f"{origin_airport}{dest_airport}{date_from}".encode()))
    rng = random.Random(seed_val)

    mock_airlines = ["Ryanair", "Wizz Air", "easyJet", "Vueling"]
    results = []

    d_from = datetime.strptime(date_from, "%Y-%m-%d")
    try:
        d_to = datetime.strptime(date_to, "%Y-%m-%d")
    except (ValueError, TypeError):
        d_to = d_from
    if d_to < d_from:
        d_to = d_from

    ret_from_dt = None
    if return_from:
        try:
            ret_from_dt = datetime.strptime(return_from, "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    ret_to_dt = None
    if return_to:
        try:
            ret_to_dt = datetime.strptime(return_to, "%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    max_out_offset = (d_to - d_from).days
    num_offers = rng.randint(2, 6)

    for i in range(num_offers):
        offset = rng.randint(0, max_out_offset) if max_out_offset > 0 else 0
        out_dt = d_from + timedelta(days=offset)

        min_n = max(0, nights_in_dst_from)
        max_n = max(min_n, nights_in_dst_to)

        if ret_from_dt is not None:
            min_n = max(min_n, (ret_from_dt - out_dt).days)
        if ret_to_dt is not None:
            max_n = min(max_n, (ret_to_dt - out_dt).days)

        if max_n < min_n:
            if nights_in_dst_to >= nights_in_dst_from:
                min_n = max(0, nights_in_dst_from)
                max_n = max(min_n, nights_in_dst_to)
            else:
                max_n = max(0, min_n)

        min_n = max(0, min_n)
        max_n = max(min_n, max_n)
        nights = rng.randint(min_n, max_n)
        ret_dt = out_dt + timedelta(days=nights)

        out_date = out_dt.strftime("%Y-%m-%d")
        ret_date = ret_dt.strftime("%Y-%m-%d")

        price_out = round(rng.uniform(15.0, 80.0), 2)
        price_ret = round(rng.uniform(15.0, 80.0), 2)
        airline = rng.choice(mock_airlines)

        results.append({
            "provider": "mock",
            "direction": "roundtrip",
            "orig_airport": origin_airport,
            "dest_airport": dest_airport,
            "orig_metro_group": get_metro_group(origin_airport),
            "dest_metro_group": get_metro_group(dest_airport),
            "outbound_date": out_date,
            "outbound_dep_time": f"{rng.randint(5,21):02d}:{rng.choice(['00','15','30','45'])}",
            "outbound_arr_time": f"{rng.randint(8,23):02d}:{rng.choice(['00','15','30','45'])}",
            "outbound_airline": f"[MOCK] {airline}",
            "outbound_flight_no": f"MOCK-{airline[:2].upper()}{1000+i}",
            "return_date": ret_date,
            "return_dep_time": f"{rng.randint(5,21):02d}:{rng.choice(['00','15','30','45'])}",
            "return_arr_time": f"{rng.randint(8,23):02d}:{rng.choice(['00','15','30','45'])}",
            "return_airline": f"[MOCK] {airline}",
            "return_flight_no": f"MOCK-{airline[:2].upper()}{2000+i}",
            "return_orig_airport": dest_airport,
            "return_dest_airport": origin_airport,
            "price_eur": round(price_out + price_ret, 2),
            "price_outbound_eur": price_out,
            "price_return_eur": price_ret,
            "currency": "EUR",
            "stops": rng.choices([0, 1], weights=[80, 20])[0],
            "nights": nights,
            "duration_min": rng.randint(100, 300),
            "booking_token": None,
            "raw_json": None,
            "is_mock": True,
        })

    return sorted(results, key=lambda x: x["price_eur"])
