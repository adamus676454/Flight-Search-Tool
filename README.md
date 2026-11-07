# AZair Extended – Local Multi-Engine Flight Search & SQL Matcher

A fast, developer-focused low-cost flight search radar built with **Python, Streamlit, and SQLite**. It combines **Kiwi.com MCP** (keyless flexible range scanning) and **SerpApi Google Flights** (multi-airport chunking) with a local **SQL JOIN matching engine** to discover the cheapest one-way and round-trip flight combinations across multiple airports and metropolitan regions.

> *Built iteratively with AI assistance alongside custom architectural design, local SQLite caching optimizations, and domain-specific flight matching rules.*

---

## Why I Built This (The Problem)

When hunting for ultra-cheap flights across Europe, the Mediterranean, Caucasus, and Maghreb with flexible dates, existing tools fall short in different ways:

* **AZair.eu** – Great logic for combining low-cost flights, but **severely limited when searching more than ~3 months ahead** (incomplete schedules and missing routes for future seasons).
* **Kiwi.com** – Powerful backend data, but a **heavy commercial UI** that makes it tedious to rapidly scan raw tabular data, compare custom airport groups, or filter combinations locally without re-running slow searches.
* **Flightlist.io** – Good for simple one-way lists, but **lacks automated round-trip pairing (matching outbound and inbound legs by stay duration)**, cross-airport metropolitan returns (e.g., flying into Milan Bergamo `BGY` and returning from Milan Malpensa `MXP` to a different Polish airport like `KRK` ↔ `KTW`), and simultaneous weekday filtering.

**AZair Extended** solves this by pulling flight schedules into a **local SQLite database (`WAL` mode)** and running custom **SQL JOIN matchers**, set-inclusion cache checks, and instant in-memory / SQL filters locally—minimizing external API calls.

---

## Key Features

* **2 Complementary Search Engines:**
  * **1. Kiwi MCP Flexible (Free / Keyless):** Connects directly to `mcp.kiwi.com` over Streamable HTTP (JSON-RPC 2.0 / SSE) to scan wide departure/return date windows and stay durations (`min–max` nights) at zero SerpApi cost.
  * **2. Exact + SQL Matcher (SerpApi Google Flights):** Queries Google Flights in batched airport chunks (**up to 6 origin IATA codes × 6 destination IATA codes in a single API call**) and pairs outbound + inbound one-way legs locally in SQLite. Includes a real-time **6-airport chunk efficiency hint** so you never waste free slots in a request.
* **Cross-Airport & Metro Group Matching (`engine/matcher.py`):**
  * Automatically pairs flights within destination metropolitan areas (e.g., land at `FCO`, return from `CIA` in Rome; `BGY`/`MXP`/`LIN` in Milan; `BCN`/`GRO`/`REU` in Barcelona; `CTA`/`CIY` in East Sicily).
  * Optional flexible return to any airport in your origin group (e.g., depart from `KTW`, return to `KRK`).
* **Smart Set-Inclusion Cache & Zero-API Mode (`engine/db.py`):**
  * **Range Coverage Optimization:** If you previously fetched Feb 5–7 for a route in Kiwi MCP, searching Feb 5–6 makes **0 HTTP requests**, and searching Feb 5–8 fetches **only the missing Feb 8 subrange** and merges the full dataset from SQLite.
  * **`3. Load from SQLite (0 API)` Button:** Instantly query and match all previously cached flights in SQLite without sending a single network request.
  * **72h Default Cache TTL (adjustable up to 336h / 14 days):** Preserves multi-session weekend deal hunting without burning API credits.
* **Interactive Airport Autocomplete & Schedule Intelligence:**
  * **City + IATA Autocomplete:** Type city names or codes (e.g. `Krakow (KRK)`, `Lodz (LCJ)`, `Marrakesh (RAK)`) or select entire regions (`ITALY_NORTH`, `MAGHREB_MOROCCO`, `PL_ALL`) and uncheck individual airports you want to exclude.
  * **Auto-Weekday Detection:** When selecting a departure or return window shorter than 7 days (e.g., Feb 24–27), the app automatically selects only the weekdays present in that window while still allowing manual adjustments.
* **Live In-Memory Table Filters & Column Value Extractor:**
  * Filter displayed results in real time by Departure/Return Date Range, Nights (`Min–Max`), Max Price (`€`), Destination Airports, Weekdays, Carriers, and Direct Flights—with numeric `float` price sorting.
  * **Column Value Extractor:** Drill down into any column (e.g. extract only `BCN`, `CTA` or specific routes) across both search tabs and the SQL Console.
* **Strict API Quota & Rate-Limit Protection (`engine/safety.py`):**
  * **1. Dry-Run Calculator:** Preview exact cache hits, missing date subranges, and required HTTP calls before executing any search.
  * **Circuit Breaker & Risky Threshold:** Hard cap of `12` HTTP calls per search (`max_retries = 0`), with UI slider warnings (`"5 (risky)" .. "12 (risky)"`) and adaptive random HTTP jitter (`1.2–3.5s`) to prevent quota drain and HTTP 429 rate limits.
  * **Mock Mode Default:** Starts in `MOCK_MODE = True` by default for offline testing with zero network traffic.
* **Bilingual UI (`EN` / `PL`):**
  * Full English (default) and Polish interface switcher in the top bar, including dynamic calendar popup localization and translated city/country names.
* **Built-In Read-Only SQL Console:**
  * Expandable SQLite console at the bottom of the page with 6 one-click analytical presets (cheapest live flights, direct `<= 100 EUR`, whole-DB One-Way SQL JOIN Matcher, route `MIN/AVG/MAX` price stats, query history) and custom `SELECT / WITH / PRAGMA` query execution.

