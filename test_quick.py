#!/usr/bin/env python3
"""
test_quick.py – Module tests for AZair Extended (Etap 2).

Tests:
  1. All module imports
  2. Metro group assertions
  3. Mock flight generation
  4. SQLite cache + matcher
  5. SerpApi parser (google_flights mock JSON)
  6. SerpApi parser (google_travel_explore mock JSON)
  7. Kiwi MCP response parser
  8. Date range + weekday generation
"""

import json
from datetime import datetime, timedelta

# ===== 1. Imports =====
print("=== 1. Imports ===")
import config
import engine.db
import engine.safety
import engine.matcher
import providers.mock_provider
import providers.serpapi_client
import providers.kiwi_mcp
print("  All modules imported OK")

# ===== 2. Metro groups =====
print("\n=== 2. Metro Groups ===")
assert config.get_metro_group("BGY") == "MILAN"
assert config.get_metro_group("MXP") == "MILAN"
assert config.get_metro_group("LIN") == "MILAN"
assert config.get_metro_group("FCO") == "ROME"
assert config.get_metro_group("CIA") == "ROME"
assert config.get_metro_group("CTA") == "SICILY_EAST"
assert config.get_metro_group("CIY") == "SICILY_EAST"
assert config.get_metro_group("PMO") == "SICILY_WEST"
assert config.get_metro_group("TPS") == "SICILY_WEST"
assert config.get_metro_group("KUT") == "KUT"
assert config.get_metro_group("AGP") == "AGP"
assert config.get_metro_group("SAW") == "ISTANBUL"
assert config.get_metro_group("IST") == "ISTANBUL"
assert config.get_metro_group("BCN") == "BARCELONA"
assert config.get_metro_group("GRO") == "BARCELONA"
print("  All metro group tests PASSED")

# ===== 3. Mock flights =====
print("\n=== 3. Mock Flight Generation ===")
flights = providers.mock_provider.generate_mock_flights(
    ["KRK", "KTW"], ["BGY", "MXP", "FCO", "CIA", "CTA", "CIY", "KUT"],
    "2027-03-15", "2027-03-22", direction="both"
)
print(f"  Generated {len(flights)} mock flights")
assert len(flights) > 0
assert all(f["currency"] == "EUR" for f in flights)
assert all("[MOCK]" in f["airline"] for f in flights)
print("  Mock flights OK")

# ===== 4. SQLite cache + matcher =====
print("\n=== 4. SQLite Cache + Matcher ===")
conn = engine.db.get_connection()
params = {"test": True, "origins": ["KRK", "KTW"],
          "dests": ["BGY", "MXP", "FCO", "CIA", "CTA", "CIY", "KUT"]}
engine.db.store_flights(conn, "mock", params, flights, is_mock=True)
qh = engine.db.compute_query_hash("mock", params)
cached = engine.db.get_cached_flights(conn, qh)
print(f"  Cached {len(cached)} flights")
assert len(cached) == len(flights)

matched = engine.matcher.match_roundtrips(
    conn, origin_airports=["KRK", "KTW"],
    min_nights=5, max_nights=10,
    allow_different_return_airport=True,
)
print(f"  Matched {len(matched)} round-trips")
assert len(matched) > 0
m = matched[0]
print(f"  Best: {m['out_orig']}->{m['out_dest']} / {m['ret_orig']}->{m['ret_dest']} = {m['total_eur']:.0f}EUR, {m['nights']}n")

# Verify metro_group matching correctness
for m in matched:
    assert m["out_dest_metro"] == m["ret_orig_metro"], \
        f"Metro mismatch: {m['out_dest']}({m['out_dest_metro']}) != {m['ret_orig']}({m['ret_orig_metro']})"
print("  All matched pairs have correct metro_group alignment")
conn.close()

