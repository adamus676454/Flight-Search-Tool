"""
providers/kiwi_mcp.py – Kiwi MCP Streamable HTTP (JSON-RPC 2.0) client.

Protocol: MCP Streamable HTTP over https://mcp.kiwi.com
Tool: search-flight
Dates: dd/mm/yyyy format
Response: SSE (text/event-stream) with JSON-RPC result in data: lines
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import requests as _requests

from config import get_metro_group

KIWI_MCP_URL = "https://mcp.kiwi.com"


class KiwiMCPClient:
    """Stateful MCP client that handles initialize + tools/call lifecycle."""

    def __init__(self):
        self._session = _requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        self._initialized = False
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, payload: dict, timeout: int = 20) -> dict | None:
        """Send a JSON-RPC request. Returns parsed result or None.

        Handles both JSON and SSE responses.
        Raises on HTTP error (no retries).
        """
        resp = self._session.post(KIWI_MCP_URL, json=payload, timeout=timeout)
        resp.raise_for_status()

        # Check for session header
        sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if sid:
            self._session.headers["Mcp-Session-Id"] = sid

        ct = resp.headers.get("Content-Type", "")

        if "text/event-stream" in ct:
            # SSE: find the data: line with our JSON-RPC response
            for line in resp.text.splitlines():
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return None
        else:
            # Plain JSON
            return resp.json()

    def initialize(self):
        """Perform MCP initialize handshake (idempotent)."""
        if self._initialized:
            return

        # Step 1: initialize
        self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "azair-extended", "version": "0.1.0"},
            },
        })

        # Step 2: notifications/initialized
        try:
            self._session.post(
                KIWI_MCP_URL,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                timeout=10,
            )
        except Exception:
            pass  # notification is fire-and-forget

        self._initialized = True

    def search_flight(
        self,
        fly_from: str,
        fly_to: str,
        departure_date: str,
        departure_date_to: str | None = None,
        return_date: str | None = None,
        return_date_to: str | None = None,
        departure_flex_days: int = 3,
        return_flex_days: int = 3,
        nights_in_dst_from: int | None = None,
        nights_in_dst_to: int | None = None,
        adults: int = 1,
        currency: str = "EUR",
        max_sector_stopovers: int | None = None,
    ) -> dict:
        """Call search-flight tool and return raw parsed result.

        Parameters
        ----------
        fly_from, fly_to : str
            Single IATA codes (Kiwi MCP does NOT accept comma-separated).
        departure_date : str
            ISO format YYYY-MM-DD (converted to dd/mm/yyyy internally).
        departure_date_to : str | None
            End of departure date range (YYYY-MM-DD).
        return_date : str | None
            ISO format YYYY-MM-DD.
        return_date_to : str | None
            End of return date range (YYYY-MM-DD).
        departure_flex_days, return_flex_days : int
            ±days around departure/return dates. Use 0 if date_to is provided.
        nights_in_dst_from, nights_in_dst_to : int | None
            Min/max nights at destination (makes it a return search).
        """
        self.initialize()

        # Convert YYYY-MM-DD to dd/mm/yyyy
        def _to_kiwi_date(iso_date: str) -> str:
            dt = datetime.strptime(iso_date, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")

        args: dict = {
            "flyFrom": fly_from,
            "flyTo": fly_to,
            "departureDate": _to_kiwi_date(departure_date),
            "currency": currency,
            "adults": adults,
            "locale": "en",
        }

        if departure_date_to:
            args["departureDateTo"] = _to_kiwi_date(departure_date_to)
            args["departureDateFlexDays"] = 0
        else:
            args["departureDateFlexDays"] = departure_flex_days

        if return_date:
            args["returnDate"] = _to_kiwi_date(return_date)
            if return_date_to:
                args["returnDateTo"] = _to_kiwi_date(return_date_to)
                args["returnDateFlexDays"] = 0
            else:
                args["returnDateFlexDays"] = return_flex_days

        if nights_in_dst_from is not None:
            args["nights_in_dst_from"] = nights_in_dst_from
        if nights_in_dst_to is not None:
            args["nights_in_dst_to"] = nights_in_dst_to
        if max_sector_stopovers is not None:
            args["max_sector_stopovers"] = max_sector_stopovers

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": "search-flight",
                "arguments": args,
            },
        }

        result = self._post(payload, timeout=30)
        return result or {}


def parse_kiwi_response(raw: dict, fly_from: str, fly_to: str) -> list[dict]:
    """Parse Kiwi MCP JSON-RPC response into normalised flight dicts.

    Returns a list of round-trip offer dicts ready for display or caching.
    """
    result = raw.get("result", {})
    content = result.get("content", [])

    if not content:
        return []

    # Find the text content with JSON data
    data = None
    for c in content:
        if c.get("type") == "text":
            try:
                data = json.loads(c["text"])
            except (json.JSONDecodeError, KeyError):
                continue
            break

    if not data:
        return []

    itineraries = data.get("itineraries", [])
    flights = []

    for it in itineraries:
        ob = it.get("outbound", {})
        ib = it.get("inbound")

        # Outbound segments
        ob_segs = ob.get("segments", [])
        ob_from = ob_segs[0]["from"] if ob_segs else fly_from
        ob_to = ob_segs[-1]["to"] if ob_segs else fly_to
        ob_carrier = ob_segs[0].get("carrierName", "") if ob_segs else ""
        ob_flight_no = ob_segs[0].get("flightNumber", "") if ob_segs else ""
        ob_dep = ob.get("departureTime", "")
        ob_arr = ob.get("arrivalTime", "")
        ob_stops = ob.get("stops", 0)

        flight = {
            "provider": "kiwi_mcp",
            "direction": "roundtrip" if ib else "oneway",
            "orig_airport": ob_from,
            "dest_airport": ob_to,
            "orig_metro_group": get_metro_group(ob_from),
            "dest_metro_group": get_metro_group(ob_to),
            "price_eur": it.get("price", 0),
            "price_formatted": it.get("priceFormatted", ""),
            "currency": data.get("currency", "EUR"),
            "stops": ob_stops,
            "booking_url": it.get("bookingUrl", ""),
            "outbound_date": ob_dep[:10] if ob_dep else "",
            "outbound_dep_time": ob_dep[11:16] if len(ob_dep) > 11 else "",
            "outbound_arr_time": ob_arr[11:16] if len(ob_arr) > 11 else "",
            "outbound_airline": ob_carrier,
            "outbound_flight_no": ob_flight_no,
            "is_mock": False,
        }

        if ib:
            ib_segs = ib.get("segments", [])
            ib_from = ib_segs[0]["from"] if ib_segs else fly_to
            ib_to = ib_segs[-1]["to"] if ib_segs else fly_from
            ib_carrier = ib_segs[0].get("carrierName", "") if ib_segs else ""
            ib_flight_no = ib_segs[0].get("flightNumber", "") if ib_segs else ""
            ib_dep = ib.get("departureTime", "")
            ib_arr = ib.get("arrivalTime", "")

            flight["return_orig_airport"] = ib_from
            flight["return_dest_airport"] = ib_to
            flight["return_date"] = ib_dep[:10] if ib_dep else ""
            flight["return_dep_time"] = ib_dep[11:16] if len(ib_dep) > 11 else ""
            flight["return_arr_time"] = ib_arr[11:16] if len(ib_arr) > 11 else ""
            flight["return_airline"] = ib_carrier
            flight["return_flight_no"] = ib_flight_no
            flight["return_stops"] = ib.get("stops", 0)

            # Calculate nights
            if flight["outbound_date"] and flight["return_date"]:
                try:
                    d_out = datetime.strptime(flight["outbound_date"], "%Y-%m-%d")
                    d_ret = datetime.strptime(flight["return_date"], "%Y-%m-%d")
                    flight["nights"] = (d_ret - d_out).days
                except ValueError:
                    flight["nights"] = None
            else:
                flight["nights"] = None
        else:
            flight["nights"] = None

        flights.append(flight)

    return flights


def count_kiwi_queries(
    origin_airports: list[str],
    dest_airports: list[str],
) -> int:
    """Calculate how many Kiwi MCP calls are needed.

    Kiwi MCP does NOT accept comma-separated airports –
    we must send one call per (origin, destination) pair.
    """
    count = 0
    for o in origin_airports:
        for d in dest_airports:
            if o != d:
                count += 1
    return count
