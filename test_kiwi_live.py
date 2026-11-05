#!/usr/bin/env python3
"""Single live test: KRK -> BGY, ~60 days out, via Kiwi MCP."""
import requests
import json
from datetime import datetime, timedelta

MCP_URL = "https://mcp.kiwi.com"

session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
})

# Initialize
resp = session.post(MCP_URL, json={
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "azair-extended", "version": "0.1.0"}
    }
}, timeout=15)
sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
if sid:
    session.headers["Mcp-Session-Id"] = sid

# Initialized notification
session.post(MCP_URL, json={
    "jsonrpc": "2.0", "method": "notifications/initialized", "params": {}
}, timeout=10)

# Search flight: KRK -> BGY, ~60 days out, return ~67 days, 5-10 nights
dep_date = (datetime.now() + timedelta(days=60)).strftime("%d/%m/%Y")
ret_date = (datetime.now() + timedelta(days=67)).strftime("%d/%m/%Y")

print(f"Searching: KRK -> BGY, dep={dep_date}, ret={ret_date}")
payload = {
    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
    "params": {
        "name": "search-flight",
        "arguments": {
            "flyFrom": "KRK",
            "flyTo": "BGY",
            "departureDate": dep_date,
            "departureDateFlexDays": 3,
            "returnDate": ret_date,
            "returnDateFlexDays": 3,
            "nights_in_dst_from": 5,
            "nights_in_dst_to": 10,
            "currency": "EUR",
            "adults": 1,
            "locale": "en",
            "max_sector_stopovers": 0,
        }
    }
}
resp = session.post(MCP_URL, json=payload, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('Content-Type', '')}")

ct = resp.headers.get("Content-Type", "")
result_data = None
if "text/event-stream" in ct:
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            result_data = json.loads(line[6:])
            break
else:
    result_data = resp.json()

if result_data:
    result = result_data.get("result", {})
    # Check for content array (MCP standard)
    content = result.get("content", [])
    if content:
        print(f"\nContent items: {len(content)}")
        for c in content:
            ctype = c.get("type", "")
            print(f"  Content type: {ctype}")
            if ctype == "text":
                text = c.get("text", "")
                print(f"  Text length: {len(text)}")
                # Try parse as JSON
                try:
                    data = json.loads(text)
                    print(f"  Parsed JSON keys: {list(data.keys())}")
                    print(f"  resultsCount: {data.get('resultsCount', '?')}")
                    print(f"  currency: {data.get('currency', '?')}")
                    itin = data.get("itineraries", [])
                    print(f"  itineraries: {len(itin)}")
                    if itin:
                        it = itin[0]
                        print(f"\n  FIRST ITINERARY:")
                        print(f"    price: {it.get('price')} {it.get('priceFormatted', '')}")
                        print(f"    bookingUrl: {it.get('bookingUrl', '')[:80]}...")
                        ob = it.get("outbound", {})
                        ib = it.get("inbound", {})
                        print(f"    outbound route: {ob.get('route', [])}")
                        print(f"    outbound dep: {ob.get('departureTime', '')}")
                        print(f"    outbound arr: {ob.get('arrivalTime', '')}")
                        print(f"    outbound stops: {ob.get('stops', '?')}")
                        segs = ob.get("segments", [])
                        if segs:
                            s = segs[0]
                            print(f"    segment: {s.get('from')} -> {s.get('to')}, {s.get('carrierName')} {s.get('flightNumber')}")
                        if ib:
                            print(f"    inbound route: {ib.get('route', [])}")
                            print(f"    inbound dep: {ib.get('departureTime', '')}")
                            isegs = ib.get("segments", [])
                            if isegs:
                                s = isegs[0]
                                print(f"    segment: {s.get('from')} -> {s.get('to')}, {s.get('carrierName')} {s.get('flightNumber')}")
                        # Print second itinerary too
                        if len(itin) > 1:
                            it2 = itin[1]
                            print(f"\n  SECOND ITINERARY:")
                            print(f"    price: {it2.get('price')} {it2.get('priceFormatted', '')}")
                            ob2 = it2.get("outbound", {})
                            ib2 = it2.get("inbound", {})
                            print(f"    outbound route: {ob2.get('route', [])}")
                            if ib2:
                                print(f"    inbound route: {ib2.get('route', [])}")
                except json.JSONDecodeError:
                    print(f"  Raw text (first 500 chars): {text[:500]}")
            elif ctype == "resource":
                res = c.get("resource", {})
                print(f"  Resource URI: {res.get('uri', '')}")
                blob = res.get("blob", res.get("text", ""))
                if isinstance(blob, str):
                    try:
                        data = json.loads(blob)
                        print(f"  Parsed: keys={list(data.keys())}")
                    except:
                        print(f"  Raw: {str(blob)[:200]}")
    else:
        # Maybe direct result
        print(f"\nResult keys: {list(result.keys())}")
        print(json.dumps(result, indent=2)[:2000])
else:
    print("No result data found")
    print(f"Raw response (first 1000): {resp.text[:1000]}")