# ===== 5. SerpApi google_flights parser =====
print("\n=== 5. SerpApi google_flights Parser ===")
mock_gf_response = {
    "best_flights": [
        {
            "flights": [
                {
                    "departure_airport": {"id": "KRK", "name": "Krakow", "time": "2027-03-15 06:15"},
                    "arrival_airport": {"id": "BGY", "name": "Milano Bergamo", "time": "2027-03-15 08:05"},
                    "airline": "Ryanair",
                    "flight_number": "FR 1234",
                }
            ],
            "price": 25,
            "total_duration": 110,
        },
        {
            "flights": [
                {
                    "departure_airport": {"id": "KTW", "name": "Katowice", "time": "2027-03-15 10:30"},
                    "arrival_airport": {"id": "FCO", "name": "Rome Fiumicino", "time": "2027-03-15 12:45"},
                    "airline": "Wizz Air",
                    "flight_number": "W6 5678",
                }
            ],
            "price": 35,
            "total_duration": 135,
        }
    ],
    "other_flights": [
        {
            "flights": [
                {
                    "departure_airport": {"id": "KRK", "name": "Krakow", "time": "2027-03-15 14:00"},
                    "arrival_airport": {"id": "VIE", "name": "Vienna", "time": "2027-03-15 15:10"},
                    "airline": "Austrian",
                    "flight_number": "OS 111",
                },
                {
                    "departure_airport": {"id": "VIE", "name": "Vienna", "time": "2027-03-15 17:00"},
                    "arrival_airport": {"id": "CTA", "name": "Catania", "time": "2027-03-15 19:30"},
                    "airline": "Austrian",
                    "flight_number": "OS 222",
                }
            ],
            "price": 89,
            "total_duration": 330,
        }
    ]
}

parsed_gf = providers.serpapi_client.parse_google_flights_response(
    mock_gf_response, direction="outbound", query_date="2027-03-15"
)
print(f"  Parsed {len(parsed_gf)} flights from mock google_flights response")
assert len(parsed_gf) == 3

# Check first flight
f1 = parsed_gf[0]
assert f1["orig_airport"] == "KRK"
assert f1["dest_airport"] == "BGY"
assert f1["price_eur"] == 25.0
assert f1["stops"] == 0
assert f1["dest_metro_group"] == "MILAN"
print(f"  Flight 1: {f1['orig_airport']}->{f1['dest_airport']} {f1['price_eur']}EUR stops={f1['stops']} metro={f1['dest_metro_group']}")

# Check second flight
f2 = parsed_gf[1]
assert f2["orig_airport"] == "KTW"
assert f2["dest_airport"] == "FCO"
assert f2["dest_metro_group"] == "ROME"
print(f"  Flight 2: {f2['orig_airport']}->{f2['dest_airport']} {f2['price_eur']}EUR metro={f2['dest_metro_group']}")

# Check connecting flight
f3 = parsed_gf[2]
assert f3["orig_airport"] == "KRK"
assert f3["dest_airport"] == "CTA"
assert f3["stops"] == 1
assert f3["dest_metro_group"] == "SICILY_EAST"
print(f"  Flight 3: {f3['orig_airport']}->{f3['dest_airport']} {f3['price_eur']}EUR stops={f3['stops']} metro={f3['dest_metro_group']}")
print("  google_flights parser OK")

# ===== 6. SerpApi google_travel_explore parser =====
print("\n=== 6. SerpApi google_travel_explore Parser ===")
mock_explore_response = {
    "destinations": [
        {
            "city": "Milan",
            "country": "Italy",
            "airports": [{"id": "BGY"}, {"id": "MXP"}],
            "price": {"value": 29},
            "departure_date": "2027-04-10",
            "return_date": "2027-04-17",
            "airlines": ["Ryanair"],
        },
        {
            "city": "Rome",
            "country": "Italy",
            "airports": [{"id": "FCO"}],
            "price": {"value": 45},
            "departure_date": "2027-04-12",
            "return_date": "2027-04-19",
            "airlines": ["Wizz Air"],
        },
        {
            "city": "Catania",
            "country": "Italy",
            "airports": [{"id": "CTA"}],
            "price": {"value": 65},
            "departure_date": "2027-04-15",
            "return_date": "2027-04-22",
            "airlines": ["Ryanair"],
        },
    ]
}

