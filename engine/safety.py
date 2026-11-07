"""
engine/safety.py – Backend Circuit Breaker & API-budget guard.

Rules enforced:
  1. HARD_MAX_CALLS_PER_SEARCH = 12  (UI can lower, never raise)
  2. max_retries = 0  (no automatic retries on HTTP errors)
  3. Pre-flight /account check for SerpApi remaining quota
  4. Concurrent-search lock via st.session_state (checked at call-site in app.py)
  5. MOCK_MODE defaults to True – zero real HTTP requests while developing
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests as _requests  # only used when MOCK_MODE is False

# ---------------------------------------------------------------------------
# Hard limits (cannot be overridden by the UI)
# ---------------------------------------------------------------------------
HARD_MAX_CALLS_PER_SEARCH = 12
MAX_RETRIES = 0  # never retry

# ---------------------------------------------------------------------------
# Default mode – ALWAYS starts as True
# ---------------------------------------------------------------------------
MOCK_MODE = True


@dataclass
class BudgetReport:
    """Result of a pre-flight budget check."""

    cached_queries: int = 0
    http_queries_needed: int = 0
    serpapi_searches_left: int | None = None  # None when using Kiwi (no limit)
    blocked: bool = False
    block_reason: str = ""
    details: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SerpApi account check (does NOT consume a search credit)
# ---------------------------------------------------------------------------
def check_serpapi_account(api_key: str) -> dict:
    """Call GET https://serpapi.com/account?api_key=... and return JSON.

    Returns an empty dict on error (never retries).
    """
    if MOCK_MODE:
        return {
            "plan_searches_left": 999,
            "account_email": "mock@example.com",
            "total_searches_left": 999,
        }
    try:
        resp = _requests.get(
            "https://serpapi.com/account",
            params={"api_key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Pre-flight budget calculation (Dry-Run)
# ---------------------------------------------------------------------------
def calculate_search_cost(
    total_queries: int,
    cached_queries: int,
    provider: str,
    api_key: str | None = None,
    user_max_calls: int = HARD_MAX_CALLS_PER_SEARCH,
) -> BudgetReport:
    """Compute exactly how many HTTP calls are needed and whether we can afford them.

    Parameters
    ----------
    total_queries : int
        Total number of query permutations (origin×dest chunks × date combos).
    cached_queries : int
        How many of those are already satisfied by SQLite cache.
    provider : str
        'serpapi_gf', 'serpapi_explore', 'kiwi_mcp', or 'mock'.
    api_key : str | None
        SerpApi key (needed only for serpapi_* providers).
    user_max_calls : int
        User-chosen cap from UI slider (1..5).
    """
    report = BudgetReport()
    report.cached_queries = cached_queries

    effective_max = min(user_max_calls, HARD_MAX_CALLS_PER_SEARCH)
    http_needed = total_queries - cached_queries
    report.http_queries_needed = http_needed

    # ---- Hard cap ----
    if http_needed > effective_max:
        report.blocked = True
        report.block_reason = (
            f"Potrzeba {http_needed} zapytań HTTP, ale twardy limit to {effective_max}. "
            f"Zawęź kryteria wyszukiwania lub wyczyść filtr cache."
        )
        return report

    # ---- SerpApi quota check ----
    if provider.startswith("serpapi") and not MOCK_MODE:
        if not api_key:
            report.blocked = True
            report.block_reason = "Brak klucza SERPAPI_API_KEY w pliku .env"
            return report

        account = check_serpapi_account(api_key)
        if "error" in account:
            report.blocked = True
            report.block_reason = f"Nie udało się sprawdzić konta SerpApi: {account['error']}"
            return report

        left = account.get("plan_searches_left", 0)
        report.serpapi_searches_left = left
        if left < http_needed:
            report.blocked = True
            report.block_reason = (
                f"SerpApi: pozostało {left} zapytań, potrzeba {http_needed}. "
                f"Limit zostałby przekroczony – blokuję wysyłkę."
            )
            return report

        report.details.append(f"SerpApi: pozostało {left} zapytań po odjęciu kosztu.")

    # ---- Kiwi MCP – no quota, but still honour hard max ----
    if provider == "kiwi_mcp":
        report.details.append("Kiwi MCP: brak limitu zapytań (darmowy endpoint).")

    # ---- Mock ----
    if provider == "mock":
        report.details.append("Tryb MOCK – żadne zapytania HTTP nie zostaną wysłane.")

    return report


# ---------------------------------------------------------------------------
# Safe HTTP caller (single-shot, no retries)
# ---------------------------------------------------------------------------
class APIError(Exception):
    """Raised on any HTTP error – the caller must NOT retry."""


_call_counter: dict[str, int] = {}  # per-search call counter


def reset_call_counter(search_id: str):
    _call_counter[search_id] = 0


def safe_http_get(
    url: str,
    params: dict,
    search_id: str,
    user_max_calls: int = HARD_MAX_CALLS_PER_SEARCH,
    timeout: int = 15,
) -> dict:
    """Perform a SINGLE HTTP GET with zero retries and hard-cap enforcement.

    Raises APIError on any failure.
    """
    effective_max = min(user_max_calls, HARD_MAX_CALLS_PER_SEARCH)

    current = _call_counter.get(search_id, 0)
    if current >= effective_max:
        raise APIError(
            f"Osiągnięto twardy limit {effective_max} zapytań HTTP dla tego wyszukiwania."
        )
    _call_counter[search_id] = current + 1

    try:
        resp = _requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except _requests.exceptions.HTTPError as exc:
        raise APIError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except _requests.exceptions.Timeout:
        raise APIError(f"Timeout po {timeout}s dla {url}") from None
    except _requests.exceptions.RequestException as exc:
        raise APIError(f"Błąd sieciowy: {exc}") from exc


def safe_http_post(
    url: str,
    json_body: dict,
    search_id: str,
    user_max_calls: int = HARD_MAX_CALLS_PER_SEARCH,
    timeout: int = 15,
) -> dict:
    """Perform a SINGLE HTTP POST with zero retries and hard-cap enforcement.

    Used for Kiwi MCP JSON-RPC calls.
    Raises APIError on any failure.
    """
    effective_max = min(user_max_calls, HARD_MAX_CALLS_PER_SEARCH)

    current = _call_counter.get(search_id, 0)
    if current >= effective_max:
        raise APIError(
            f"Osiągnięto twardy limit {effective_max} zapytań HTTP dla tego wyszukiwania."
        )
    _call_counter[search_id] = current + 1

    try:
        resp = _requests.post(url, json=json_body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except _requests.exceptions.HTTPError as exc:
        raise APIError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except _requests.exceptions.Timeout:
        raise APIError(f"Timeout po {timeout}s dla {url}") from None
    except _requests.exceptions.RequestException as exc:
        raise APIError(f"Błąd sieciowy: {exc}") from exc
