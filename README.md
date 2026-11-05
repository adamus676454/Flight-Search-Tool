# ✈️ AZair Extended – Local Multi-Engine Flight Search & SQL Matcher

A local, developer-focused flight search tool built with **Python, Streamlit, and SQLite**. It combines **Kiwi.com MCP** and **SerpApi (Google Flights / Explore)** with a local SQL matching engine to find the cheapest one-way and round-trip flight combinations across multiple airports and metropolitan regions.

> ⚠️ **Project Status: Work in Progress (Alpha)**  
> This is a personal tool built to solve my own travel-planning frustrations. It is functional and actively used, but still has minor UI/UX bugs and incomplete features (see [Roadmap / Known Issues](#-roadmap--known-issues)).

---

## 💡 Why I Built This (The Problem)

When searching for ultra-cheap flights across Europe with flexible dates, existing tools all fall short in different ways:

* **AZair.eu** – Great logic for combining low-cost flights, but **severely limited when searching more than ~3 months ahead** (incomplete schedules and missing routes for future seasons).
* **Kiwi.com** – Powerful backend data, but a **clunky, heavy UI** that makes it tedious to rapidly scan raw tabular data, compare multiple custom airport groups, or analyze raw legs without commercial clutter.
* **Flightlist.io** – Good for simple one-way lists, but **lacks automated round-trip pairing (matching outbound and inbound legs by stay duration)**, cross-airport metropolitan returns (e.g., flying into Milan Bergamo `BGY` and returning from Milan Malpensa `MXP` to a different home airport like `KRK` ↔ `KTW`), and simultaneous weekday filtering.

**AZair Extended** bridges these gaps by pulling raw flight schedules into a **local SQLite database** and running custom **SQL JOIN matchers** and interactive SQL queries locally—without burning through API quotas.

---

## 🚀 Key Features

* **3 Specialized Search Modes:**
  * **🌍 Tab A (Explore Radar):** Uses Google Travel Explore (`serpapi`) to scan an entire country/region for a given month in a single API call.
  * **🛫 Tab B (Kiwi MCP Flexible):** Connects directly to `mcp.kiwi.com` (keyless JSON-RPC/SSE) for flexible date ranges and stay durations.
  * **🎯 Tab C (Exact + Local SQL Matcher):** Queries Google Flights in batched airport chunks (up to 6 IATA codes per request) and pairs outbound + inbound one-way legs locally in SQLite.
* **Cross-Airport & Metro Group Matching:** Automatically pairs flights within defined origin groups (e.g., Southern Poland: `KRK, KTW, WRO, RZE`) and destination metro areas (e.g., Milan, Rome, Sicily).
* **Strict API Quota Protection (`safety.py`):**
  * **Dry-Run Cost Calculator:** Preview exact cache hits vs. live HTTP calls before executing any search.
  * **Hard Circuit Breaker:** Hard cap of max 5 HTTP requests per search execution and `max_retries = 0` to prevent accidental quota drain.
  * **Mock Mode Default:** Starts in `MOCK_MODE = True` by default so you can test the UI and SQL matcher with zero network traffic.
* **Persistent SQLite Cache & Interactive SQL Console:**
  * All fetched legs and full JSON payloads (`raw_json`) are stored locally in `data/flights.db`.
  * Built-in **SQL Console** at the bottom of the UI with one-click presets and custom `SELECT` query support to slice, filter, and sort your cached flights any way you want.

---

## 🛠️ Tech Stack & Architecture

```text
├── app.py                  # Streamlit UI (3 search tabs + interactive SQL cache console)
├── config.py               # IATA dictionaries, origin groups, metro groups, KGMIDs
├── engine/
│   ├── db.py               # SQLite WAL storage, query hashing, TTL cache & raw_json unpacking
│   ├── matcher.py          # Local SQL JOIN engine pairing outbound & inbound legs
│   └── safety.py           # Circuit breaker, HTTP call counters, SerpApi account check
├── providers/
│   ├── kiwi_mcp.py         # Streamable HTTP / SSE client for mcp.kiwi.com
│   ├── serpapi_client.py   # Google Flights & Explore REST client with 6-airport chunking
│   └── mock_provider.py    # Deterministic mock flight generator for offline testing
└── test_quick.py           # Unit & integration test suite



⚡ Getting Started
1. Prerequisites

    Python 3.10+

    (Optional) A SerpApi API Key for Tab A & Tab C (Tab B uses Kiwi MCP and works without an API key, and Mock Mode works completely offline).

    
2. Installation

Clone the repository and set up a virtual environment.

pip install streamlit pandas requests python-dotenv

3. Configuration (.env)

Copy the example environment file and add your SerpApi key:
Bash

cp .env.example .env

Edit .env:
Fragment kodu

SERPAPI_API_KEY=your_serpapi_key_here

(You can also paste your API key directly into the Streamlit sidebar at runtime).
4. Run the Application
Bash

streamlit run app.py --server.port 8501

Open http://localhost:8501 in your browser.

    To run live searches, toggle off 🔒 MOCK MODE at the top of the page.

5. Run Tests
Bash

python test_quick.py

🔧 Roadmap & Known Issues

This project is actively evolving. Current focus areas for upcoming iterations include:

    [ ] Unified Date & Stay Filtering Across All Tabs: Support simultaneous filtering by Departure Date Range (From–To), Return Date Range (From–To), Stay Duration Range (Min–Max Nights), and Allowed Weekdays (Outbound & Return) uniformly across Tabs A, B, and C.

    [ ] UI/UX Polish: Clean up compact CSS spacing, improve header/toggle visibility, and refine table column formatting.

    [ ] Bug Fixes: Iron out minor edge cases in cache reconstruction, state persistence between tab switches, and local table filters.

    [ ] More Granular SQL Presets: Expand the built-in SQL console with more analytical views and multi-leg combinations.

📄 License

MIT License — feel free to fork, modify, and adapt for your own travel hacking.