parsed_explore = providers.serpapi_client.parse_explore_response(
    mock_explore_response, "KRK"
)
print(f"  Parsed {len(parsed_explore)} destinations")
assert len(parsed_explore) == 3
assert parsed_explore[0]["destination_airport"] == "BGY"
assert parsed_explore[0]["price_eur"] == 29.0
assert parsed_explore[0]["destination_city"] == "Milan"
print(f"  Cheapest: {parsed_explore[0]['destination_city']} ({parsed_explore[0]['destination_airport']}) = {parsed_explore[0]['price_eur']}EUR")
print("  google_travel_explore parser OK")

# ===== 7. Kiwi MCP response parser =====
print("\n=== 7. Kiwi MCP Response Parser ===")
mock_kiwi_response = {
    "result": {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "query": "KRK->BGY",
                    "currency": "EUR",
                    "passengers": {"adults": 1},
                    "resultsCount": 2,
                    "itineraries": [
                        {
                            "price": 74.0,
                            "priceFormatted": "74 EUR",
                            "bookingUrl": "https://kiwi.com/book/test1",
                            "totalDurationSeconds": 7200,
                            "outbound": {
                                "route": ["KRK", "BGY"],
                                "departureTime": "2027-01-01T05:50:00",
                                "arrivalTime": "2027-01-01T07:40:00",
                                "stops": 0,
                                "segments": [
                                    {
                                        "from": "KRK", "to": "BGY",
                                        "fromCity": "Krakow", "toCity": "Milan",
                                        "carrierName": "Ryanair", "flightNumber": "FR889",
                                        "carrier": "FR",
                                    }
                                ]
                            },
                            "inbound": {
                                "route": ["BGY", "KRK"],
                                "departureTime": "2027-01-08T10:30:00",
                                "arrivalTime": "2027-01-08T12:20:00",
                                "stops": 0,
                                "segments": [
                                    {
                                        "from": "BGY", "to": "KRK",
                                        "carrierName": "Ryanair", "flightNumber": "FR888",
                                        "carrier": "FR",
                                    }
                                ]
                            }
                        },
                        {
                            "price": 98.0,
                            "priceFormatted": "98 EUR",
                            "bookingUrl": "https://kiwi.com/book/test2",
                            "totalDurationSeconds": 9000,
                            "outbound": {
                                "route": ["KRK", "MXP"],
                                "departureTime": "2027-01-02T14:00:00",
                                "arrivalTime": "2027-01-02T16:05:00",
                                "stops": 0,
                                "segments": [
                                    {
                                        "from": "KRK", "to": "MXP",
                                        "carrierName": "Wizz Air", "flightNumber": "W6100",
                                        "carrier": "W6",
                                    }
                                ]
                            },
                            "inbound": {
                                "route": ["MXP", "KRK"],
                                "departureTime": "2027-01-10T08:00:00",
                                "arrivalTime": "2027-01-10T10:00:00",
                                "stops": 0,
                                "segments": [
                                    {
                                        "from": "MXP", "to": "KRK",
                                        "carrierName": "Wizz Air", "flightNumber": "W6101",
                                        "carrier": "W6",
                                    }
                                ]
                            }
                        }
                    ],
                    "searchTimeMs": 1234,
                })
            }
        ]
    }
}

parsed_kiwi = providers.kiwi_mcp.parse_kiwi_response(mock_kiwi_response, "KRK", "BGY")
print(f"  Parsed {len(parsed_kiwi)} itineraries")
assert len(parsed_kiwi) == 2

k1 = parsed_kiwi[0]
assert k1["orig_airport"] == "KRK"
assert k1["dest_airport"] == "BGY"
assert k1["price_eur"] == 74.0
assert k1["outbound_airline"] == "Ryanair"
assert k1["outbound_flight_no"] == "FR889"
assert k1["return_orig_airport"] == "BGY"
assert k1["return_dest_airport"] == "KRK"
assert k1["nights"] == 7
assert k1["booking_url"] == "https://kiwi.com/book/test1"
assert k1["is_mock"] is False
print(f"  Itinerary 1: {k1['orig_airport']}->{k1['dest_airport']} {k1['price_eur']}EUR {k1['outbound_airline']} {k1['nights']}n")

