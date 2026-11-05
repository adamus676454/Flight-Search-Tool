"""
app.py – AZair Extended – Streamlit UI.

Compact AZair-style layout with 3 search tabs.
DEFAULT: MOCK_MODE = True (zero real HTTP requests).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from config import (
    AIRPORT_CITY_NAMES,
    CURRENCY,
    DEFAULT_CACHE_TTL_HOURS,
    DESTINATION_REGIONS,
    EXPLORE_KGMID,
    METRO_GROUPS,
    ORIGIN_GROUPS,
    get_city_name,
    get_metro_group,
)
from engine import db, safety
from engine.matcher import match_roundtrips
from providers.mock_provider import (
    generate_mock_explore,
    generate_mock_flights,
    generate_mock_kiwi_flights,
)
from providers import serpapi_client, kiwi_mcp

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AZair Extended – Tanie loty",
    page_icon="✈️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Compact AZair-style CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Reduce top padding */
    .block-container { padding-top: 3.5rem; padding-bottom: 0.5rem; }
    /* Compact widget spacing */
    div[data-testid="stVerticalBlock"] > div { padding-bottom: 0; }
    div[data-testid="column"] { padding: 0 0.3rem; }
    /* Smaller headings */
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { padding: 4px 12px; font-size: 0.85rem; }
    /* Compact inputs */
    .stSelectbox, .stMultiselect, .stDateInput, .stNumberInput {
        margin-bottom: 0.15rem;
    }
    .stSelectbox label, .stMultiselect label, .stDateInput label,
    .stNumberInput label, .stCheckbox label, .stRadio label {
        font-size: 0.82rem !important;
        margin-bottom: 0 !important;
    }
    /* Compact dataframe */
    .stDataFrame { font-size: 0.8rem; }
    /* Tight metric */
    div[data-testid="stMetric"] { padding: 0; }
    div[data-testid="stMetric"] label { font-size: 0.75rem !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "search_running": False,
        "dry_run_result": None,
        "search_results": None,
        "explore_results": None,
        "kiwi_results": None,
        "exact_results": None,
        "mock_mode": True,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

# ---------------------------------------------------------------------------
# Header (compact)
# ---------------------------------------------------------------------------
hdr_col1, hdr_col2, hdr_col3 = st.columns([4, 2, 2])
with hdr_col1:
    st.markdown("## ✈️ AZair Extended")
with hdr_col2:
    mock_toggle = st.toggle("🔒 MOCK MODE", value=st.session_state.mock_mode, key="mock_toggle_main")
    st.session_state.mock_mode = mock_toggle
    safety.MOCK_MODE = mock_toggle
with hdr_col3:
    if st.session_state.mock_mode:
        st.warning("Dane testowe", icon="🟡")
    else:
        st.success("Tryb LIVE", icon="🟢")

# ---------------------------------------------------------------------------
# Sidebar – settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Ustawienia")

    user_max_calls = st.slider(
        "Maks. zapytań HTTP / wyszukiwanie",
        min_value=1, max_value=5, value=3,
        help=f"Twardy limit backendu: {safety.HARD_MAX_CALLS_PER_SEARCH}.",
    )

    cache_ttl = st.slider(
        "Cache TTL (godziny)",
        min_value=1, max_value=168, value=DEFAULT_CACHE_TTL_HOURS,
    )

    if st.button("🗑️ Wyczyść cache"):
        conn = db.get_connection()
        db.clear_cache(conn)
        conn.close()
        st.success("Cache wyczyszczony.")

    st.divider()
    st.subheader("🔑 SerpApi")
    serpapi_key_input = st.text_input(
        "API Key", value=SERPAPI_API_KEY, type="password",
        help="Lub ustaw SERPAPI_API_KEY w .env",
    )
    effective_api_key = serpapi_key_input or SERPAPI_API_KEY

    if effective_api_key:
        account = safety.check_serpapi_account(effective_api_key)
        left = account.get("plan_searches_left", "?")
        st.metric("Zapytania pozostałe", left)
    else:
        st.info("Ustaw SERPAPI_API_KEY.")

    st.divider()
    st.caption(
        f"Waluta: {CURRENCY} | Cache: {cache_ttl}h | "
        f"Limit: {safety.HARD_MAX_CALLS_PER_SEARCH}/wyszuk."
    )


# ---------------------------------------------------------------------------
# Helper: airport multiselect with groups
# ---------------------------------------------------------------------------
def _compact_airport_selector(
    label_group: str,
    groups: dict[str, list[str]],
    key_prefix: str,
    manual_label: str = "Ręcznie (IATA)",
    show_manual: bool = True,
) -> list[str]:
    """Compact airport selector: group dropdown + multiselect of individual airports."""
    group_names = list(groups.keys())
    selected_groups = st.multiselect(
        label_group,
        options=group_names,
        key=f"{key_prefix}_groups",
    )

    airports: list[str] = []
    for g in selected_groups:
        airports.extend(groups[g])
    airports = list(dict.fromkeys(airports))

    if airports:
        # Allow user to deselect individual airports
        labels = {c: f"{c} ({get_city_name(c)})" for c in airports}
        selected = st.multiselect(
            "Lotniska",
            options=airports,
            default=airports,
            format_func=lambda x: labels.get(x, x),
            key=f"{key_prefix}_airports",
        )
        airports = selected

    if show_manual:
        manual = st.text_input(manual_label, key=f"{key_prefix}_manual")
        if manual:
            extras = [c.strip().upper() for c in manual.split(",") if c.strip()]
            airports = list(dict.fromkeys(airports + extras))

    return airports


# ---------------------------------------------------------------------------
# Helper: format results tables
# ---------------------------------------------------------------------------
def _format_matched_results(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        mock_flag = " 🟡MOCK" if r.get("is_mock") else ""
        records.append({
            "Total EUR": f"{r['total_eur']:.0f} € ({r['price_out_eur']:.0f}+{r['price_ret_eur']:.0f})",
            "Outbound": f"{r['out_orig']}→{r['out_dest']}",
            "Out Date": f"{r['out_date']} {r.get('out_dep_time', '')}",
            "Out Airline": f"{r.get('out_airline', '')} {r.get('out_flight_no', '')}",
            "Return": f"{r['ret_orig']}→{r['ret_dest']}",
            "Ret Date": f"{r['ret_date']} {r.get('ret_dep_time', '')}",
            "Ret Airline": f"{r.get('ret_airline', '')} {r.get('ret_flight_no', '')}",
            "Nights": r["nights"],
            "Stops": f"{r.get('out_stops', 0)}+{r.get('ret_stops', 0)}",
            "Source": f"{r.get('out_provider', '')}{mock_flag}",
        })
    return pd.DataFrame(records)


def _format_kiwi_results(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        mock_flag = " 🟡MOCK" if r.get("is_mock") else ""
        price_detail = ""
        if r.get("price_outbound_eur") is not None and r.get("price_return_eur") is not None:
            price_detail = f" ({r['price_outbound_eur']:.0f}+{r['price_return_eur']:.0f})"

        ret_orig = r.get("return_orig_airport", r.get("dest_airport", ""))
        ret_dest = r.get("return_dest_airport", r.get("orig_airport", ""))

        rec = {
            "Total EUR": f"{r['price_eur']:.0f} €{price_detail}",
            "Outbound": f"{r['orig_airport']}→{r['dest_airport']}",
            "Out Date": f"{r.get('outbound_date', '')} {r.get('outbound_dep_time', '')}",
            "Out Airline": f"{r.get('outbound_airline', '')} {r.get('outbound_flight_no', '')}",
            "Return": f"{ret_orig}→{ret_dest}",
            "Ret Date": f"{r.get('return_date', '')} {r.get('return_dep_time', '')}",
            "Ret Airline": f"{r.get('return_airline', '')} {r.get('return_flight_no', '')}",
            "Nights": r.get("nights", "?"),
            "Stops": r.get("stops", 0),
            "Source": f"Kiwi{mock_flag}",
        }

        # Add booking URL if available
        if r.get("booking_url"):
            rec["Book"] = r["booking_url"]

        records.append(rec)
    return pd.DataFrame(records)


def _apply_local_filters(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    if df.empty:
        return df

    c1, c2, c3 = st.columns(3)
    with c1:
        max_price = st.number_input("Max EUR", min_value=0, max_value=2000, value=500, step=10, key=f"{key_prefix}_flt_mp")
    with c2:
        airline_cols = [c for c in df.columns if "Airline" in c]
        all_airlines: set[str] = set()
        for col_name in airline_cols:
            all_airlines.update(v.strip() for v in df[col_name].dropna().unique() if v.strip())
        selected_airlines = st.multiselect("Przewoźnicy", sorted(all_airlines), key=f"{key_prefix}_flt_al")
    with c3:
        direct_only = st.checkbox("Tylko bezpośrednie", key=f"{key_prefix}_flt_dir")

    filtered = df.copy()

    # Price filter
    if "Total EUR" in filtered.columns:
        filtered["_p"] = filtered["Total EUR"].apply(
            lambda x: float(str(x).split("€")[0].strip().replace(" ", "")) if "€" in str(x) else 9999
        )
        filtered = filtered[filtered["_p"] <= max_price].drop(columns=["_p"])

    # Airline filter
    if selected_airlines:
        mask = pd.Series(False, index=filtered.index)
        for col_name in airline_cols:
            if col_name in filtered.columns:
                for al in selected_airlines:
                    mask |= filtered[col_name].str.contains(al, case=False, na=False)
        filtered = filtered[mask]

    # Direct only
    if direct_only and "Stops" in filtered.columns:
        filtered = filtered[
            filtered["Stops"].apply(lambda x: str(x).replace(" ", "") in ("0", "0+0"))
        ]

    return filtered


# ---------------------------------------------------------------------------
# Weekday helpers
# ---------------------------------------------------------------------------
WEEKDAYS_PL = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]
WEEKDAY_MAP = {0: "Pn", 1: "Wt", 2: "Śr", 3: "Cz", 4: "Pt", 5: "Sb", 6: "Nd"}


def _generate_dates_in_range(
    date_from: datetime,
    date_to: datetime,
    allowed_weekdays: list[str] | None = None,
) -> list[str]:
    """Generate list of ISO date strings in range, filtered by weekday."""
    dates = []
    current = date_from
    while current <= date_to:
        if allowed_weekdays is None or WEEKDAY_MAP[current.weekday()] in allowed_weekdays:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


# =========================================================================
# TABS
# =========================================================================
tab_explore, tab_kiwi, tab_exact = st.tabs([
    "🌍 A: Explore",
    "🛫 B: Kiwi Flexible",
    "🎯 C: Exact + Matcher",
])


# =========================================================================
# TAB A: Explore
# =========================================================================
with tab_explore:
    st.caption("Najtańsze kierunki w kraju/regionie – 1 zapytanie API")

    ea1, ea2, ea3, ea4, ea5 = st.columns([2, 2, 1.5, 1.5, 1])
    with ea1:
        explore_origin_group = st.selectbox(
            "Wylot z", list(ORIGIN_GROUPS.keys()), key="ea_og",
        )
        explore_airports = ORIGIN_GROUPS[explore_origin_group]
        explore_departure_id = ",".join(explore_airports)
        st.caption(", ".join(f"{c}" for c in explore_airports))

    with ea2:
        explore_country = st.selectbox(
            "Kraj docelowy", list(EXPLORE_KGMID.keys()), key="ea_country",
        )

    with ea3:
        explore_month_num = st.selectbox(
            "Miesiąc wylotu", list(range(1, 13)),
            index=(datetime.now().month + 1) % 12,
            format_func=lambda m: ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze",
                                    "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"][m - 1],
            key="ea_month",
        )
        # Determine year
        now = datetime.now()
        explore_year = now.year if explore_month_num > now.month else now.year + 1
        explore_month = f"{explore_year}-{explore_month_num:02d}"

    with ea4:
        explore_duration = st.selectbox(
            "Długość", ["Weekend (3)", "1 tydzień (7)", "2 tygodnie (14)"],
            index=1, key="ea_dur",
        )
        dur_map = {"Weekend (3)": "3", "1 tydzień (7)": "7", "2 tygodnie (14)": "14"}
        explore_dur_val = dur_map.get(explore_duration, "7")

    with ea5:
        explore_direct = st.checkbox("Bezpośrednie", key="ea_direct")

    # Buttons
    eb1, eb2, eb3 = st.columns([2, 2, 4])
    with eb1:
        explore_dryrun = st.button("1. Dry-Run", key="ea_dr", use_container_width=True)
    with eb2:
        explore_exec = st.button("2. Pobierz", key="ea_ex", use_container_width=True,
                                  disabled=st.session_state.search_running)

    if explore_dryrun:
        conn = db.get_connection()
        params = {
            "departure_id": explore_departure_id,
            "destination_kgmid": EXPLORE_KGMID[explore_country],
            "month": explore_month,
            "travel_duration": explore_dur_val,
        }
        qhash = db.compute_query_hash("serpapi_explore", params)
        cached = 1 if db.is_cache_valid(conn, qhash, cache_ttl) else 0
        conn.close()
        report = safety.calculate_search_cost(
            total_queries=1, cached_queries=cached,
            provider="serpapi_explore", api_key=effective_api_key,
            user_max_calls=user_max_calls,
        )
        st.info(f"📊 Cache: {cached} | HTTP: {report.http_queries_needed}")
        if report.blocked:
            st.error(f"🚫 {report.block_reason}")

    if explore_exec:
        if st.session_state.search_running:
            st.error("Inne wyszukiwanie w toku.")
        else:
            st.session_state.search_running = True
            try:
                params = {
                    "departure_id": explore_departure_id,
                    "destination_kgmid": EXPLORE_KGMID[explore_country],
                    "month": explore_month,
                    "travel_duration": explore_dur_val,
                }

                if st.session_state.mock_mode:
                    results = generate_mock_explore(
                        explore_airports[0], explore_country, explore_month
                    )
                    st.session_state.explore_results = results
                else:
                    # LIVE SerpApi call
                    search_id = str(uuid.uuid4())[:8]
                    safety.reset_call_counter(search_id)

                    qhash = db.compute_query_hash("serpapi_explore", params)
                    conn = db.get_connection()
                    if db.is_cache_valid(conn, qhash, cache_ttl):
                        cached = db.get_cached_flights(conn, qhash)
                        # Reconstruct explore results from cache
                        results = []
                        for f in cached:
                            results.append({
                                "destination_airport": f["dest_airport"],
                                "destination_city": get_city_name(f["dest_airport"]),
                                "price_eur": f["price_eur"],
                                "outbound_date": f["flight_date"],
                                "return_date": "",
                                "airline": f.get("airline", ""),
                                "source": "cache",
                                "is_mock": bool(f.get("is_mock", 0)),
                            })
                        st.session_state.explore_results = results
                    else:
                        api_params = serpapi_client.build_explore_params(
                            departure_id=explore_departure_id,
                            destination_kgmid=EXPLORE_KGMID[explore_country],
                            month=explore_month,
                            api_key=effective_api_key,
                            travel_duration=explore_dur_val,
                        )
                        try:
                            resp_data = safety.safe_http_get(
                                serpapi_client.SERPAPI_BASE_URL,
                                api_params, search_id,
                                user_max_calls=user_max_calls, timeout=20,
                            )
                            results = serpapi_client.parse_explore_response(
                                resp_data, explore_airports[0]
                            )
                            # Cache
                            if results:
                                flight_dicts = []
                                for r in results:
                                    flight_dicts.append({
                                        "provider": "serpapi_explore",
                                        "direction": "roundtrip",
                                        "orig_airport": explore_airports[0],
                                        "dest_airport": r["destination_airport"],
                                        "orig_metro_group": get_metro_group(explore_airports[0]),
                                        "dest_metro_group": get_metro_group(r["destination_airport"]),
                                        "flight_date": r.get("outbound_date", ""),
                                        "departure_time": None,
                                        "arrival_time": None,
                                        "airline": r.get("airline", ""),
                                        "flight_no": None,
                                        "price_eur": r["price_eur"],
                                        "currency": "EUR",
                                        "stops": 0,
                                        "duration_min": None,
                                        "is_mock": False,
                                    })
                                db.store_flights(conn, "serpapi_explore", params,
                                                 flight_dicts, is_mock=False)
                            st.session_state.explore_results = results
                        except safety.APIError as e:
                            st.error(f"❌ Błąd API: {e}")
                    conn.close()
            finally:
                st.session_state.search_running = False

    # Display explore results
    if st.session_state.explore_results:
        results = st.session_state.explore_results
        df = pd.DataFrame(results)
        if not df.empty:
            df["Miasto"] = df["destination_airport"].apply(get_city_name)
            df = df.rename(columns={
                "destination_airport": "IATA",
                "price_eur": "Cena EUR",
                "outbound_date": "Wylot",
                "return_date": "Powrót",
                "airline": "Linia",
                "source": "Źródło",
            })
            display_cols = ["Miasto", "IATA", "Cena EUR", "Wylot", "Powrót", "Linia", "Źródło"]
            st.dataframe(df[[c for c in display_cols if c in df.columns]],
                         use_container_width=True, hide_index=True)


# =========================================================================
# TAB B: Kiwi MCP Flexible
# =========================================================================
with tab_kiwi:
    st.caption("Oferty z elastycznym oknem dat – Kiwi.com MCP")

    kb1, kb2, kb3, kb4 = st.columns([2, 2, 2, 2])

    with kb1:
        st.markdown("**Skąd**")
        kiwi_origins = _compact_airport_selector(
            "Grupa wylotu", ORIGIN_GROUPS, "kb_orig",
        )

    with kb2:
        st.markdown("**Dokąd**")
        kiwi_dest_source = st.radio(
            "Źródło", ["Region", "Metro"], key="kb_dsrc", horizontal=True,
        )
        if kiwi_dest_source == "Region":
            kiwi_dest_sel = st.multiselect(
                "Region docelowy", list(DESTINATION_REGIONS.keys()), key="kb_dreg",
            )
            kiwi_dests_raw: list[str] = []
            for r in kiwi_dest_sel:
                kiwi_dests_raw.extend(DESTINATION_REGIONS[r])
        else:
            kiwi_dest_sel = st.multiselect(
                "Grupa metro", list(METRO_GROUPS.keys()), key="kb_dmet",
            )
            kiwi_dests_raw = []
            for m in kiwi_dest_sel:
                kiwi_dests_raw.extend(METRO_GROUPS[m])

        kiwi_manual = st.text_input("Ręcznie (IATA)", key="kb_dman")
        if kiwi_manual:
            kiwi_dests_raw.extend(c.strip().upper() for c in kiwi_manual.split(",") if c.strip())
        kiwi_dests = list(dict.fromkeys(kiwi_dests_raw))

        if kiwi_dests:
            st.caption(f"{len(kiwi_dests)} lotnisk: {', '.join(kiwi_dests[:10])}{'…' if len(kiwi_dests)>10 else ''}")

    with kb3:
        st.markdown("**Kiedy & pobyt**")
        kiwi_date_from = st.date_input(
            "Wylot OD", value=datetime.now().date() + timedelta(days=14), key="kb_df",
        )
        kiwi_date_to = st.date_input(
            "Wylot DO", value=datetime.now().date() + timedelta(days=20), key="kb_dt",
        )
        kc1, kc2 = st.columns(2)
        with kc1:
            kiwi_nmin = st.number_input("Min nocy", value=3, min_value=1, key="kb_nmin")
        with kc2:
            kiwi_nmax = st.number_input("Max nocy", value=10, min_value=1, key="kb_nmax")

    with kb4:
        st.markdown("**Opcje & Start**")
        kiwi_max_price = st.number_input("Max cena €", value=200, min_value=0, step=10, key="kb_maxp")
        kiwi_direct = st.checkbox("Bezpośrednie", key="kb_dir")

        kiwi_dryrun = st.button("1. Dry-Run", key="kb_dr", use_container_width=True)
        kiwi_exec = st.button("2. Pobierz", key="kb_ex", use_container_width=True,
                               disabled=st.session_state.search_running)

    if kiwi_dryrun and kiwi_origins and kiwi_dests:
        total_q = kiwi_mcp.count_kiwi_queries(kiwi_origins, kiwi_dests)
        conn = db.get_connection()
        cached_count = 0
        for orig in kiwi_origins:
            for dest in kiwi_dests:
                if orig == dest:
                    continue
                params = {
                    "flyFrom": orig, "flyTo": dest,
                    "date_from": str(kiwi_date_from), "date_to": str(kiwi_date_to),
                    "nmin": int(kiwi_nmin), "nmax": int(kiwi_nmax),
                }
                qh = db.compute_query_hash("kiwi_mcp", params)
                if db.is_cache_valid(conn, qh, cache_ttl):
                    cached_count += 1
        conn.close()
        report = safety.calculate_search_cost(
            total_queries=total_q, cached_queries=cached_count,
            provider="kiwi_mcp", user_max_calls=user_max_calls,
        )
        st.info(f"📊 Par: {total_q} | Cache: {cached_count} | HTTP: {report.http_queries_needed}")
        if report.blocked:
            st.error(f"🚫 {report.block_reason}")

    if kiwi_exec:
        if st.session_state.search_running:
            st.error("Inne wyszukiwanie w toku.")
        elif not kiwi_origins or not kiwi_dests:
            st.error("Wybierz lotniska.")
        else:
            st.session_state.search_running = True
            try:
                all_results = []
                conn = db.get_connection()
                search_id = str(uuid.uuid4())[:8]
                safety.reset_call_counter(search_id)

                if st.session_state.mock_mode:
                    progress = st.progress(0)
                    total_pairs = kiwi_mcp.count_kiwi_queries(kiwi_origins, kiwi_dests)
                    done = 0
                    for orig in kiwi_origins:
                        for dest in kiwi_dests:
                            if orig == dest:
                                continue
                            results = generate_mock_kiwi_flights(
                                orig, dest, str(kiwi_date_from), str(kiwi_date_to),
                                int(kiwi_nmin), int(kiwi_nmax),
                            )
                            all_results.extend(results)
                            done += 1
                            progress.progress(min(done / max(total_pairs, 1), 1.0))
                    progress.empty()
                else:
                    # LIVE Kiwi MCP
                    client = kiwi_mcp.KiwiMCPClient()
                    total_pairs = kiwi_mcp.count_kiwi_queries(kiwi_origins, kiwi_dests)
                    progress = st.progress(0)
                    done = 0
                    http_sent = 0

                    for orig in kiwi_origins:
                        for dest in kiwi_dests:
                            if orig == dest:
                                done += 1
                                continue

                            params = {
                                "flyFrom": orig, "flyTo": dest,
                                "date_from": str(kiwi_date_from),
                                "date_to": str(kiwi_date_to),
                                "nmin": int(kiwi_nmin), "nmax": int(kiwi_nmax),
                            }
                            qh = db.compute_query_hash("kiwi_mcp", params)

                            # Check cache
                            if db.is_cache_valid(conn, qh, cache_ttl):
                                cached_flights = db.get_cached_flights(conn, qh)
                                # Reconstruct from cache
                                for f in cached_flights:
                                    all_results.append(f)
                                done += 1
                                progress.progress(min(done / max(total_pairs, 1), 1.0))
                                continue

                            # Hard cap check
                            if http_sent >= min(user_max_calls, safety.HARD_MAX_CALLS_PER_SEARCH):
                                st.warning(f"Limit {min(user_max_calls, safety.HARD_MAX_CALLS_PER_SEARCH)} zapytań osiągnięty. Reszta par pominięta.")
                                break

                            try:
                                # Calculate center date for flex range
                                raw = client.search_flight(
                                    fly_from=orig,
                                    fly_to=dest,
                                    departure_date=str(kiwi_date_from),
                                    departure_date_to=str(kiwi_date_to),
                                    nights_in_dst_from=int(kiwi_nmin),
                                    nights_in_dst_to=int(kiwi_nmax),
                                    currency="EUR",
                                    max_sector_stopovers=0 if kiwi_direct else None,
                                )
                                http_sent += 1

                                parsed = kiwi_mcp.parse_kiwi_response(raw, orig, dest)
                                if parsed:
                                    # Store in cache as flights (with full dict in raw_json)
                                    flight_dicts = []
                                    for p in parsed:
                                        flight_dicts.append({
                                            "provider": "kiwi_mcp",
                                            "direction": "roundtrip",
                                            "orig_airport": p["orig_airport"],
                                            "dest_airport": p["dest_airport"],
                                            "orig_metro_group": p["orig_metro_group"],
                                            "dest_metro_group": p["dest_metro_group"],
                                            "flight_date": p.get("outbound_date", ""),
                                            "departure_time": p.get("outbound_dep_time"),
                                            "arrival_time": p.get("outbound_arr_time"),
                                            "airline": p.get("outbound_airline", ""),
                                            "flight_no": p.get("outbound_flight_no", ""),
                                            "price_eur": p["price_eur"],
                                            "currency": "EUR",
                                            "stops": p.get("stops", 0),
                                            "duration_min": None,
                                            "is_mock": False,
                                            "raw_json": json.dumps(p),
                                        })
                                    db.store_flights(conn, "kiwi_mcp", params,
                                                     flight_dicts, is_mock=False)
                                    all_results.extend(parsed)

                                time.sleep(1.5)  # Rate limiting

                            except Exception as e:
                                st.warning(f"⚠️ {orig}→{dest}: {e}")

                            done += 1
                            progress.progress(min(done / max(total_pairs, 1), 1.0))
                        else:
                            continue
                        break  # break outer loop if inner broke due to limit

                    progress.empty()

                conn.close()
                all_results.sort(key=lambda x: x.get("price_eur", 9999))
                st.session_state.kiwi_results = all_results
            finally:
                st.session_state.search_running = False

    # Display Kiwi results
    if st.session_state.kiwi_results:
        df = _format_kiwi_results(st.session_state.kiwi_results)
        if not df.empty:
            st.markdown(f"**{len(df)} ofert**")
            df = _apply_local_filters(df, "kb")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Brak wyników.")


# =========================================================================
# TAB C: Exact + SQL Matcher
# =========================================================================
with tab_exact:
    st.caption("SerpApi google_flights + lokalny SQL Matcher — zakresy dat OD–DO, min/maks nocy")

    ec1, ec2, ec3, ec4 = st.columns([2, 2, 2.5, 1.5])

    with ec1:
        st.markdown("**Skąd**")
        exact_origins = _compact_airport_selector(
            "Grupa wylotu", ORIGIN_GROUPS, "ec_orig",
        )
        allow_diff_return = st.checkbox(
            "Powrót na inne lotnisko z grupy (np. KRK↔KTW)",
            key="ec_flex",
        )

    with ec2:
        st.markdown("**Dokąd**")
        exact_dest_source = st.radio(
            "Źródło", ["Region", "Metro"], key="ec_dsrc", horizontal=True,
        )
        if exact_dest_source == "Region":
            exact_dest_sel = st.multiselect(
                "Region", list(DESTINATION_REGIONS.keys()), key="ec_dreg",
            )
            exact_dests_raw: list[str] = []
            for r in exact_dest_sel:
                exact_dests_raw.extend(DESTINATION_REGIONS[r])
        else:
            exact_dest_sel = st.multiselect(
                "Metro", list(METRO_GROUPS.keys()), key="ec_dmet",
            )
            exact_dests_raw = []
            for m in exact_dest_sel:
                exact_dests_raw.extend(METRO_GROUPS[m])

        exact_manual = st.text_input("Ręcznie (IATA)", key="ec_dman")
        if exact_manual:
            exact_dests_raw.extend(c.strip().upper() for c in exact_manual.split(",") if c.strip())
        exact_dests = list(dict.fromkeys(exact_dests_raw))

        if exact_dests:
            n_chunks = len(serpapi_client.chunk_airports(exact_dests, 6))
            st.caption(f"{len(exact_dests)} lotnisk → {n_chunks} paczek po ≤6")

    with ec3:
        st.markdown("**Kiedy & pobyt**")
        ecd1, ecd2 = st.columns(2)
        with ecd1:
            exact_date_from = st.date_input(
                "Wylot OD", value=datetime.now().date() + timedelta(days=30), key="ec_df",
            )
        with ecd2:
            exact_date_to = st.date_input(
                "Wylot DO", value=datetime.now().date() + timedelta(days=37), key="ec_dt",
            )

        ecn1, ecn2 = st.columns(2)
        with ecn1:
            exact_nmin = st.number_input("Min nocy", value=3, min_value=1, key="ec_nmin")
        with ecn2:
            exact_nmax = st.number_input("Max nocy", value=10, min_value=1, key="ec_nmax")

        # Weekday filters
        st.markdown("**Dni tygodnia wylotu:**")
        out_weekdays = st.multiselect(
            "Wylot", WEEKDAYS_PL, default=WEEKDAYS_PL, key="ec_owd",
            label_visibility="collapsed",
        )
        st.markdown("**Dni tygodnia powrotu:**")
        ret_weekdays = st.multiselect(
            "Powrót", WEEKDAYS_PL, default=WEEKDAYS_PL, key="ec_rwd",
            label_visibility="collapsed",
        )

    with ec4:
        st.markdown("**Tryb & Koszt**")
        search_mode = st.radio(
            "Tryb", ["One-Way + Matcher", "Round-Trip"], key="ec_mode",
        )
        exact_direct = st.checkbox("Bezpośrednie", key="ec_dir")

        exact_dryrun = st.button("1. Dry-Run", key="ec_dr", use_container_width=True)
        exact_exec = st.button("2. Pobierz", key="ec_ex", use_container_width=True,
                                disabled=st.session_state.search_running)

    # Generate outbound dates
    if exact_origins and exact_dests:
        out_dates = _generate_dates_in_range(
            datetime.combine(exact_date_from, datetime.min.time()),
            datetime.combine(exact_date_to, datetime.min.time()),
            out_weekdays,
        )
    else:
        out_dates = []

    # Generate return dates from outbound + nights range, filtered by weekday
    def _compute_return_dates(out_dates: list[str], nmin: int, nmax: int, ret_wd: list[str]) -> list[str]:
        ret_set: set[str] = set()
        for od in out_dates:
            d = datetime.strptime(od, "%Y-%m-%d")
            for n in range(nmin, nmax + 1):
                rd = d + timedelta(days=n)
                if WEEKDAY_MAP[rd.weekday()] in ret_wd:
                    ret_set.add(rd.strftime("%Y-%m-%d"))
        return sorted(ret_set)

    ret_dates = _compute_return_dates(out_dates, int(exact_nmin), int(exact_nmax), ret_weekdays) if out_dates else []

    is_oneway = "One-Way" in search_mode

    # Dry-run calculation
    if exact_dryrun:
        if not exact_origins or not exact_dests:
            st.error("Wybierz lotniska.")
        elif not out_dates:
            st.error("Brak dat wylotu w wybranym zakresie i dniach tygodnia.")
        else:
            origin_chunks = serpapi_client.chunk_airports(exact_origins, 6)
            dest_chunks = serpapi_client.chunk_airports(exact_dests, 6)
            n_airport_combos = len(origin_chunks) * len(dest_chunks)

            if is_oneway:
                # Unique outbound dates + unique return dates
                total_q = n_airport_combos * len(out_dates) + n_airport_combos * len(ret_dates)
            else:
                # Each (outbound_date, return_date) pair
                n_date_pairs = 0
                for od in out_dates:
                    d = datetime.strptime(od, "%Y-%m-%d")
                    for n in range(int(exact_nmin), int(exact_nmax) + 1):
                        rd = d + timedelta(days=n)
                        if WEEKDAY_MAP[rd.weekday()] in ret_weekdays:
                            n_date_pairs += 1
                total_q = n_airport_combos * n_date_pairs

            # Check cache
            conn = db.get_connection()
            cached_count = 0

            if is_oneway:
                for o_chunk in origin_chunks:
                    for d_chunk in dest_chunks:
                        dep_id = ",".join(o_chunk)
                        arr_id = ",".join(d_chunk)
                        for od in out_dates:
                            p = {"departure_id": dep_id, "arrival_id": arr_id,
                                 "outbound_date": od, "type": 2}
                            if db.is_cache_valid(conn, db.compute_query_hash("serpapi_gf", p), cache_ttl):
                                cached_count += 1
                        for rd in ret_dates:
                            p = {"departure_id": arr_id, "arrival_id": dep_id,
                                 "outbound_date": rd, "type": 2}
                            if db.is_cache_valid(conn, db.compute_query_hash("serpapi_gf", p), cache_ttl):
                                cached_count += 1
            else:
                for o_chunk in origin_chunks:
                    for d_chunk in dest_chunks:
                        dep_id = ",".join(o_chunk)
                        arr_id = ",".join(d_chunk)
                        for od in out_dates:
                            d = datetime.strptime(od, "%Y-%m-%d")
                            for n in range(int(exact_nmin), int(exact_nmax) + 1):
                                rd_dt = d + timedelta(days=n)
                                if WEEKDAY_MAP[rd_dt.weekday()] in ret_weekdays:
                                    rd = rd_dt.strftime("%Y-%m-%d")
                                    p = {"departure_id": dep_id, "arrival_id": arr_id,
                                         "outbound_date": od, "return_date": rd, "type": 1}
                                    if db.is_cache_valid(conn, db.compute_query_hash("serpapi_gf", p), cache_ttl):
                                        cached_count += 1
            conn.close()

            http_needed = total_q - cached_count

            st.info(
                f"📊 Paczki lotnisk: {len(origin_chunks)}×{len(dest_chunks)} | "
                f"Daty wylotu: {len(out_dates)} | "
                f"{'Daty powrotu: ' + str(len(ret_dates)) if is_oneway else 'Par dat: ' + str(total_q // max(n_airport_combos,1))}\n\n"
                f"**Łącznie: {total_q} zapytań | Cache: {cached_count} | "
                f"HTTP: {http_needed}**"
            )

            effective_max = min(user_max_calls, safety.HARD_MAX_CALLS_PER_SEARCH)
            if http_needed > effective_max:
                st.error(
                    f"🚫 Wybrany zakres wymaga **{http_needed}** nowych zapytań HTTP "
                    f"(limit bezpieczeństwa: {effective_max}). "
                    f"Zawęź daty OD–DO, wybierz konkretne dni tygodnia (np. tylko Pt/Nd) "
                    f"lub pobierz dane w partiach — pobrane dni zapiszą się w cache SQLite "
                    f"i w kolejnym kroku będą kosztować 0 zapytań!"
                )
            else:
                for d in safety.calculate_search_cost(
                    total_q, cached_count, "serpapi_gf",
                    effective_api_key, user_max_calls,
                ).details:
                    st.caption(d)

    # Execute
    if exact_exec:
        if st.session_state.search_running:
            st.error("Inne wyszukiwanie w toku.")
        elif not exact_origins or not exact_dests:
            st.error("Wybierz lotniska.")
        elif not out_dates:
            st.error("Brak dat wylotu.")
        else:
            st.session_state.search_running = True
            try:
                conn = db.get_connection()
                search_id = str(uuid.uuid4())[:8]
                safety.reset_call_counter(search_id)
                all_query_hashes_out: list[str] = []
                all_query_hashes_in: list[str] = []

                origin_chunks = serpapi_client.chunk_airports(exact_origins, 6)
                dest_chunks = serpapi_client.chunk_airports(exact_dests, 6)

                if st.session_state.mock_mode:
                    # MOCK
                    if is_oneway:
                        for od in out_dates:
                            out_flights = generate_mock_flights(
                                exact_origins, exact_dests, od, direction="outbound",
                            )
                            p_out = {"origins": exact_origins, "dests": exact_dests,
                                     "date": od, "direction": "outbound"}
                            qh = db.compute_query_hash("mock", p_out)
                            all_query_hashes_out.append(qh)
                            if out_flights:
                                db.store_flights(conn, "mock", p_out, out_flights, is_mock=True)

                        for rd in ret_dates:
                            in_flights = generate_mock_flights(
                                exact_dests, exact_origins, rd, direction="inbound",
                            )
                            p_in = {"origins": exact_dests, "dests": exact_origins,
                                    "date": rd, "direction": "inbound"}
                            qh = db.compute_query_hash("mock", p_in)
                            all_query_hashes_in.append(qh)
                            if in_flights:
                                db.store_flights(conn, "mock", p_in, in_flights, is_mock=True)

                        matched = match_roundtrips(
                            conn,
                            origin_airports=exact_origins,
                            min_nights=int(exact_nmin),
                            max_nights=int(exact_nmax),
                            allow_different_return_airport=allow_diff_return,
                            direct_only=exact_direct,
                            query_hashes_outbound=all_query_hashes_out,
                            query_hashes_inbound=all_query_hashes_in,
                        )
                        st.session_state.exact_results = ("matched", matched)
                        st.success(f"✅ Matcher: {len(matched)} kombinacji")
                    else:
                        # RT mock
                        all_rt = []
                        for orig in exact_origins:
                            for dest in exact_dests:
                                if orig == dest:
                                    continue
                                for od in out_dates:
                                    res = generate_mock_kiwi_flights(
                                        orig, dest, od, od,
                                        int(exact_nmin), int(exact_nmax),
                                    )
                                    all_rt.extend(res)
                        all_rt.sort(key=lambda x: x.get("price_eur", 9999))
                        st.session_state.exact_results = ("kiwi", all_rt)
                        st.success(f"✅ {len(all_rt)} ofert RT")
                else:
                    # LIVE SerpApi
                    http_sent = 0
                    effective_max = min(user_max_calls, safety.HARD_MAX_CALLS_PER_SEARCH)

                    if is_oneway:
                        # Outbound queries
                        for o_chunk in origin_chunks:
                            for d_chunk in dest_chunks:
                                dep_id = ",".join(o_chunk)
                                arr_id = ",".join(d_chunk)
                                for od in out_dates:
                                    p = {"departure_id": dep_id, "arrival_id": arr_id,
                                         "outbound_date": od, "type": 2}
                                    qh = db.compute_query_hash("serpapi_gf", p)
                                    all_query_hashes_out.append(qh)

                                    if db.is_cache_valid(conn, qh, cache_ttl):
                                        continue
                                    if http_sent >= effective_max:
                                        continue

                                    try:
                                        api_params = serpapi_client.build_google_flights_params(
                                            departure_id=dep_id, arrival_id=arr_id,
                                            outbound_date=od, trip_type=2,
                                            api_key=effective_api_key,
                                            stops=1 if exact_direct else None,
                                        )
                                        resp_data = safety.safe_http_get(
                                            serpapi_client.SERPAPI_BASE_URL,
                                            api_params, search_id,
                                            user_max_calls=user_max_calls, timeout=20,
                                        )
                                        flights = serpapi_client.parse_google_flights_response(
                                            resp_data, direction="outbound", query_date=od,
                                        )
                                        if flights:
                                            db.store_flights(conn, "serpapi_gf", p, flights, is_mock=False)
                                        http_sent += 1
                                    except safety.APIError as e:
                                        st.warning(f"⚠️ Out {dep_id}→{arr_id} {od}: {e}")
                                        break

                        # Inbound queries
                        for o_chunk in origin_chunks:
                            for d_chunk in dest_chunks:
                                dep_id = ",".join(o_chunk)
                                arr_id = ",".join(d_chunk)
                                for rd in ret_dates:
                                    p = {"departure_id": arr_id, "arrival_id": dep_id,
                                         "outbound_date": rd, "type": 2}
                                    qh = db.compute_query_hash("serpapi_gf", p)
                                    all_query_hashes_in.append(qh)

                                    if db.is_cache_valid(conn, qh, cache_ttl):
                                        continue
                                    if http_sent >= effective_max:
                                        continue

                                    try:
                                        api_params = serpapi_client.build_google_flights_params(
                                            departure_id=arr_id, arrival_id=dep_id,
                                            outbound_date=rd, trip_type=2,
                                            api_key=effective_api_key,
                                            stops=1 if exact_direct else None,
                                        )
                                        resp_data = safety.safe_http_get(
                                            serpapi_client.SERPAPI_BASE_URL,
                                            api_params, search_id,
                                            user_max_calls=user_max_calls, timeout=20,
                                        )
                                        flights = serpapi_client.parse_google_flights_response(
                                            resp_data, direction="inbound", query_date=rd,
                                        )
                                        if flights:
                                            db.store_flights(conn, "serpapi_gf", p, flights, is_mock=False)
                                        http_sent += 1
                                    except safety.APIError as e:
                                        st.warning(f"⚠️ In {arr_id}→{dep_id} {rd}: {e}")
                                        break

                        # Run matcher
                        matched = match_roundtrips(
                            conn,
                            origin_airports=exact_origins,
                            min_nights=int(exact_nmin),
                            max_nights=int(exact_nmax),
                            allow_different_return_airport=allow_diff_return,
                            direct_only=exact_direct,
                            query_hashes_outbound=all_query_hashes_out,
                            query_hashes_inbound=all_query_hashes_in,
                        )
                        st.session_state.exact_results = ("matched", matched)
                        st.success(f"✅ {http_sent} zapytań HTTP | Matcher: {len(matched)} kombinacji")

                    else:
                        # Round-Trip LIVE
                        all_rt_results: list[dict] = []
                        for o_chunk in origin_chunks:
                            for d_chunk in dest_chunks:
                                dep_id = ",".join(o_chunk)
                                arr_id = ",".join(d_chunk)
                                for od in out_dates:
                                    d = datetime.strptime(od, "%Y-%m-%d")
                                    for n in range(int(exact_nmin), int(exact_nmax) + 1):
                                        rd_dt = d + timedelta(days=n)
                                        if WEEKDAY_MAP[rd_dt.weekday()] not in ret_weekdays:
                                            continue
                                        rd = rd_dt.strftime("%Y-%m-%d")
                                        p = {"departure_id": dep_id, "arrival_id": arr_id,
                                             "outbound_date": od, "return_date": rd, "type": 1}
                                        qh = db.compute_query_hash("serpapi_gf", p)

                                        if db.is_cache_valid(conn, qh, cache_ttl):
                                            cached_f = db.get_cached_flights(conn, qh)
                                            all_rt_results.extend(cached_f)
                                            continue
                                        if http_sent >= effective_max:
                                            continue

                                        try:
                                            api_params = serpapi_client.build_google_flights_params(
                                                departure_id=dep_id, arrival_id=arr_id,
                                                outbound_date=od, return_date=rd, trip_type=1,
                                                api_key=effective_api_key,
                                                stops=1 if exact_direct else None,
                                            )
                                            resp_data = safety.safe_http_get(
                                                serpapi_client.SERPAPI_BASE_URL,
                                                api_params, search_id,
                                                user_max_calls=user_max_calls, timeout=20,
                                            )
                                            flights = serpapi_client.parse_google_flights_response(
                                                resp_data, direction="roundtrip", query_date=od,
                                            )
                                            if flights:
                                                db.store_flights(conn, "serpapi_gf", p, flights, is_mock=False)
                                                all_rt_results.extend(flights)
                                            http_sent += 1
                                        except safety.APIError as e:
                                            st.warning(f"⚠️ RT {dep_id}→{arr_id} {od}/{rd}: {e}")
                                            break

                        all_rt_results.sort(key=lambda x: x.get("price_eur", 9999))
                        st.session_state.exact_results = ("rt_live", all_rt_results)
                        st.success(f"✅ {http_sent} zapytań HTTP | {len(all_rt_results)} wyników")

                conn.close()
            finally:
                st.session_state.search_running = False

    # Display Exact results
    if st.session_state.exact_results:
        rtype, rdata = st.session_state.exact_results
        if rtype == "matched":
            df = _format_matched_results(rdata)
            if not df.empty:
                st.markdown(f"**{len(df)} kombinacji (SQL Matcher)**")
                df = _apply_local_filters(df, "ec")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Brak pasujących kombinacji.")
        elif rtype == "kiwi":
            df = _format_kiwi_results(rdata)
            if not df.empty:
                st.markdown(f"**{len(df)} ofert RT**")
                df = _apply_local_filters(df, "ec_rt")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Brak wyników.")
        elif rtype == "rt_live":
            # Live RT results are raw flight dicts
            if rdata:
                records = []
                for f in rdata:
                    records.append({
                        "Total EUR": f"{f.get('price_eur', 0):.0f} €",
                        "Outbound": f"{f.get('orig_airport', '')}→{f.get('dest_airport', '')}",
                        "Out Date": f"{f.get('flight_date', '')} {f.get('departure_time', '')}",
                        "Out Airline": f"{f.get('airline', '')} {f.get('flight_no', '')}",
                        "Return": f"{f.get('return_orig', '')}→{f.get('return_dest', '')}",
                        "Ret Date": f"{f.get('return_date', '')} {f.get('return_dep_time', '')}",
                        "Ret Airline": f"{f.get('return_airline', '')}",
                        "Stops": f.get("stops", 0),
                        "Source": "SerpApi",
                    })
                df = pd.DataFrame(records)
                st.markdown(f"**{len(df)} wyników RT**")
                df = _apply_local_filters(df, "ec_rtl")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Brak wyników.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    f"AZair Extended v0.2 | {CURRENCY} | "
    f"Mock: {'✅' if st.session_state.mock_mode else '❌'} | "
    f"Cache: {cache_ttl}h | Limit: {safety.HARD_MAX_CALLS_PER_SEARCH}"
)

# ---------------------------------------------------------------------------
# Full SQLite Cache Viewer + Interactive SQL Console
# ---------------------------------------------------------------------------
with st.expander("📦 Baza Cache SQLite — Konsola SQL i Szybkie Filtry", expanded=False):
    st.caption(
        "Steruj tabelą za pomocą przycisków lub wpisz własne zapytanie SQL "
        "(dostępne tabele: `flights`, `query_cache`)."
    )

    preset_queries = {
        "🔥 Wszystkie loty LIVE (od najtańszych)": (
            "SELECT id, provider, direction, orig_airport, dest_airport, flight_date, "
            "departure_time, arrival_time, airline, flight_no, price_eur, stops, raw_json "
            "FROM flights WHERE is_mock = 0 ORDER BY price_eur ASC"
        ),
        "✈️ Bezpośrednie LIVE <= 100 EUR": (
            "SELECT provider, direction, orig_airport, dest_airport, flight_date, "
            "departure_time, airline, flight_no, price_eur, stops, raw_json "
            "FROM flights WHERE is_mock = 0 AND stops = 0 AND price_eur <= 100 "
            "ORDER BY price_eur ASC"
        ),
        "🔗 Składaki One-Way (SQL JOIN Matcher z całej bazy)": (
            "SELECT ROUND(o.price_eur + r.price_eur, 0) AS total_eur, "
            "o.orig_airport || '→' || o.dest_airport AS outbound, "
            "o.flight_date AS out_date, o.departure_time AS out_time, o.airline AS out_airline, "
            "r.orig_airport || '→' || r.dest_airport AS inbound, "
            "r.flight_date AS ret_date, r.departure_time AS ret_time, r.airline AS ret_airline, "
            "CAST(julianday(r.flight_date) - julianday(o.flight_date) AS INTEGER) AS nights, "
            "o.price_eur AS out_eur, r.price_eur AS ret_eur "
            "FROM flights o JOIN flights r ON o.dest_metro_group = r.orig_metro_group "
            "AND o.orig_metro_group = r.dest_metro_group "
            "WHERE o.direction = 'outbound' AND r.direction = 'inbound' "
            "AND o.is_mock = r.is_mock "
            "AND julianday(r.flight_date) - julianday(o.flight_date) BETWEEN 2 AND 14 "
            "ORDER BY total_eur ASC LIMIT 300"
        ),
        "📊 Statystyki cen wg trasy (MIN / AVG / MAX)": (
            "SELECT orig_airport, dest_airport, direction, provider, COUNT(*) AS ofert, "
            "ROUND(MIN(price_eur), 0) AS min_eur, ROUND(AVG(price_eur), 0) AS avg_eur, "
            "ROUND(MAX(price_eur), 0) AS max_eur "
            "FROM flights WHERE is_mock = 0 "
            "GROUP BY orig_airport, dest_airport, direction, provider ORDER BY min_eur ASC"
        ),
        "🗂️ Historia zapytań (tabela query_cache)": (
            "SELECT query_hash, provider, result_count, fetched_at, is_mock, params_json "
            "FROM query_cache ORDER BY fetched_at DESC"
        ),
        "🧪 Wszystkie rekordy (łącznie z MOCK)": (
            "SELECT id, provider, direction, orig_airport, dest_airport, flight_date, "
            "departure_time, airline, flight_no, price_eur, stops, is_mock, raw_json "
            "FROM flights ORDER BY price_eur ASC LIMIT 500"
        ),
    }

    if "custom_sql_query" not in st.session_state:
        st.session_state.custom_sql_query = list(preset_queries.values())[0]

    # Szybkie przyciski (Presety SQL)
    p_cols = st.columns(3)
    for idx, (label, q_str) in enumerate(preset_queries.items()):
        with p_cols[idx % 3]:
            if st.button(label, key=f"sql_preset_btn_{idx}", use_container_width=True):
                st.session_state.custom_sql_query = q_str
                st.session_state.sql_editor_area = q_str

    # Pole tekstowe SQL
    sql_input = st.text_area(
        "Zapytanie SQL (tylko SELECT / WITH / PRAGMA — zatwierdź Ctrl+Enter):",
        value=st.session_state.custom_sql_query,
        height=110,
        key="sql_editor_area",
    )

    clean_sql = sql_input.strip()
    first_word = clean_sql.split()[0].upper() if clean_sql else ""

    if first_word not in ("SELECT", "WITH", "PRAGMA"):
        st.error("Dozwolone są wyłącznie zapytania odczytujące (SELECT, WITH, PRAGMA).")
    else:
        conn_sql = db.get_connection()
        try:
            df_sql = pd.read_sql_query(clean_sql, conn_sql)

            # Automatyczne wyciągnięcie pól powrotu z raw_json, jeśli kolumna jest w SELECT
            if "raw_json" in df_sql.columns:
                def _extract_raw_field(raw_val, key):
                    if raw_val and isinstance(raw_val, str):
                        try:
                            return json.loads(raw_val).get(key, "")
                        except Exception:
                            return ""
                    return ""

                df_sql["return_date"] = df_sql["raw_json"].apply(lambda r: _extract_raw_field(r, "return_date"))
                df_sql["return_airline"] = df_sql["raw_json"].apply(lambda r: _extract_raw_field(r, "return_airline"))
                df_sql["nights"] = df_sql["raw_json"].apply(lambda r: _extract_raw_field(r, "nights"))
                df_sql["booking_url"] = df_sql["raw_json"].apply(lambda r: _extract_raw_field(r, "booking_url"))
                df_sql = df_sql.drop(columns=["raw_json"])

            st.caption(f"Wyświetlono wierszy: **{len(df_sql)}** (kliknij nagłówek dowolnej kolumny, aby posortować)")
            st.dataframe(
                df_sql,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "price_eur": st.column_config.NumberColumn("Cena EUR", format="%.0f €"),
                    "total_eur": st.column_config.NumberColumn("Total EUR", format="%.0f €"),
                    "out_eur": st.column_config.NumberColumn("Tam EUR", format="%.0f €"),
                    "ret_eur": st.column_config.NumberColumn("Powrót EUR", format="%.0f €"),
                    "min_eur": st.column_config.NumberColumn("Min EUR", format="%.0f €"),
                    "avg_eur": st.column_config.NumberColumn("Śr. EUR", format="%.0f €"),
                    "max_eur": st.column_config.NumberColumn("Max EUR", format="%.0f €"),
                    "booking_url": st.column_config.LinkColumn("Rezerwacja", display_text="🔗 Link"),
                },
            )
        except Exception as e:
            st.error(f"Błąd składni SQL: {e}")
        finally:
            conn_sql.close()