---

## Tech Stack & Repository Structure

```text
├── .streamlit/
│   └── config.toml          # SaaS Slate & Blue light theme configuration for Streamlit
├── app.py                   # Streamlit UI (2 search tabs, live filters, EN/PL i18n, SQL console)
├── config.py                # Hardcoded IATA dictionaries, Polish/EU origin groups, metro groups
├── engine/
│   ├── db.py                # SQLite WAL storage, query hashing, set-inclusion cache & range diffing
│   ├── matcher.py           # Parameterized SQL JOIN engine pairing outbound & inbound legs
│   └── safety.py            # Circuit breaker, HTTP call counters, SerpApi /account quota check
├── providers/
│   ├── kiwi_mcp.py          # Streamable HTTP / SSE JSON-RPC 2.0 client for mcp.kiwi.com
│   ├── serpapi_client.py    # Google Flights REST client with 6-airport chunking
│   └── mock_provider.py     # Deterministic mock flight generator for offline testing
├── test_quick.py            # 13-suite offline unit & integration test runner
├── probe_kiwi.py            # Diagnostic CLI script to inspect Kiwi MCP protocol & tool schemas
├── test_kiwi_live.py        # Manual CLI script for testing a single live Kiwi MCP call
├── requirements.txt         # Python dependencies (streamlit, pandas, requests, python-dotenv)
├── .env.example             # Template for environment variables (SERPAPI_API_KEY)
├── .gitignore               # Git exclusion rules (protects .env, .venv/, and data/*.db)
├── LICENSE                  # PolyForm Noncommercial License 1.0.0
└── README.md                # Project documentation
```

---

## Getting Started

### 1. Prerequisites

* **Python 3.10+** (tested on Python 3.12 / Ubuntu WSL)
* *(Optional)* A **SerpApi API Key** for Tab 2 (Exact + SQL Matcher). Tab 1 (Kiwi MCP Flexible), Load from SQLite (0 API), and MOCK MODE work without any API key.

### 2. Installation

Clone the repository, create a virtual environment, and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration (.env)

Copy the example environment file and add your SerpApi key:

```bash
cp .env.example .env
```

Edit `.env`:
```env
SERPAPI_API_KEY=your_serpapi_key_here
```
*(You can also paste your API key directly into the Streamlit sidebar at runtime).*

### 4. Run the Application

```bash
.venv/bin/streamlit run app.py --server.port 8501 --server.headless true
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

> The app starts in **MOCK MODE** by default (zero live network requests). Toggle off MOCK MODE in the top bar to run live searches.

### 5. Run the Test Suite

```bash
.venv/bin/python test_quick.py
```

All 13 test suites run completely offline with zero live HTTP calls.

---

## Tips for Minimizing API & MCP Calls

1. **Pack Full Chunks of 6 Airports in SerpApi (Tab 2):** Google Flights accepts up to 6 origin IATA codes and 6 destination IATA codes in a single request. Checking 6 destination airports costs the exact same (1 API call) as checking 1 airport. Watch the chunk hint under the airport selector to fill free slots at 0 extra cost.
2. **Use the 2-Stage Funnel (Kiwi MCP → SerpApi Matcher):**
   * **Stage 1 (Free Recon):** Use Tab 1 (Kiwi MCP) with a wide date range (e.g., a whole month) on a few key airports to spot the cheapest weeks for 0 SerpApi credits.
   * **Stage 2 (One-Way Combos):** Switch to Tab 2 (Exact + SQL Matcher), select a narrow 3–5 day window (or specific weekdays like Thu/Fri outbound and Sun/Mon return) across 6 airports to build cross-carrier and cross-metro one-way combinations.
3. **Leverage `3. Load from SQLite (0 API)`:** Every search is persisted in `data/flights.db`. Use button 3 or the bottom SQL Console to re-match and filter historical flights offline.

---

## Completed Milestones & Roadmap

- [x] **Unified Date & Stay Filtering:** Simultaneous filtering by Departure Date Range (FROM–TO), Return Date Range (FROM–TO), Stay Duration (Min–Max Nights), and Allowed Weekdays across all tabs and SQLite matchers.
- [x] **Set-Inclusion Cache Optimization:** Automatic date-range diffing for Kiwi MCP so overlapping or subset searches never re-fetch cached days.
- [x] **Clean SaaS Slate & Blue UI + Full EN/PL Localization:** Monospace tabular numerals (JetBrains Mono), proper float price sorting, and dynamic calendar localization.
- [x] **Interactive Airport Autocomplete & Region Unchecking:** Full support for all Polish regional airports (KRK, KTW, WRO, RZE, WAW, WMI, LCJ, RDO, GDN, POZ, SZZ, BZG, LUZ, SZY, IEG), nearby hubs (VIE, BUD, BTS, OSR, PRG, BER, KSC, VNO, KUN), and 150+ European/Mediterranean destinations.
- [ ] **Multi-Hop / Self-Transfer Hub Finder:** Experimental SQLite self-transfer chaining via major European low-cost hubs (BGY, STN, CRL, EIN).
- [ ] **CSV / Parquet Export & Price History Alerts:** Track route price changes across multiple cached snapshots over time.

---

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).

You are welcome to download, run locally, and modify this tool for personal, educational, and other non-commercial purposes. Any commercial use—including paid hosting, commercial SaaS deployment, or reselling—requires prior written permission from the author.

*This is source-available software (not OSI-approved open source) and is provided "as is", without warranty of any kind.*