k2 = parsed_kiwi[1]
assert k2["orig_airport"] == "KRK"
assert k2["dest_airport"] == "MXP"
assert k2["dest_metro_group"] == "MILAN"
assert k2["nights"] == 8
print(f"  Itinerary 2: {k2['orig_airport']}->{k2['dest_airport']} {k2['price_eur']}EUR metro={k2['dest_metro_group']} {k2['nights']}n")
print("  Kiwi MCP parser OK")

# ===== 8. Date range + weekday helpers =====
print("\n=== 8. Date Range & Weekday Helpers ===")
from datetime import datetime as dt

# Helper from app.py logic
WEEKDAY_MAP = {0: "Pn", 1: "Wt", 2: "Śr", 3: "Cz", 4: "Pt", 5: "Sb", 6: "Nd"}

def gen_dates(date_from, date_to, allowed_wd):
    dates = []
    current = date_from
    while current <= date_to:
        if WEEKDAY_MAP[current.weekday()] in allowed_wd:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates

# Test: only Fridays and Sundays in a week
d_from = dt(2027, 3, 15)  # Monday
d_to = dt(2027, 3, 21)    # Sunday
fri_sun = gen_dates(d_from, d_to, ["Pt", "Nd"])
print(f"  Dates Pt+Nd in Mar 15-21: {fri_sun}")
assert len(fri_sun) == 2
assert "2027-03-19" in fri_sun  # Friday
assert "2027-03-21" in fri_sun  # Sunday

# Test: all days
all_days = gen_dates(d_from, d_to, list(WEEKDAY_MAP.values()))
assert len(all_days) == 7
print(f"  All days in week: {len(all_days)}")
print("  Date range tests OK")

# ===== Chunking =====
print("\n=== 9. Airport Chunking ===")
airports_11 = ["BGY", "MXP", "LIN", "VCE", "TSF", "BLQ", "TRN", "VRN", "GOA", "TRS", "RMI"]
chunks = providers.serpapi_client.chunk_airports(airports_11, 6)
print(f"  {len(airports_11)} airports -> {len(chunks)} chunks: {[len(c) for c in chunks]}")
assert len(chunks) == 2
assert len(chunks[0]) == 6
assert len(chunks[1]) == 5
print("  Chunking OK")

# ===== 10. Kiwi Cache Preservation =====
print("\n=== 10. Kiwi Cache Preservation ===")
conn_test = engine.db.get_connection()
kiwi_params = {"flyFrom": "KRK", "flyTo": "BGY", "date_from": "2027-01-01"}
engine.db.store_flights(conn_test, "kiwi_mcp", kiwi_params, parsed_kiwi, is_mock=False)
kiwi_qh = engine.db.compute_query_hash("kiwi_mcp", kiwi_params)
kiwi_cached = engine.db.get_cached_flights(conn_test, kiwi_qh)
assert len(kiwi_cached) == len(parsed_kiwi)
kc1 = kiwi_cached[0]
assert kc1["return_date"] == "2027-01-08", f"Expected '2027-01-08', got {kc1.get('return_date')}"
assert kc1["return_airline"] == "Ryanair", f"Expected 'Ryanair', got {kc1.get('return_airline')}"
assert kc1["nights"] == 7, f"Expected 7, got {kc1.get('nights')}"
assert kc1["booking_url"] == "https://kiwi.com/book/test1", f"Expected url, got {kc1.get('booking_url')}"
conn_test.close()
print("  Kiwi cache preservation OK")

# ===== 11. Unified Schedule Filters & Numeric Price Formatting =====
print("\n=== 11. Unified Schedule Filters & Numeric Price Formatting ===")

# 1. generate_mock_kiwi_flights with keyword arguments
mock_kiwi_bounds = providers.mock_provider.generate_mock_kiwi_flights(
    origin_airport="KRK",
    dest_airport="BGY",
    date_from="2027-03-15",
    date_to="2027-03-17",
    return_from="2027-03-18",
    return_to="2027-03-25",
    nights_in_dst_from=3,
    nights_in_dst_to=6,
)
assert len(mock_kiwi_bounds) > 0, "Expected at least 1 mock flight generated"
for f in mock_kiwi_bounds:
    assert 3 <= f["nights"] <= 6, f"Expected 3 <= nights <= 6, got {f['nights']}"
    assert "2027-03-18" <= f["return_date"] <= "2027-03-25", f"Return date {f['return_date']} outside bounds"
print("  Mock Kiwi return date and nights bounds OK")

# 2. match_roundtrips with schedule filter parameters
conn_match = engine.db.get_connection()
matched_sched = engine.matcher.match_roundtrips(
    conn_match,
    origin_airports=["KRK", "KTW"],
    min_nights=5,
    max_nights=10,
    allow_different_return_airport=True,
    out_date_from="2027-03-15",
    out_date_to="2027-03-16",
    ret_date_from="2027-03-20",
    ret_date_to="2027-03-22",
    out_weekdays=["Pn", "Wt"],
    ret_weekdays=["Sb", "Nd", "Pn"],
)
assert len(matched_sched) > 0, "Expected matched roundtrips with schedule filters"
for m in matched_sched:
    assert "2027-03-15" <= m["out_date"] <= "2027-03-16"
    assert "2027-03-20" <= m["ret_date"] <= "2027-03-22"
    out_wd = engine.matcher.WEEKDAY_MAP[datetime.strptime(m["out_date"], "%Y-%m-%d").weekday()]
    ret_wd = engine.matcher.WEEKDAY_MAP[datetime.strptime(m["ret_date"], "%Y-%m-%d").weekday()]
    assert out_wd in ["Pn", "Wt"]
    assert ret_wd in ["Sb", "Nd", "Pn"]
conn_match.close()
print("  Matcher schedule date & weekday filters OK")

# 3. Numeric price sorting
test_prices = [100.0, 39.0, 56.0]
assert all(isinstance(p, float) for p in test_prices)
sorted_prices = sorted(test_prices)
assert sorted_prices == [39.0, 56.0, 100.0], f"Expected numeric sort [39.0, 56.0, 100.0], got {sorted_prices}"
assert 39.0 < 56.0 < 100.0
# Verify that string sorting would have produced incorrect ordering
str_sorted = sorted([str(p) for p in test_prices])
assert str_sorted[0] == "100.0", "String sorting puts '100.0' first"
print("  Numeric price sorting (39.0 < 56.0 < 100.0) OK")

# ===== 12. Set-Inclusion & Range Coverage Cache Optimization =====
print("\n=== 12. Set-Inclusion & Range Coverage Cache Optimization ===")
conn_12 = engine.db.get_connection()
test_p = {"flyFrom": "KRK", "flyTo": "BGY", "date_from": "2027-02-05", "date_to": "2027-02-07", "nmin": 2, "nmax": 7}
test_flights = [{"provider": "mock", "direction": "roundtrip", "orig_airport": "KRK", "dest_airport": "BGY",
                 "orig_metro_group": "KRK", "dest_metro_group": "MILAN", "flight_date": "2027-02-05",
                 "price_eur": 50.0, "currency": "EUR", "stops": 0, "is_mock": True}]
engine.db.store_flights(conn_12, "mock", test_p, test_flights, is_mock=True)

# Subset test (2027-02-05 to 2027-02-06 should return None -> 0 API calls)
res_sub = engine.db.compute_uncovered_kiwi_range(conn_12, "KRK", "BGY", "2027-02-05", "2027-02-06", 2, 7, ttl_hours=24, is_mock=True)
assert res_sub is None, f"Expected None for covered subset, got {res_sub}"
print("  Subset inclusion (0 calls): OK")

# Partially uncovered test (2027-02-05 to 2027-02-08 should return ('2027-02-08', '2027-02-08'))
res_partial = engine.db.compute_uncovered_kiwi_range(conn_12, "KRK", "BGY", "2027-02-05", "2027-02-08", 2, 7, ttl_hours=24, is_mock=True)
assert res_partial == ("2027-02-08", "2027-02-08"), f"Expected ('2027-02-08', '2027-02-08'), got {res_partial}"
print("  Partial range coverage calculation: OK")

# query_flights_by_criteria test
queried = engine.db.query_flights_by_criteria(conn_12, origins=["KRK"], dests=["BGY"], date_from="2027-02-05", date_to="2027-02-05", is_mock=True)
assert len(queried) > 0, "Expected at least 1 flight from query_flights_by_criteria"
assert queried[0]["orig_airport"] == "KRK"
assert queried[0]["dest_airport"] == "BGY"
print("  query_flights_by_criteria lookup: OK")

conn_12.close()

# ===== 13. Exact Matcher dest_airports, EN/PL Weekdays & Static Verification =====
print("\n=== 13. Exact Matcher dest_airports, EN/PL Weekdays & Static Verification ===")
conn_13 = engine.db.get_connection()

# 1. dest_airports filtering before LIMIT 500
matched_bgy = engine.matcher.match_roundtrips(
    conn_13,
    origin_airports=["KRK", "KTW"],
    dest_airports=["BGY"],
    min_nights=5,
    max_nights=10,
    allow_different_return_airport=True,
    is_mock=True,
)
assert len(matched_bgy) > 0, "Expected at least 1 round-trip to BGY"
assert all(m["out_dest"] == "BGY" for m in matched_bgy), f"All destinations must be BGY, got: {[m['out_dest'] for m in matched_bgy]}"
print(f"  dest_airports=['BGY'] filter (0 non-BGY): OK ({len(matched_bgy)} combinations)")

# 2. EN & PL Weekdays matching
matched_en = engine.matcher.match_roundtrips(
    conn_13,
    origin_airports=["KRK", "KTW"],
    dest_airports=["BGY"],
    min_nights=5,
    max_nights=10,
    allow_different_return_airport=True,
    out_weekdays=["Mon", "Tue"],
    is_mock=True,
)
assert len(matched_en) > 0, "Expected matched roundtrips with EN weekdays"
for m in matched_en:
    wd = datetime.strptime(m["out_date"], "%Y-%m-%d").weekday()
    assert wd in [0, 1], f"Expected Monday (0) or Tuesday (1), got weekday {wd} for {m['out_date']}"

matched_pl = engine.matcher.match_roundtrips(
    conn_13,
    origin_airports=["KRK", "KTW"],
    dest_airports=["BGY"],
    min_nights=5,
    max_nights=10,
    allow_different_return_airport=True,
    out_weekdays=["Pn", "Wt"],
    is_mock=True,
)
assert len(matched_pl) > 0, "Expected matched roundtrips with PL weekdays"
assert len(matched_pl) == len(matched_en), f"PL ({len(matched_pl)}) and EN ({len(matched_en)}) weekday filters should return identical results"
print(f"  EN/PL Weekday matching (Mon/Tue == Pn/Wt): OK ({len(matched_en)} items)")

conn_13.close()

# 3. Static verification of app.py
with open("app.py", encoding="utf-8") as f:
    app_content = f.read()

# No kind="primary" in widget calls
import re
widget_kind_calls = re.findall(r'st\.\w+\([^)]*kind\s*=', app_content)
assert len(widget_kind_calls) == 0, f"Found kind= in Streamlit widget calls: {widget_kind_calls}"
print("  Zero kind= in Streamlit widget calls: OK")

# No 'Book' column config in table configs
assert '"Book":' not in app_content and "'Book':" not in app_content, "Found 'Book' column in config in app.py"
print("  Zero 'Book' column in table configs: OK")

# No forbidden emojis in app.py
forbidden_emojis = ["✈️", "🔒", "🟡", "🟢", "⚙️", "🗑️", "🔑", "🌍", "🛫", "🎯", "📊", "🚫", "✅", "⚠️", "❌", "📦", "🔥", "🔗", "🗂️", "🧪"]
for em in forbidden_emojis:
    assert em not in app_content, f"Forbidden emoji '{em}' found in app.py"
print("  Zero forbidden emojis in app.py: OK")

print("\n" + "="*50)
print("ALL TESTS PASSED")
