"""
app.py – AZair Extended – Streamlit UI.

Compact AZair-style layout with 3 search tabs.
DEFAULT: MOCK_MODE = True (zero real HTTP requests).
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
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
    page_title="AZair Extended – Flight Search Radar",
    page_icon=None,
    layout="wide",
)

# ---------------------------------------------------------------------------
# Modern SaaS Slate & Blue CSS (AZair Extended)
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, .stApp, [data-testid="stAppViewContainer"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }

    [data-testid="stHeader"] {
        background-color: #ffffff !important;
        border-bottom: 1px solid #e2e8f0 !important;
    }

    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e2e8f0 !important;
    }

    .block-container {
        padding-top: 2.8rem !important;
        padding-bottom: 2rem !important;
        max-width: 1440px !important;
    }

    /* Segmented Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #e2e8f0;
        padding: 4px;
        border-radius: 10px;
        width: fit-content;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 7px 16px;
        font-size: 0.82rem;
        font-weight: 600;
        border-radius: 7px;
        color: #475569 !important;
        background-color: transparent !important;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #0f172a !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }

    /* Karty zakładek i formularzy */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03) !important;
    }

    /* Przyciski */
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.80rem !important;
        border: 1px solid #cbd5e1 !important;
        background-color: #ffffff !important;
        color: #0f172a !important;
        transition: all 0.15s ease !important;
    }
    .stButton > button:hover {
        background-color: #f1f5f9 !important;
        border-color: #94a3b8 !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #2563eb !important;
        color: #ffffff !important;
        border-color: #2563eb !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
    }

    /* Etykiety pól */
    .stSelectbox label, .stMultiselect label, .stDateInput label,
    .stNumberInput label, .stCheckbox label, .stRadio label, .stSlider label {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        color: #334155 !important;
    }

    /* Tabele danych */
    .stDataFrame, [data-testid="stTable"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-variant-numeric: tabular-nums !important;
        font-size: 0.80rem !important;
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
    }

    /* Expander SQL */
    div[data-testid="stExpander"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        color: #0f172a !important;
        background-color: #f8fafc !important;
        padding: 0.75rem 1rem !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Weekday & Month Constants and Index Maps
# ---------------------------------------------------------------------------
WEEKDAYS_PL = ["Pn", "Wt", "Śr", "Cz", "Pt", "Sb", "Nd"]
WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_PL_TO_EN = dict(zip(WEEKDAYS_PL, WEEKDAYS_EN))
WEEKDAY_INDEX_MAP = {
    "Pn": 0, "Wt": 1, "Śr": 2, "Cz": 3, "Pt": 4, "Sb": 5, "Nd": 6,
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6,
}
WEEKDAY_MAP = {0: "Pn", 1: "Wt", 2: "Śr", 3: "Cz", 4: "Pt", 5: "Sb", 6: "Nd"}

MONTHS_PL = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze", "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAMES_PL = MONTHS_PL
MONTH_NAMES_EN = MONTHS_EN

# ---------------------------------------------------------------------------
# Country & Duration Localization Maps
# ---------------------------------------------------------------------------
COUNTRY_EN_MAP = {
    "Włochy": "Italy",
    "Hiszpania": "Spain",
    "Portugalia": "Portugal",
    "Grecja": "Greece",
    "Chorwacja": "Croatia",
    "Albania": "Albania",
    "Czarnogóra": "Montenegro",
    "Cypr": "Cyprus",
    "Malta": "Malta",
    "Bułgaria": "Bulgaria",
    "Turcja": "Turkey",
    "Gruzja": "Georgia",
    "Armenia": "Armenia",
    "Azerbejdżan": "Azerbaijan",
    "Maroko": "Morocco",
    "Tunezja": "Tunisia",
    "Jordania": "Jordan",
    "Izrael": "Israel",
    "Egipt": "Egypt",
    "Zjednoczone Emiraty Arabskie": "United Arab Emirates",
    "Arabia Saudyjska": "Saudi Arabia",
    "Oman": "Oman",
    "Europa Południowa": "Southern Europe",
}

DUR_LABELS_EN = {"3": "Weekend (3 days)", "7": "1 week (7 days)", "14": "2 weeks (14 days)"}
DUR_LABELS_PL = {"3": "Weekend (3 dni)", "7": "1 tydzień (7 dni)", "8": "8 dni", "14": "2 tygodnie (14 dni)"}

# ---------------------------------------------------------------------------
# Localized City Names Map
# ---------------------------------------------------------------------------
CITY_PL_TO_EN = {
    "Kraków": "Krakow",
    "Warszawa Chopin": "Warsaw Chopin",
    "Warszawa Modlin": "Warsaw Modlin",
    "Wrocław": "Wroclaw",
    "Gdańsk": "Gdansk",
    "Poznań": "Poznan",
    "Rzeszów": "Rzeszow",
    "Wiedeń": "Vienna",
    "Budapeszt": "Budapest",
    "Bratysława": "Bratislava",
    "Ostrawa": "Ostrava",
    "Mediolan Bergamo": "Milan Bergamo",
    "Mediolan Malpensa": "Milan Malpensa",
    "Mediolan Linate": "Milan Linate",
    "Wenecja Marco Polo": "Venice Marco Polo",
    "Wenecja Treviso": "Venice Treviso",
    "Bolonia": "Bologna",
    "Turyn": "Turin",
    "Werona": "Verona",
    "Genua": "Genoa",
    "Triest": "Trieste",
    "Rimini": "Rimini",
    "Rzym Fiumicino": "Rome Fiumicino",
    "Rzym Ciampino": "Rome Ciampino",
    "Neapol": "Naples",
    "Bari": "Bari",
    "Brindisi": "Brindisi",
    "Pescara": "Pescara",
    "Piza": "Pisa",
    "Perugia": "Perugia",
    "Lamezia Terme": "Lamezia Terme",
    "Salerno": "Salerno",
    "Katania": "Catania",
    "Comiso": "Comiso",
    "Palermo": "Palermo",
    "Trapani": "Trapani",
    "Cagliari": "Cagliari",
    "Alghero": "Alghero",
    "Olbia": "Olbia",
    "Lampedusa": "Lampedusa",
    "Barcelona El Prat": "Barcelona El Prat",
    "Barcelona Girona": "Barcelona Girona",
    "Barcelona Reus": "Barcelona Reus",
    "Madryt": "Madrid",
    "Malaga": "Malaga",
    "Alicante": "Alicante",
    "Walencja": "Valencia",
    "Sewilla": "Seville",
    "Almeria": "Almeria",
    "Murcia": "Murcia",
    "Castellón": "Castellon",
    "Santander": "Santander",
    "Saragossa": "Zaragoza",
    "Bilbao": "Bilbao",
    "Oviedo/Asturia": "Oviedo/Asturias",
    "Santiago de Compostela": "Santiago de Compostela",
    "Palma de Mallorca": "Palma de Mallorca",
    "Ibiza": "Ibiza",
    "Menorca": "Menorca",
    "Teneryfa Południe": "Tenerife South",
    "Teneryfa Północ": "Tenerife North",
    "Gran Canaria": "Gran Canaria",
    "Lanzarote": "Lanzarote",
    "Fuerteventura": "Fuerteventura",
    "La Palma": "La Palma",
    "Lizbona": "Lisbon",
    "Porto": "Porto",
    "Faro": "Faro",
    "Madera Funchal": "Madeira Funchal",
    "Azory Ponta Delgada": "Azores Ponta Delgada",
    "Nicea": "Nice",
    "Marsylia": "Marseille",
    "Montpellier": "Montpellier",
    "Tuluza": "Toulouse",
    "Béziers": "Beziers",
    "Perpignan": "Perpignan",
    "Biarritz": "Biarritz",
    "Figari (Korsyka)": "Figari (Corsica)",
    "Bastia (Korsyka)": "Bastia (Corsica)",
    "Ateny": "Athens",
    "Saloniki": "Thessaloniki",
    "Preveza/Lefkada": "Preveza/Lefkada",
    "Wolos": "Volos",
    "Kalamata": "Kalamata",
    "Patras/Araxos": "Patras/Araxos",
    "Chania (Kreta)": "Chania (Crete)",
    "Heraklion (Kreta)": "Heraklion (Crete)",
    "Rodos": "Rhodes",
    "Korfu": "Corfu",
    "Zakynthos": "Zakynthos",
    "Kos": "Kos",
    "Santorini": "Santorini",
    "Mykonos": "Mykonos",
    "Kefalonia": "Kefalonia",
    "Skiathos": "Skiathos",
    "Lesbos": "Lesbos",
    "Samos": "Samos",
    "Pafos": "Paphos",
    "Larnaka": "Larnaca",
    "Malta": "Malta",
    "Zadar": "Zadar",
    "Split": "Split",
    "Dubrownik": "Dubrovnik",
    "Pula": "Pula",
    "Rijeka": "Rijeka",
    "Zagrzeb": "Zagreb",
    "Podgorica": "Podgorica",
    "Tivat": "Tivat",
    "Lublana": "Ljubljana",
    "Tirana": "Tirana",
    "Skopje": "Skopje",
    "Ohrid": "Ohrid",
    "Sarajewo": "Sarajevo",
    "Banja Luka": "Banja Luka",
    "Tuzla": "Tuzla",
    "Prisztina": "Pristina",
    "Sofia": "Sofia",
    "Burgas": "Burgas",
    "Warna": "Varna",
    "Płowdiw": "Plovdiv",
    "Bukareszt": "Bucharest",
    "Konstanca": "Constanta",
    "Stambuł Sabiha": "Istanbul Sabiha",
    "Stambuł": "Istanbul",
    "Antalya": "Antalya",
    "Dalaman": "Dalaman",
    "Bodrum": "Bodrum",
    "Izmir": "Izmir",
    "Ankara": "Ankara",
    "Gaziantep": "Gaziantep",
    "Trabzon": "Trabzon",
    "Kutaisi": "Kutaisi",
    "Tbilisi": "Tbilisi",
    "Batumi": "Batumi",
    "Erywań": "Yerevan",
    "Baku": "Baku",
    "Amman": "Amman",
    "Akaba": "Aqaba",
    "Tel Awiw": "Tel Aviv",
    "Bejrut": "Beirut",
    "Abu Zabi": "Abu Dhabi",
    "Dubaj": "Dubai",
    "Dubaj Al Maktoum": "Dubai Al Maktoum",
    "Szardża": "Sharjah",
    "Doha": "Doha",
    "Kuwejt": "Kuwait",
    "Bahrajn": "Bahrain",
    "Maskat": "Muscat",
    "Rijad": "Riyadh",
    "Dżudda": "Jeddah",
    "Dammam": "Dammam",
    "Salalah": "Salalah",
    "Hurghada": "Hurghada",
    "Sharm el-Sheikh": "Sharm el-Sheikh",
    "Sfinks (Kair)": "Sphinx (Cairo)",
    "Kair": "Cairo",
    "Marsa Alam": "Marsa Alam",
    "Marrakesz": "Marrakesh",
    "Agadir": "Agadir",
    "Fez": "Fez",
    "Tanger": "Tangier",
    "Rabat": "Rabat",
    "Nador": "Nador",
    "Oudja": "Oujda",
    "Essaouira": "Essaouira",
    "Casablanca": "Casablanca",
    "Tetouan": "Tetouan",
    "Tunis": "Tunis",
    "Monastir": "Monastir",
    "Dżerba": "Djerba",
    "Enfidha": "Enfidha",
    "Algier": "Algiers",
    "Oran": "Oran",
    "Łódź": "Lodz",
    "Szczecin": "Szczecin",
    "Bydgoszcz": "Bydgoszcz",
    "Lublin": "Lublin",
    "Olsztyn-Mazury": "Olsztyn-Mazury",
    "Zielona Góra": "Zielona Gora",
    "Warszawa Radom": "Warsaw Radom",
    "Praga": "Prague",
    "Berlin": "Berlin",
    "Koszyce": "Kosice",
    "Wilno": "Vilnius",
    "Kowno": "Kaunas",
    "Ankona": "Ancona",
    "Paryż Beauvais": "Paris Beauvais",
    "Paryż CDG": "Paris CDG",
    "Paryż Orly": "Paris Orly",
    "Bruksela Charleroi": "Brussels Charleroi",
    "Bazylea": "Basel",
    "Genewa": "Geneva",
    "Zurych": "Zurich",
    "Londyn Stansted": "London Stansted",
    "Londyn Luton": "London Luton",
    "Londyn Gatwick": "London Gatwick",
    "Edynburg": "Edinburgh",
    "Kopenhaga": "Copenhagen",
    "Sztokholm Skavsta": "Stockholm Skavsta",
    "Sztokholm Arlanda": "Stockholm Arlanda",
    "Ryga": "Riga",
    "Kluż-Napoka": "Cluj-Napoca",
    "Jassy": "Iasi",
    "Krajowa": "Craiova",
}


def get_localized_city_name(code_or_name: str) -> str:
    raw = get_city_name(code_or_name)
    if st.session_state.get("lang", "EN") == "EN":
        return CITY_PL_TO_EN.get(raw, raw)
    return raw


# ---------------------------------------------------------------------------
# UI Translations (EN default, PL alternative)
# ---------------------------------------------------------------------------
UI_TEXT = {
    "EN": {
        "page_title": "AZair Extended – Flight Search Radar",
        "header_subtitle": "Flexible low-cost flight radar & SQLite cache",
        "mode_mock": "Mode: Mock Data (MOCK)",
        "mode_live": "Mode: LIVE API",
        "lock_mock": "MOCK MODE",
        "settings": "Settings",
        "max_http": "Max HTTP requests / search",
        "max_http_calls": "Max HTTP requests / search",
        "cache_ttl": "Cache TTL (hours)",
        "clear_cache": "Clear SQLite Cache",
        "cache_cleared": "Cache cleared.",
        "serpapi_key": "SerpApi Key",
        "api_key_help": "Or set SERPAPI_API_KEY in .env",
        "searches_left": "Remaining searches",
        "set_api_key": "Set SERPAPI_API_KEY.",
        "currency": "Currency",
        "limit": "Limit",
        "tab_a": "Tab A: Explore Radar",
        "tab_b": "1. Kiwi MCP Flexible",
        "tab_c": "2. Exact + SQL Matcher",
        "tab_a_sub": "SerpApi google_travel_explore – cheap destinations from selected airport / country",
        "tab_b_sub": "Kiwi MCP Streamable HTTP – flexible date & stay ranges with return date bounds",
        "tab_c_sub": "SerpApi google_flights + local SQL Matcher – date ranges FROM–TO, min/max nights",
        "from": "From",
        "to": "To",
        "origin_group": "Origin group",
        "airports": "Airports",
        "airports_label": "Airports",
        "manual_iata": "Manual (IATA)",
        "target_country": "Target country",
        "dest_country": "Target country",
        "dep_month": "Departure month",
        "duration": "Duration",
        "direct_only": "Direct only",
        "source": "Source",
        "region": "Region",
        "metro": "Metro",
        "target_region": "Target region",
        "metro_group": "Metro group",
        "when_stay": "When & stay",
        "dep_from": "Dep FROM",
        "dep_to": "Dep TO",
        "ret_from": "Ret FROM",
        "ret_to": "Ret TO",
        "min_nights": "Min nights",
        "max_nights": "Max nights",
        "dep_weekdays": "Departure weekdays",
        "ret_weekdays": "Return weekdays",
        "mode_cost": "Mode & Cost",
        "btn_dryrun": "1. Dry-Run",
        "btn_search": "2. Search",
        "btn_load_sql": "3. Load from SQLite (0 API)",
        "allow_diff_return": "Allow return to another airport in origin group (e.g. KRK<->KTW)",
        "max_price": "Max price (€)",
        "options_start": "Options & Start",
        "select_airports_err": "Select airports.",
        "search_in_progress": "Another search in progress.",
        "no_out_dates": "No departure dates in selected range and weekdays.",
        "no_results": "No results matching criteria.",
        "schedule_filters": "Schedule filters (date ranges, nights, weekdays)",
        "flt_dep_range": "Filter Dep FROM – TO",
        "flt_ret_range": "Filter Ret FROM – TO",
        "flt_nights": "Filter Nights (Min – Max)",
        "flt_max_price": "Max price (€)",
        "flt_airports": "Destination / Airport filter (e.g. BCN, CTA)",
        "flt_airlines": "Carriers",
        "flt_direct": "Direct flights only (0 stops)",
        "col_filter_title": "Column Value Extractor (e.g. filter only BCN, CTA in any column)",
        "col_filter_select_cols": "Select columns to filter by specific values",
        "sql_expander_title": "SQLite Cache Database — Interactive SQL Console & Quick Filters (click to expand)",
        "sql_caption": "Control the table using presets or enter your own SQL query (available tables: `flights`, `query_cache`).",
        "sql_editor_label": "SQL Query (SELECT / WITH / PRAGMA only — press Ctrl+Enter to run):",
        "sql_rows_displayed": "Rows displayed:",
        "preset_all_live": "All LIVE flights (cheapest first)",
        "preset_direct_100": "Direct LIVE <= 100 EUR",
        "preset_oneway_matcher": "One-Way Combos (SQL JOIN Matcher from whole DB)",
        "preset_price_stats": "Route Price Stats (MIN / AVG / MAX)",
        "preset_query_history": "Query History (query_cache table)",
        "preset_all_records": "All Records (including MOCK)",
        "col_total_eur": "Total (€)",
        "col_out_eur": "Outbound (€)",
        "col_ret_eur": "Return (€)",
        "col_price_eur": "Price (€)",
        "col_nights": "Nights",
        "col_stops": "Stops",
        "mode": "Mode",
        "mode_oneway": "One-Way + Matcher",
        "mode_rt": "Round-Trip",
        "dur_weekend": "Weekend (3)",
        "dur_1week": "1 week (7)",
        "dur_2weeks": "2 weeks (14)",
        "offers": "offers",
        "combos": "combos (SQL Matcher)",
        "results": "results",
        "footer_info": "AZair Extended v0.2",
    },
    "PL": {
        "page_title": "AZair Extended – Radar Tanich Lotów",
        "header_subtitle": "Elastyczny radar tanich lotów i pamięć podręczna SQLite",
        "mode_mock": "Tryb: Dane testowe (MOCK)",
        "mode_live": "Tryb: LIVE API",
        "lock_mock": "MOCK MODE",
        "settings": "Ustawienia",
        "max_http": "Maks. zapytań HTTP / wyszukiwanie",
        "max_http_calls": "Maks. zapytań HTTP / wyszukiwanie",
        "cache_ttl": "Cache TTL (godziny)",
        "clear_cache": "Wyczyść cache SQLite",
        "cache_cleared": "Cache wyczyszczony.",
        "serpapi_key": "Klucz SerpApi",
        "api_key_help": "Lub ustaw SERPAPI_API_KEY w .env",
        "searches_left": "Zapytania pozostałe",
        "set_api_key": "Ustaw SERPAPI_API_KEY.",
        "currency": "Waluta",
        "limit": "Limit",
        "tab_a": "Tab A: Explore Radar",
        "tab_b": "1. Kiwi MCP Elastyczne",
        "tab_c": "2. Exact + SQL Matcher",
        "tab_a_sub": "SerpApi google_travel_explore – tanie kierunki z wybranego lotniska / kraju",
        "tab_b_sub": "Kiwi MCP Streamable HTTP – elastyczne zakresy dat i pobytu z ograniczeniem daty powrotu",
        "tab_c_sub": "SerpApi google_flights + lokalny SQL Matcher – zakresy dat OD–DO, min/maks nocy",
        "from": "Skąd",
        "to": "Dokąd",
        "origin_group": "Grupa wylotu",
        "airports": "Lotniska",
        "airports_label": "Lotniska",
        "manual_iata": "Ręcznie (IATA)",
        "target_country": "Kraj docelowy",
        "dest_country": "Kraj docelowy",
        "dep_month": "Miesiąc wylotu",
        "duration": "Długość",
        "direct_only": "Bezpośrednie",
        "source": "Źródło",
        "region": "Region",
        "metro": "Metro",
        "target_region": "Region docelowy",
        "metro_group": "Grupa metro",
        "when_stay": "Kiedy & pobyt",
        "dep_from": "Wylot OD",
        "dep_to": "Wylot DO",
        "ret_from": "Powrót OD",
        "ret_to": "Powrót DO",
        "min_nights": "Min nocy",
        "max_nights": "Max nocy",
        "dep_weekdays": "Dni tygodnia wylotu",
        "ret_weekdays": "Dni tygodnia powrotu",
        "mode_cost": "Tryb & Koszt",
        "btn_dryrun": "1. Dry-Run",
        "btn_search": "2. Pobierz",
        "btn_load_sql": "3. Wczytaj z SQLite (0 API)",
        "allow_diff_return": "Powrót na inne lotnisko z grupy (np. KRK<->KTW)",
        "max_price": "Max cena (€)",
        "options_start": "Opcje & Start",
        "select_airports_err": "Wybierz lotniska.",
        "search_in_progress": "Inne wyszukiwanie w toku.",
        "no_out_dates": "Brak dat wylotu w wybranym zakresie i dniach tygodnia.",
        "no_results": "Brak wyników spełniających kryteria.",
        "schedule_filters": "Filtry harmonogramu (zakres dat, noce, dni tygodnia)",
        "flt_dep_range": "Zawęź Wylot OD – DO",
        "flt_ret_range": "Zawęź Powrót OD – DO",
        "flt_nights": "Zawęź Noce (Min – Max)",
        "flt_max_price": "Max cena (€)",
        "flt_airports": "Filtruj lotniska (np. BCN, CTA)",
        "flt_airlines": "Przewoźnicy",
        "flt_direct": "Tylko bezpośrednie (0 przesiadek)",
        "col_filter_title": "Wyodrębnij wartości w kolumnach (np. tylko BCN, CTA w dowolnej kolumnie)",
        "col_filter_select_cols": "Wybierz kolumny do filtrowania",
        "sql_expander_title": "Baza Cache SQLite — Interaktywna Konsola SQL i Szybkie Filtry (kliknij, aby rozwinąć)",
        "sql_caption": "Steruj tabelą za pomocą przycisków lub wpisz własne zapytanie SQL (dostępne tabele: `flights`, `query_cache`).",
        "sql_editor_label": "Zapytanie SQL (tylko SELECT / WITH / PRAGMA — zatwierdź Ctrl+Enter):",
        "sql_rows_displayed": "Wyświetlono wierszy:",
        "preset_all_live": "Wszystkie loty LIVE (od najtańszych)",
        "preset_direct_100": "Bezpośrednie LIVE <= 100 EUR",
        "preset_oneway_matcher": "Składaki One-Way (SQL JOIN Matcher z całej bazy)",
        "preset_price_stats": "Statystyki cen wg trasy (MIN / AVG / MAX)",
        "preset_query_history": "Historia zapytań (tabela query_cache)",
        "preset_all_records": "Wszystkie rekordy (łącznie z MOCK)",
        "col_total_eur": "Total (€)",
        "col_out_eur": "Wylot (€)",
        "col_ret_eur": "Powrót (€)",
        "col_price_eur": "Cena (€)",
        "col_nights": "Noce",
        "col_stops": "Przesiadki",
        "mode": "Tryb",
        "mode_oneway": "One-Way + Matcher",
        "mode_rt": "Round-Trip",
        "dur_weekend": "Weekend (3)",
        "dur_1week": "1 tydzień (7)",
        "dur_2weeks": "2 tygodnie (14)",
        "offers": "ofert",
        "combos": "kombinacji (SQL Matcher)",
        "results": "wyników",
        "footer_info": "AZair Extended v0.2",
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("lang", "EN")
    return UI_TEXT.get(lang, UI_TEXT["EN"]).get(key, key)


def current_weekdays() -> list[str]:
    return WEEKDAYS_EN if st.session_state.get("lang", "EN") == "EN" else WEEKDAYS_PL


def current_months() -> list[str]:
    return MONTH_NAMES_EN if st.session_state.get("lang", "EN") == "EN" else MONTH_NAMES_PL


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
        "lang": "EN",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _inject_calendar_locale_sync(lang: str) -> None:
    """Synchronize BaseWeb date_input calendar popups with the selected UI language (EN or PL)."""
    components.html(
        f"""
        <script>
        (function() {{
            const pWin = window.parent;
            const pDoc = pWin.document;
            pWin._azairTargetLang = "{lang}";
            pDoc.documentElement.lang = "{lang}" === "EN" ? "en" : "pl";

            if (!pWin._origDateTimeFormat) {{
                pWin._origDateTimeFormat = pWin.Intl.DateTimeFormat;
            }}
            const OrigDTF = pWin._origDateTimeFormat;
            function PatchedDTF(locales, options) {{
                const loc = pWin._azairTargetLang === "EN" ? "en-US" : "pl-PL";
                return new OrigDTF(loc, options);
            }}
            PatchedDTF.prototype = OrigDTF.prototype;
            PatchedDTF.supportedLocalesOf = OrigDTF.supportedLocalesOf.bind(OrigDTF);
            pWin.Intl.DateTimeFormat = PatchedDTF;

            const plToEnMonths = [
                [/stycznia|styczeń|styczen/gi, "January"],
                [/lutego|luty/gi, "February"],
                [/marca|marzec/gi, "March"],
                [/kwietnia|kwiecień|kwiecien/gi, "April"],
                [/maja|maj/gi, "May"],
                [/czerwca|czerwiec/gi, "June"],
                [/lipca|lipiec/gi, "July"],
                [/sierpnia|sierpień|sierpien/gi, "August"],
                [/września|wrzesień|wrzesien/gi, "September"],
                [/października|październik|pazdziernik/gi, "October"],
                [/listopada|listopad/gi, "November"],
                [/grudnia|grudzień|grudzien/gi, "December"]
            ];
            const enToPlMonths = [
                [/january/gi, "Styczeń"],
                [/february/gi, "Luty"],
                [/march/gi, "Marzec"],
                [/april/gi, "Kwiecień"],
                [/\\bmay\\b/gi, "Maj"],
                [/june/gi, "Czerwiec"],
                [/july/gi, "Lipiec"],
                [/august/gi, "Sierpień"],
                [/september/gi, "Wrzesień"],
                [/october/gi, "Październik"],
                [/november/gi, "Listopad"],
                [/december/gi, "Grudzień"]
            ];
            const plToEnDays = {{
                "Pn": "Mo", "Pon": "Mo", "Wt": "Tu", "Wto": "Tu",
                "Śr": "We", "Śro": "We", "Cz": "Th", "Czw": "Th",
                "Pt": "Fr", "Pią": "Fr", "So": "Sa", "Sob": "Sa", "Sb": "Sa",
                "Nd": "Su", "Niedz": "Su", "Nie": "Su"
            }};
            const enToPlDays = {{
                "Mo": "Pn", "Mon": "Pn", "Tu": "Wt", "Tue": "Wt",
                "We": "Śr", "Wed": "Śr", "Th": "Cz", "Thu": "Cz",
                "Fr": "Pt", "Fri": "Pt", "Sa": "Sb", "Sat": "Sb",
                "Su": "Nd", "Sun": "Nd"
            }};

            function translateCalendarRoot(root) {{
                const curLang = pWin._azairTargetLang || "EN";
                const monthRules = curLang === "EN" ? plToEnMonths : enToPlMonths;
                const dayMap = curLang === "EN" ? plToEnDays : enToPlDays;

                const walker = pDoc.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
                let node;
                while ((node = walker.nextNode())) {{
                    let txt = node.nodeValue;
                    if (!txt || !txt.trim()) continue;
                    let updated = txt;
                    for (const [regex, replacement] of monthRules) {{
                        updated = updated.replace(regex, replacement);
                    }}
                    const trimmed = updated.trim();
                    if (dayMap[trimmed]) {{
                        updated = dayMap[trimmed];
                    }}
                    if (updated !== txt) {{
                        node.nodeValue = updated;
                    }}
                }}
            }}

            function scanPopovers() {{
                const roots = pDoc.querySelectorAll(
                    '[data-baseweb="popover"], [data-baseweb="calendar"], [data-baseweb="calendar-header"], [data-baseweb="menu"], [role="dialog"], [role="listbox"]'
                );
                roots.forEach(translateCalendarRoot);
            }}

            if (pWin._azairCalObserver) {{
                pWin._azairCalObserver.disconnect();
            }}
            pWin._azairCalObserver = new MutationObserver(() => {{
                scanPopovers();
                setTimeout(scanPopovers, 30);
                setTimeout(scanPopovers, 100);
            }});
            pWin._azairCalObserver.observe(pDoc.body, {{
                childList: true,
                subtree: true,
                characterData: true
            }});

            if (pWin._azairCalInterval) {{
                clearInterval(pWin._azairCalInterval);
            }}
            pWin._azairCalInterval = setInterval(scanPopovers, 100);
            scanPopovers();
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


_init_state()

# ---------------------------------------------------------------------------
# Header (compact, with EN/PL language selector)
# ---------------------------------------------------------------------------
hdr_col1, hdr_col2, hdr_col3, hdr_col4 = st.columns([3.5, 2, 2, 1.5])
with hdr_col1:
    st.markdown("## AZair Extended")
with hdr_col2:
    mock_toggle = st.toggle(t("lock_mock"), value=st.session_state.mock_mode, key="mock_toggle_main")
    st.session_state.mock_mode = mock_toggle
    safety.MOCK_MODE = mock_toggle
with hdr_col3:
    if st.session_state.mock_mode:
        st.info(t("mode_mock"))
    else:
        st.success(t("mode_live"))
with hdr_col4:
    lang_choice = st.radio(
        "Language / Język",
        options=["EN", "PL"],
        index=0 if st.session_state.lang == "EN" else 1,
        horizontal=True,
        key="lang_selector_top",
    )
    st.session_state.lang = lang_choice

_inject_calendar_locale_sync(st.session_state.get("lang", "EN"))

# ---------------------------------------------------------------------------
# Sidebar – settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header(t("settings"))

    risky_suffix = " (risky)" if st.session_state.get("lang", "EN") == "EN" else " (ryzykowne)"
    user_max_calls = st.select_slider(
        t("max_http_calls"),
        options=list(range(1, safety.HARD_MAX_CALLS_PER_SEARCH + 1)),
        value=4,
        format_func=lambda v: f"{v}{risky_suffix}" if v >= 5 else str(v),
        help=f"Hard backend limit: {safety.HARD_MAX_CALLS_PER_SEARCH}",
    )
    if user_max_calls >= 5:
        st.caption(
            "Warning: >= 5 requests per search may quickly consume SerpApi quota or hit Kiwi MCP rate limits."
            if st.session_state.get("lang", "EN") == "EN"
            else "Uwaga: >= 5 zapytań na wyszukiwanie może szybko zużyć pakiet SerpApi lub napotkać rate-limit Kiwi MCP."
        )

    cache_ttl = st.slider(
        t("cache_ttl"),
        min_value=1,
        max_value=336,
        value=72,
        help="72h (3 days) recommended to preserve multi-session searches without wasting API quota.",
    )

    if st.button(t("clear_cache"), use_container_width=True):
        conn = db.get_connection()
        db.clear_cache(conn)
        conn.close()
        st.success(t("cache_cleared"))

    st.divider()
    st.subheader(t("serpapi_key"))
    serpapi_key_input = st.text_input(
        "API Key", value=SERPAPI_API_KEY, type="password",
        help=t("api_key_help"),
    )
    effective_api_key = serpapi_key_input or SERPAPI_API_KEY

    if effective_api_key:
        account = safety.check_serpapi_account(effective_api_key)
        left = account.get("plan_searches_left", "?")
        st.metric(t("searches_left"), left)
    else:
        st.info(t("set_api_key"))

    st.divider()
    st.caption(
        f"{t('currency')}: {CURRENCY} | Cache: {cache_ttl}h | "
        f"{t('limit')}: {safety.HARD_MAX_CALLS_PER_SEARCH}/search"
    )


# ---------------------------------------------------------------------------
# Helper: airport multiselect with groups
# ---------------------------------------------------------------------------
def _compact_airport_selector(
    label_group: str,
    groups: dict[str, list[str]],
    key_prefix: str,
    manual_label: str | None = None,
    show_manual: bool = True,
) -> list[str]:
    """Interactive group/region selector + searchable airport multiselect with 'City (IATA)' autocomplete and uncheck support."""
    group_names = list(groups.keys())
    selected_groups = st.multiselect(
        label_group,
        options=group_names,
        key=f"{key_prefix}_groups",
    )

    prev_groups_key = f"{key_prefix}_prev_groups"
    apts_state_key = f"{key_prefix}_airports_ms"

    if prev_groups_key not in st.session_state:
        st.session_state[prev_groups_key] = []
    if apts_state_key not in st.session_state:
        st.session_state[apts_state_key] = []

    prev_groups = st.session_state[prev_groups_key]
    if selected_groups != prev_groups:
        added_groups = [g for g in selected_groups if g not in prev_groups]
        removed_groups = [g for g in prev_groups if g not in selected_groups]
        current_apts = list(st.session_state[apts_state_key])

        for g in added_groups:
            for code in groups.get(g, []):
                if code not in current_apts:
                    current_apts.append(code)

        removed_codes = {code for g in removed_groups for code in groups.get(g, [])}
        still_active_codes = {code for g in selected_groups for code in groups.get(g, [])}
        codes_to_remove = removed_codes - still_active_codes
        current_apts = [c for c in current_apts if c not in codes_to_remove]

        st.session_state[apts_state_key] = current_apts
        st.session_state[prev_groups_key] = list(selected_groups)

    # Build full searchable list of airports (selected group airports first, then all others from config)
    group_airports = [c for g in selected_groups for c in groups.get(g, [])]
    all_known = list(dict.fromkeys(group_airports + sorted(AIRPORT_CITY_NAMES.keys())))

    is_en = st.session_state.get("lang", "EN") == "EN"
    box_label = (
        "Airports (uncheck unwanted or type city/IATA, e.g. Krakow (KRK))"
        if is_en
        else "Lotniska (odznacz niechciane lub wpisz miasto/kod, np. Kraków (KRK))"
    )

    selected_airports = st.multiselect(
        box_label,
        options=all_known,
        format_func=lambda code: f"{get_localized_city_name(code)} ({code})",
        key=apts_state_key,
    )

    return list(dict.fromkeys(selected_airports))


# ---------------------------------------------------------------------------
# Global Column Configuration for Tables (No "Book" column)
# ---------------------------------------------------------------------------
def get_column_config() -> dict:
    is_pl = st.session_state.get("lang", "EN") == "PL"
    return {
        "Price EUR": st.column_config.NumberColumn("Cena EUR" if is_pl else "Price EUR", format="%.2f €"),
        "Total EUR": st.column_config.NumberColumn("Total EUR", format="%.2f €"),
        "Out EUR": st.column_config.NumberColumn("Wylot EUR" if is_pl else "Out EUR", format="%.2f €"),
        "Ret EUR": st.column_config.NumberColumn("Powrót EUR" if is_pl else "Ret EUR", format="%.2f €"),
        "Cena EUR": st.column_config.NumberColumn("Cena EUR" if is_pl else "Price EUR", format="%.2f €"),
        "Nights": st.column_config.NumberColumn("Noce" if is_pl else "Nights", format="%d"),
        "Stops": st.column_config.NumberColumn("Przesiadki" if is_pl else "Stops", format="%d"),
    }


# Backwards compatibility reference
MAIN_TABLE_COLUMN_CONFIG = {
    "Total EUR": st.column_config.NumberColumn("Total (€)", format="%.2f €"),
    "Out EUR": st.column_config.NumberColumn("Outbound (€)", format="%.2f €"),
    "Ret EUR": st.column_config.NumberColumn("Return (€)", format="%.2f €"),
    "Cena EUR": st.column_config.NumberColumn("Price (€)", format="%.2f €"),
    "Nights": st.column_config.NumberColumn("Nights", format="%d"),
    "Stops": st.column_config.NumberColumn("Stops", format="%d"),
}


# ---------------------------------------------------------------------------
# Helper: format results tables (No "Book" column)
# ---------------------------------------------------------------------------
def _format_matched_results(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        mock_flag = " [MOCK]" if r.get("is_mock") else ""
        records.append({
            "Total EUR": round(float(r["total_eur"]), 2),
            "Out EUR": round(float(r["price_out_eur"]), 2),
            "Ret EUR": round(float(r["price_ret_eur"]), 2),
            "Outbound": f"{r['out_orig']}->{r['out_dest']}",
            "Out Date": f"{r['out_date']} {r.get('out_dep_time', '')}".strip(),
            "Out Airline": f"{r.get('out_airline', '')} {r.get('out_flight_no', '')}".strip(),
            "Return": f"{r['ret_orig']}->{r['ret_dest']}",
            "Ret Date": f"{r['ret_date']} {r.get('ret_dep_time', '')}".strip(),
            "Ret Airline": f"{r.get('ret_airline', '')} {r.get('ret_flight_no', '')}".strip(),
            "Nights": int(r["nights"]) if r.get("nights") is not None else None,
            "Stops": f"{r.get('out_stops', 0)}+{r.get('ret_stops', 0)}",
            "Source": f"{r.get('out_provider', '')}{mock_flag}",
        })
    return pd.DataFrame(records)


def _format_kiwi_results(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        mock_flag = " [MOCK]" if r.get("is_mock") else ""
        ret_orig = r.get("return_orig_airport") or r.get("dest_airport") or ""
        ret_dest = r.get("return_dest_airport") or r.get("orig_airport") or ""

        total_price = round(float(r.get("price_eur", 0)), 2)
        out_price = round(float(r["price_outbound_eur"]), 2) if r.get("price_outbound_eur") is not None else None
        ret_price = round(float(r["price_return_eur"]), 2) if r.get("price_return_eur") is not None else None

        # Dual key lookup from Kiwi parser and SQLite flights table
        out_d = r.get("outbound_date") or r.get("flight_date") or ""
        out_dep = r.get("outbound_dep_time") or r.get("departure_time") or ""
        out_airline = r.get("outbound_airline") or r.get("airline") or ""
        out_fno = r.get("outbound_flight_no") or r.get("flight_no") or ""

        ret_d = r.get("return_date") or ""
        ret_dep = r.get("return_dep_time") or ""
        ret_airline = r.get("return_airline") or ""
        ret_fno = r.get("return_flight_no") or ""

        rec = {
            "Total EUR": total_price,
            "Outbound": f"{r.get('orig_airport', '')}->{r.get('dest_airport', '')}",
            "Out Date": f"{out_d} {out_dep}".strip(),
            "Out Airline": f"{out_airline} {out_fno}".strip(),
            "Return": f"{ret_orig}->{ret_dest}",
            "Ret Date": f"{ret_d} {ret_dep}".strip(),
            "Ret Airline": f"{ret_airline} {ret_fno}".strip(),
            "Nights": int(r["nights"]) if r.get("nights") not in (None, "?") else None,
            "Stops": int(r.get("stops", 0)) if isinstance(r.get("stops"), (int, float)) else r.get("stops", 0),
            "Source": f"Kiwi{mock_flag}",
        }
        if out_price is not None:
            rec["Out EUR"] = out_price
        if ret_price is not None:
            rec["Ret EUR"] = ret_price

        # Do NOT add "Book"
        records.append(rec)
    return pd.DataFrame(records)


def _apply_column_value_extractor(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """
    Pozwala wybrać jedną lub więcej kolumn i wyodrębnić z nich tylko wskazane wartości
    (np. dest_airport -> ['BCN', 'CTA'] lub Outbound -> ['KRK->BCN', 'KTW->CTA']).
    Działa dla wszystkich kolumn tabeli.
    """
    if df.empty:
        return df
    with st.expander(t("col_filter_title"), expanded=False):
        cols_to_filter = st.multiselect(
            t("col_filter_select_cols"),
            options=list(df.columns),
            key=f"{key_prefix}_col_ext_cols",
        )
        filtered = df.copy()
        if cols_to_filter:
            f_cols = st.columns(min(len(cols_to_filter), 4))
            for idx, col_name in enumerate(cols_to_filter):
                with f_cols[idx % len(f_cols)]:
                    unique_vals = sorted(filtered[col_name].dropna().astype(str).unique().tolist())
                    selected_vals = st.multiselect(
                        f"{col_name}",
                        options=unique_vals,
                        key=f"{key_prefix}_col_ext_val_{col_name}",
                    )
                    if selected_vals:
                        filtered = filtered[filtered[col_name].astype(str).isin(selected_vals)]
        return filtered


def _apply_local_filters(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df.copy()

    # Identify date and night bounds from current df
    out_date_col = next((c for c in ["Out Date", "Wylot", "out_date", "flight_date"] if c in df.columns), None)
    ret_date_col = next((c for c in ["Ret Date", "Powrót", "ret_date", "return_date"] if c in df.columns), None)
    nights_col = next((c for c in ["Nights", "Noce", "nights"] if c in df.columns), None)
    price_col = next((c for c in ["Total EUR", "Price EUR", "Cena EUR", "price_eur", "total_eur"] if c in df.columns), None)
    airline_cols = [c for c in df.columns if any(k in c for k in ["Airline", "Linia", "airline"])]
    stops_col = next((c for c in ["Stops", "stops"] if c in df.columns), None)

    # Determine default/min/max for dates
    min_out_d, max_out_d = None, None
    if out_date_col:
        try:
            valid_out_dates = [
                datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
                for v in df[out_date_col].dropna()
                if len(str(v)) >= 10 and str(v)[:10].replace("-", "").isdigit()
            ]
            if valid_out_dates:
                min_out_d = min(valid_out_dates)
                max_out_d = max(valid_out_dates)
        except Exception:
            pass

    min_ret_d, max_ret_d = None, None
    if ret_date_col:
        try:
            valid_ret_dates = [
                datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
                for v in df[ret_date_col].dropna()
                if len(str(v)) >= 10 and str(v)[:10].replace("-", "").isdigit()
            ]
            if valid_ret_dates:
                min_ret_d = min(valid_ret_dates)
                max_ret_d = max(valid_ret_dates)
        except Exception:
            pass

    # Determine nights bounds
    min_n_val, max_n_val = 1, 30
    if nights_col:
        numeric_nights = pd.to_numeric(df[nights_col], errors="coerce").dropna()
        if not numeric_nights.empty:
            min_n_val = max(1, int(numeric_nights.min()))
            max_n_val = max(min_n_val, int(numeric_nights.max()))

    # Determine price bounds
    max_p_val = 500
    if price_col:
        num_p = pd.to_numeric(df[price_col], errors="coerce").dropna()
        if not num_p.empty:
            max_p_val = max(500, int(num_p.max()) + 10)

    # Dynamic session signature to reset sliders when a new search occurs
    data_sig = f"{len(df)}_{min_out_d}_{max_out_d}_{min_n_val}_{max_n_val}"

    # ROW 1: Filter Dep FROM–TO, Filter Ret FROM–TO, Filter Nights (Min–Max), Max price (€)
    r1_c1, r1_c2, r1_c3, r1_c4 = st.columns([2.5, 2.5, 2.5, 2.5])

    with r1_c1:
        if min_out_d and max_out_d and min_out_d < max_out_d:
            flt_out_range = st.date_input(
                t("flt_dep_range"),
                value=(min_out_d, max_out_d),
                min_value=min_out_d,
                max_value=max_out_d,
                format="YYYY-MM-DD",
                key=f"{key_prefix}_flt_out_{data_sig}",
            )
        elif min_out_d:
            st.caption(f"{t('dep_from')}: {min_out_d}")
            flt_out_range = (min_out_d, min_out_d)
        else:
            flt_out_range = None

    with r1_c2:
        if min_ret_d and max_ret_d and min_ret_d < max_ret_d:
            flt_ret_range = st.date_input(
                t("flt_ret_range"),
                value=(min_ret_d, max_ret_d),
                min_value=min_ret_d,
                max_value=max_ret_d,
                format="YYYY-MM-DD",
                key=f"{key_prefix}_flt_ret_{data_sig}",
            )
        elif min_ret_d:
            st.caption(f"{t('ret_from')}: {min_ret_d}")
            flt_ret_range = (min_ret_d, min_ret_d)
        else:
            flt_ret_range = None

    with r1_c3:
        if nights_col and min_n_val < max_n_val:
            flt_nights = st.slider(
                t("flt_nights"),
                min_value=min_n_val,
                max_value=max_n_val,
                value=(min_n_val, max_n_val),
                step=1,
                key=f"{key_prefix}_flt_n_{data_sig}",
            )
        elif nights_col:
            flt_nights = (min_n_val, max_n_val)
            st.caption(f"{t('min_nights')}: {min_n_val}")
        else:
            flt_nights = None

    with r1_c4:
        flt_max_price = st.number_input(
            t("flt_max_price"),
            min_value=0,
            max_value=max(2000, max_p_val + 100),
            value=max_p_val,
            step=10,
            key=f"{key_prefix}_flt_maxp_{data_sig}",
        )

    # Extract all destination airports available in results
    avail_airports: set[str] = set()
    if "Outbound" in df.columns:
        for val in df["Outbound"].dropna():
            parts = str(val).split("->")
            if len(parts) == 2:
                avail_airports.add(parts[1].strip())
    if "dest_airport" in df.columns:
        avail_airports.update(str(x).strip() for x in df["dest_airport"].dropna() if str(x).strip())
    if "IATA" in df.columns:
        avail_airports.update(str(x).strip() for x in df["IATA"].dropna() if str(x).strip())
    if "destination_airport" in df.columns:
        avail_airports.update(str(x).strip() for x in df["destination_airport"].dropna() if str(x).strip())

    # ROW 2: Airports (e.g. BCN, CTA), Dep weekdays, Ret weekdays, Carriers, Direct only
    r2_c1, r2_c2, r2_c3, r2_c4, r2_c5 = st.columns([2, 2, 2, 2.5, 1.5])

    with r2_c1:
        sel_airports = st.multiselect(
            t("flt_airports"),
            sorted(avail_airports),
            key=f"{key_prefix}_flt_airports_{data_sig}",
        )

    with r2_c2:
        flt_owd = st.multiselect(
            t("dep_weekdays"),
            options=WEEKDAYS_PL,
            default=WEEKDAYS_PL,
            format_func=lambda wd: WEEKDAY_PL_TO_EN.get(wd, wd) if st.session_state.get("lang", "EN") == "EN" else wd,
            key=f"{key_prefix}_flt_owd_{data_sig}",
        )

    with r2_c3:
        flt_rwd = st.multiselect(
            t("ret_weekdays"),
            options=WEEKDAYS_PL,
            default=WEEKDAYS_PL,
            format_func=lambda wd: WEEKDAY_PL_TO_EN.get(wd, wd) if st.session_state.get("lang", "EN") == "EN" else wd,
            key=f"{key_prefix}_flt_rwd_{data_sig}",
        )

    with r2_c4:
        all_airlines: set[str] = set()
        for c in airline_cols:
            all_airlines.update(str(v).strip() for v in df[c].dropna().unique() if str(v).strip())
        selected_airlines = st.multiselect(
            t("flt_airlines"),
            sorted(all_airlines),
            key=f"{key_prefix}_flt_al_{data_sig}",
        )

    with r2_c5:
        st.write("")
        direct_only = st.checkbox(
            t("flt_direct"),
            key=f"{key_prefix}_flt_dir_{data_sig}",
        )

    # --- APPLY FILTERS IN MEMORY ---
    if out_date_col and flt_out_range and isinstance(flt_out_range, (list, tuple)) and len(flt_out_range) == 2:
        d_start, d_end = flt_out_range[0].strftime("%Y-%m-%d"), flt_out_range[1].strftime("%Y-%m-%d")
        filtered = filtered[filtered[out_date_col].astype(str).str[:10].between(d_start, d_end)]

    if ret_date_col and flt_ret_range and isinstance(flt_ret_range, (list, tuple)) and len(flt_ret_range) == 2:
        rd_start, rd_end = flt_ret_range[0].strftime("%Y-%m-%d"), flt_ret_range[1].strftime("%Y-%m-%d")
        filtered = filtered[filtered[ret_date_col].astype(str).str[:10].between(rd_start, rd_end)]

    if nights_col and flt_nights:
        num_nights = pd.to_numeric(filtered[nights_col], errors="coerce")
        filtered = filtered[(num_nights >= flt_nights[0]) & (num_nights <= flt_nights[1])]

    if price_col:
        num_price = pd.to_numeric(filtered[price_col], errors="coerce").fillna(9999.0)
        filtered = filtered[num_price <= flt_max_price]

    if sel_airports:
        def _matches_airport(row):
            if "Outbound" in row:
                parts = str(row["Outbound"]).replace("→", "->").split("->")
                if len(parts) == 2 and parts[1].strip() in sel_airports:
                    return True
            if "dest_airport" in row and str(row["dest_airport"]).strip() in sel_airports:
                return True
            if "IATA" in row and str(row["IATA"]).strip() in sel_airports:
                return True
            if "destination_airport" in row and str(row["destination_airport"]).strip() in sel_airports:
                return True
            if "Return" in row:
                parts = str(row["Return"]).replace("→", "->").split("->")
                if len(parts) == 2 and parts[0].strip() in sel_airports:
                    return True
            return False
        filtered = filtered[filtered.apply(_matches_airport, axis=1)]

    if out_date_col and flt_owd and len(flt_owd) < 7:
        allowed_owd_indices = {WEEKDAY_INDEX_MAP[w] for w in flt_owd if w in WEEKDAY_INDEX_MAP}
        def _match_out_wd(val):
            try:
                dt = datetime.strptime(str(val)[:10], "%Y-%m-%d")
                return dt.weekday() in allowed_owd_indices
            except Exception:
                return True
        filtered = filtered[filtered[out_date_col].apply(_match_out_wd)]

    if ret_date_col and flt_rwd and len(flt_rwd) < 7:
        allowed_rwd_indices = {WEEKDAY_INDEX_MAP[w] for w in flt_rwd if w in WEEKDAY_INDEX_MAP}
        def _match_ret_wd(val):
            try:
                dt = datetime.strptime(str(val)[:10], "%Y-%m-%d")
                return dt.weekday() in allowed_rwd_indices
            except Exception:
                return True
        filtered = filtered[filtered[ret_date_col].apply(_match_ret_wd)]

    if selected_airlines and airline_cols:
        mask = pd.Series(False, index=filtered.index)
        for col_name in airline_cols:
            if col_name in filtered.columns:
                for al in selected_airlines:
                    mask |= filtered[col_name].astype(str).str.contains(al, case=False, na=False)
        filtered = filtered[mask]

    if direct_only and stops_col:
        filtered = filtered[
            filtered[stops_col].apply(lambda x: str(x).replace(" ", "") in ("0", "0+0"))
        ]

    # Apply Column Value Extractor
    filtered = _apply_column_value_extractor(filtered, key_prefix)

    return filtered


def _filter_rows_by_unified_schedule(
    rows: list[dict],
    out_date_from: str | None = None,
    out_date_to: str | None = None,
    ret_date_from: str | None = None,
    ret_date_to: str | None = None,
    min_nights: int | None = None,
    max_nights: int | None = None,
    out_weekdays: list[str] | None = None,
    ret_weekdays: list[str] | None = None,
) -> list[dict]:
    """Filter flight dicts across all tabs by unified schedule parameters."""
    if not rows:
        return []

    filtered = []
    allowed_out_indices = {WEEKDAY_INDEX_MAP[w] for w in out_weekdays if w in WEEKDAY_INDEX_MAP} if out_weekdays else None
    allowed_ret_indices = {WEEKDAY_INDEX_MAP[w] for w in ret_weekdays if w in WEEKDAY_INDEX_MAP} if ret_weekdays else None

    for r in rows:
        out_d_str = r.get("outbound_date") or r.get("out_date") or r.get("flight_date") or ""
        ret_d_str = r.get("return_date") or r.get("ret_date") or ""

        if out_d_str:
            clean_out = out_d_str[:10]
            if out_date_from and clean_out < out_date_from:
                continue
            if out_date_to and clean_out > out_date_to:
                continue
            if allowed_out_indices is not None:
                try:
                    dt_out = datetime.strptime(clean_out, "%Y-%m-%d")
                    if dt_out.weekday() not in allowed_out_indices:
                        continue
                except (ValueError, TypeError):
                    pass

        if ret_d_str:
            clean_ret = ret_d_str[:10]
            if ret_date_from and clean_ret < ret_date_from:
                continue
            if ret_date_to and clean_ret > ret_date_to:
                continue
            if allowed_ret_indices is not None:
                try:
                    dt_ret = datetime.strptime(clean_ret, "%Y-%m-%d")
                    if dt_ret.weekday() not in allowed_ret_indices:
                        continue
                except (ValueError, TypeError):
                    pass

        nights_val = r.get("nights")
        if nights_val is None or nights_val == "?":
            if out_d_str and ret_d_str:
                try:
                    d1 = datetime.strptime(out_d_str[:10], "%Y-%m-%d")
                    d2 = datetime.strptime(ret_d_str[:10], "%Y-%m-%d")
                    nights_val = (d2 - d1).days
                except (ValueError, TypeError):
                    nights_val = None

        if nights_val is not None and isinstance(nights_val, (int, float)):
            if min_nights is not None and nights_val < min_nights:
                continue
            if max_nights is not None and nights_val > max_nights:
                continue

        filtered.append(r)

    return filtered


def _generate_dates_in_range(
    date_from: datetime,
    date_to: datetime,
    allowed_weekdays: list[str] | None = None,
) -> list[str]:
    """Generate list of ISO date strings in range, filtered by weekday."""
    dates = []
    current = date_from
    allowed_indices = (
        {WEEKDAY_INDEX_MAP[w] for w in allowed_weekdays if w in WEEKDAY_INDEX_MAP}
        if allowed_weekdays is not None
        else None
    )
    while current <= date_to:
        if allowed_indices is None or current.weekday() in allowed_indices:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _sync_weekdays_with_date_range(
    d_from,
    d_to,
    wd_state_key: str,
    prev_range_key: str,
) -> None:
    """Auto-update weekday multiselect when date range changes.
    If range is 1..6 days (< 7 days), select only weekdays present in [d_from, d_to].
    If range is >= 7 days, select all 7 weekdays.
    Only triggers when (d_from, d_to) changes so manual user unchecking is preserved!
    """
    if not d_from or not d_to:
        return
    if wd_state_key not in st.session_state:
        st.session_state[wd_state_key] = list(WEEKDAYS_PL)

    cur_range = (str(d_from), str(d_to))
    if st.session_state.get(prev_range_key) != cur_range:
        st.session_state[prev_range_key] = cur_range
        span_days = (d_to - d_from).days
        if 0 <= span_days < 6:  # 1 to 6 days inclusive (shorter than a 7-day week)
            present_wds = set()
            curr = d_from
            while curr <= d_to:
                present_wds.add(WEEKDAY_MAP[curr.weekday()])
                curr += timedelta(days=1)
            st.session_state[wd_state_key] = [w for w in WEEKDAYS_PL if w in present_wds]
        elif span_days >= 6:
            st.session_state[wd_state_key] = list(WEEKDAYS_PL)


# =========================================================================
# TABS
# =========================================================================
tab_kiwi, tab_exact = st.tabs([
    t("tab_b"),
    t("tab_c"),
])


# =========================================================================
# TAB B: Kiwi MCP Flexible
# =========================================================================
with tab_kiwi:
    st.caption(t("tab_b_sub"))

    kb1, kb2, kb3, kb4 = st.columns([2, 2, 2, 2])

    with kb1:
        st.markdown(f"**{t('from')}**")
        kiwi_origins = _compact_airport_selector(
            t("origin_group"), ORIGIN_GROUPS, "kb_orig",
        )

    with kb2:
        st.markdown(f"**{t('to')}**")
        kiwi_dest_source = st.radio(
            t("source"), [t("region"), t("metro")], key="kb_dsrc", horizontal=True,
        )
        if kiwi_dest_source in (t("region"), "Region"):
            kiwi_dests = _compact_airport_selector(
                t("target_region"), DESTINATION_REGIONS, "kb_dreg",
            )
        else:
            kiwi_dests = _compact_airport_selector(
                t("metro_group"), METRO_GROUPS, "kb_dmet",
            )

        if kiwi_dests:
            st.caption(f"{len(kiwi_dests)} airports: {', '.join(kiwi_dests[:10])}{'…' if len(kiwi_dests) > 10 else ''}")

    with kb3:
        st.markdown(f"**{t('when_stay')}**")
        kbd1, kbd2 = st.columns(2)
        with kbd1:
            kiwi_date_from = st.date_input(
                t("dep_from"), value=datetime.now().date() + timedelta(days=14), format="YYYY-MM-DD", key="kb_df",
            )
        with kbd2:
            kiwi_date_to = st.date_input(
                t("dep_to"), value=datetime.now().date() + timedelta(days=20), format="YYYY-MM-DD", key="kb_dt",
            )

        kbr1, kbr2 = st.columns(2)
        with kbr1:
            kiwi_ret_from = st.date_input(
                t("ret_from"), value=datetime.now().date() + timedelta(days=17), format="YYYY-MM-DD", key="kb_rf",
            )
        with kbr2:
            kiwi_ret_to = st.date_input(
                t("ret_to"), value=datetime.now().date() + timedelta(days=30), format="YYYY-MM-DD", key="kb_rt",
            )

        kc1, kc2 = st.columns(2)
        with kc1:
            kiwi_nmin = st.number_input(t("min_nights"), value=3, min_value=1, key="kb_nmin")
        with kc2:
            kiwi_nmax = st.number_input(t("max_nights"), value=10, min_value=1, key="kb_nmax")

        _sync_weekdays_with_date_range(kiwi_date_from, kiwi_date_to, "kb_owd", "kb_prev_out_range")
        _sync_weekdays_with_date_range(kiwi_ret_from, kiwi_ret_to, "kb_rwd", "kb_prev_ret_range")

        kiwi_out_weekdays = st.multiselect(
            t("dep_weekdays"),
            options=WEEKDAYS_PL,
            format_func=lambda wd: WEEKDAY_PL_TO_EN.get(wd, wd) if st.session_state.get("lang", "EN") == "EN" else wd,
            key="kb_owd",
        )
        kiwi_ret_weekdays = st.multiselect(
            t("ret_weekdays"),
            options=WEEKDAYS_PL,
            format_func=lambda wd: WEEKDAY_PL_TO_EN.get(wd, wd) if st.session_state.get("lang", "EN") == "EN" else wd,
            key="kb_rwd",
        )

    with kb4:
        st.markdown(f"**{t('options_start')}**")
        kiwi_max_price = st.number_input(t("max_price"), value=200, min_value=0, step=10, key="kb_maxp")
        kiwi_direct = st.checkbox(t("direct_only"), key="kb_dir")

        kb_b1, kb_b2, kb_b3 = st.columns([2, 2, 2])
        with kb_b1:
            kiwi_dryrun = st.button(t("btn_dryrun"), key="kb_dr", use_container_width=True)
        with kb_b2:
            kiwi_exec = st.button(t("btn_search"), key="kb_ex", use_container_width=True,
                                   disabled=st.session_state.search_running, type="primary")
        with kb_b3:
            kiwi_load_sql = st.button(t("btn_load_sql"), key="kb_load_sql", use_container_width=True)

    if kiwi_dryrun and kiwi_origins and kiwi_dests:
        total_q = kiwi_mcp.count_kiwi_queries(kiwi_origins, kiwi_dests)
        conn = db.get_connection()
        cached_count = 0
        missing_pairs = []
        for orig in kiwi_origins:
            for dest in kiwi_dests:
                if orig == dest:
                    continue
                uncovered = db.compute_uncovered_kiwi_range(
                    conn, orig, dest, str(kiwi_date_from), str(kiwi_date_to),
                    int(kiwi_nmin), int(kiwi_nmax), cache_ttl,
                    is_mock=st.session_state.mock_mode,
                )
                if uncovered is None:
                    cached_count += 1
                else:
                    missing_pairs.append((orig, dest, uncovered))
        conn.close()
        report = safety.calculate_search_cost(
            total_queries=total_q, cached_queries=cached_count,
            provider="kiwi_mcp", user_max_calls=user_max_calls,
        )
        st.info(f"Par: {total_q} | Pokryte w cache: {cached_count} | Do pobrania (HTTP): {report.http_queries_needed}" if st.session_state.lang == "PL" else f"Pairs: {total_q} | Covered in cache: {cached_count} | To fetch (HTTP): {report.http_queries_needed}")
        if missing_pairs and report.http_queries_needed > 0:
            st.caption("Brakujące podprzedziały dat:" if st.session_state.lang == "PL" else "Missing date subranges:")
            for o, d, (mf, mt) in missing_pairs[:5]:
                st.caption(f"- {o}->{d}: {mf} do {mt}")
        if report.blocked:
            st.error(f"Zablokowano: {report.block_reason}" if st.session_state.lang == "PL" else f"Blocked: {report.block_reason}")

    if kiwi_load_sql:
        if not kiwi_origins or not kiwi_dests:
            st.error(t("select_airports_err"))
        else:
            conn = db.get_connection()
            loaded = db.query_flights_by_criteria(
                conn,
                origins=kiwi_origins,
                dests=kiwi_dests,
                direction="roundtrip",
                date_from=str(kiwi_date_from),
                date_to=str(kiwi_date_to),
                is_mock=st.session_state.mock_mode,
            )
            conn.close()
            loaded.sort(key=lambda x: x.get("price_eur", 9999))
            st.session_state.kiwi_results = loaded
            st.success(f"Wczytano {len(loaded)} ofert bezpośrednio z lokalnej bazy SQLite (0 zapytań API).")

    if kiwi_exec:
        if st.session_state.search_running:
            st.error("Inne wyszukiwanie w toku.")
        elif not kiwi_origins or not kiwi_dests:
            st.error("Wybierz lotniska.")
        else:
            st.session_state.search_running = True
            try:
                conn = db.get_connection()
                search_id = str(uuid.uuid4())[:8]
                safety.reset_call_counter(search_id)
                total_pairs = kiwi_mcp.count_kiwi_queries(kiwi_origins, kiwi_dests)
                progress = st.progress(0)
                done = 0
                http_sent = 0
                effective_max = min(user_max_calls, safety.HARD_MAX_CALLS_PER_SEARCH)

                if st.session_state.mock_mode:
                    for orig in kiwi_origins:
                        for dest in kiwi_dests:
                            if orig == dest:
                                done += 1
                                continue

                            uncovered = db.compute_uncovered_kiwi_range(
                                conn, orig, dest, str(kiwi_date_from), str(kiwi_date_to),
                                int(kiwi_nmin), int(kiwi_nmax), cache_ttl,
                                is_mock=True,
                            )
                            if uncovered is None:
                                done += 1
                                progress.progress(min(done / max(total_pairs, 1), 1.0))
                                continue

                            miss_from, miss_to = uncovered
                            params = {
                                "flyFrom": orig, "flyTo": dest,
                                "date_from": miss_from,
                                "date_to": miss_to,
                                "return_from": str(kiwi_ret_from),
                                "return_to": str(kiwi_ret_to),
                                "nmin": int(kiwi_nmin), "nmax": int(kiwi_nmax),
                            }
                            results = generate_mock_kiwi_flights(
                                origin_airport=orig,
                                dest_airport=dest,
                                date_from=miss_from,
                                date_to=miss_to,
                                return_from=str(kiwi_ret_from),
                                return_to=str(kiwi_ret_to),
                                nights_in_dst_from=int(kiwi_nmin),
                                nights_in_dst_to=int(kiwi_nmax),
                            )
                            db.store_flights(conn, "mock", params, results, is_mock=True)
                            done += 1
                            progress.progress(min(done / max(total_pairs, 1), 1.0))
                else:
                    # LIVE Kiwi MCP
                    client = kiwi_mcp.KiwiMCPClient()
                    for orig in kiwi_origins:
                        for dest in kiwi_dests:
                            if orig == dest:
                                done += 1
                                continue

                            uncovered = db.compute_uncovered_kiwi_range(
                                conn, orig, dest, str(kiwi_date_from), str(kiwi_date_to),
                                int(kiwi_nmin), int(kiwi_nmax), cache_ttl,
                                is_mock=False,
                            )
                            if uncovered is None:
                                done += 1
                                progress.progress(min(done / max(total_pairs, 1), 1.0))
                                continue

                            if http_sent >= effective_max:
                                st.warning(
                                    f"Reached limit of {effective_max} HTTP requests. Remaining pairs skipped."
                                    if st.session_state.get("lang", "EN") == "EN"
                                    else f"Osiągnięto limit {effective_max} zapytań HTTP. Reszta par pominięta."
                                )
                                break

                            miss_from, miss_to = uncovered
                            params = {
                                "flyFrom": orig, "flyTo": dest,
                                "date_from": miss_from,
                                "date_to": miss_to,
                                "return_from": str(kiwi_ret_from),
                                "return_to": str(kiwi_ret_to),
                                "nmin": int(kiwi_nmin), "nmax": int(kiwi_nmax),
                            }

                            try:
                                raw = client.search_flight(
                                    fly_from=orig,
                                    fly_to=dest,
                                    departure_date=miss_from,
                                    departure_date_to=miss_to,
                                    return_date=str(kiwi_ret_from),
                                    return_date_to=str(kiwi_ret_to),
                                    nights_in_dst_from=int(kiwi_nmin),
                                    nights_in_dst_to=int(kiwi_nmax),
                                    currency="EUR",
                                    max_sector_stopovers=0 if kiwi_direct else None,
                                )
                                http_sent += 1
                                parsed = kiwi_mcp.parse_kiwi_response(raw, orig, dest)
                                if parsed:
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
                                jitter_delay = random.uniform(2.0, 3.5) if http_sent >= 5 else random.uniform(1.2, 2.6)
                                time.sleep(jitter_delay)
                            except Exception as e:
                                st.warning(f"Błąd {orig}->{dest}: {e}")

                            done += 1
                            progress.progress(min(done / max(total_pairs, 1), 1.0))
                        else:
                            continue
                        break

                progress.empty()

                # Query full dataset from SQLite across the whole requested range [kiwi_date_from, kiwi_date_to]
                loaded = db.query_flights_by_criteria(
                    conn,
                    origins=kiwi_origins,
                    dests=kiwi_dests,
                    direction="roundtrip",
                    date_from=str(kiwi_date_from),
                    date_to=str(kiwi_date_to),
                    is_mock=st.session_state.mock_mode,
                )
                conn.close()
                loaded.sort(key=lambda x: x.get("price_eur", 9999))
                st.session_state.kiwi_results = loaded
                st.success(
                    f"Search complete ({http_sent} HTTP requests). Loaded {len(loaded)} offers from SQLite."
                    if st.session_state.get("lang", "EN") == "EN"
                    else f"Pobieranie zakończone ({http_sent} zapytań HTTP). Wczytano {len(loaded)} ofert z bazy SQLite."
                )
            finally:
                st.session_state.search_running = False

    # Display Kiwi results
    if st.session_state.kiwi_results:
        filtered_results = _filter_rows_by_unified_schedule(
            st.session_state.kiwi_results,
            out_date_from=str(kiwi_date_from),
            out_date_to=str(kiwi_date_to),
            ret_date_from=str(kiwi_ret_from),
            ret_date_to=str(kiwi_ret_to),
            min_nights=int(kiwi_nmin),
            max_nights=int(kiwi_nmax),
            out_weekdays=kiwi_out_weekdays,
            ret_weekdays=kiwi_ret_weekdays,
        )
        df = _format_kiwi_results(filtered_results)
        if not df.empty:
            st.markdown(f"**{len(df)} {t('offers')}**")
            df = _apply_local_filters(df, "kb")
            st.dataframe(df, column_config=get_column_config(), use_container_width=True, hide_index=True)
        else:
            st.info(t("no_results"))


# =========================================================================
# TAB C: Exact + SQL Matcher
# =========================================================================
with tab_exact:
    st.caption(t("tab_c_sub"))

    ec1, ec2, ec3, ec4 = st.columns([2, 2, 2.5, 1.5])

    with ec1:
        st.markdown(f"**{t('from')}**")
        exact_origins = _compact_airport_selector(
            t("origin_group"), ORIGIN_GROUPS, "ec_orig",
        )
        if exact_origins:
            orig_chunks_n = len(serpapi_client.chunk_airports(exact_origins, 6))
            orig_rem = len(exact_origins) % 6
            orig_free = (6 - orig_rem) if orig_rem != 0 else 0
            if st.session_state.get("lang", "EN") == "EN":
                st.caption(f"{len(exact_origins)} origin(s) → {orig_chunks_n} chunk(s) (can add {orig_free} more for 0 extra cost)")
            else:
                st.caption(f"{len(exact_origins)} wylot(ów) → {orig_chunks_n} paczka/i (możesz dodać {orig_free} bez wzrostu kosztu)")
        allow_diff_return = st.checkbox(
            t("allow_diff_return"),
            key="ec_flex",
        )

    with ec2:
        st.markdown(f"**{t('to')}**")
        exact_dest_source = st.radio(
            t("source"), [t("region"), t("metro")], key="ec_dsrc", horizontal=True,
        )
        if exact_dest_source in (t("region"), "Region"):
            exact_dests = _compact_airport_selector(
                t("target_region"), DESTINATION_REGIONS, "ec_dreg",
            )
        else:
            exact_dests = _compact_airport_selector(
                t("metro_group"), METRO_GROUPS, "ec_dmet",
            )

        if exact_dests:
            n_chunks = len(serpapi_client.chunk_airports(exact_dests, 6))
            rem = len(exact_dests) % 6
            free_slots = (6 - rem) if rem != 0 else 0
            if st.session_state.get("lang", "EN") == "EN":
                slot_hint = (
                    f" — you can add {free_slots} more airport(s) for 0 extra API calls!"
                    if free_slots > 0
                    else " — full chunk of 6 (optimal API efficiency!)"
                )
                st.caption(f"{len(exact_dests)} airports → {n_chunks} chunk(s) of ≤6{slot_hint}")
            else:
                slot_hint = (
                    f" — możesz dodać jeszcze {free_slots} lotnisk(a) za 0 dodatkowych zapytań API!"
                    if free_slots > 0
                    else " — pełna paczka 6/6 (optymalne zużycie API!)"
                )
                st.caption(f"{len(exact_dests)} lotnisk → {n_chunks} paczek po ≤6{slot_hint}")

    with ec3:
        st.markdown(f"**{t('when_stay')}**")
        ecd1, ecd2 = st.columns(2)
        with ecd1:
            exact_date_from = st.date_input(
                t("dep_from"), value=datetime.now().date() + timedelta(days=30), format="YYYY-MM-DD", key="ec_df",
            )
        with ecd2:
            exact_date_to = st.date_input(
                t("dep_to"), value=datetime.now().date() + timedelta(days=37), format="YYYY-MM-DD", key="ec_dt",
            )

        ecr1, ecr2 = st.columns(2)
        with ecr1:
            exact_ret_from = st.date_input(
                t("ret_from"), value=datetime.now().date() + timedelta(days=33), format="YYYY-MM-DD", key="ec_rf",
            )
        with ecr2:
            exact_ret_to = st.date_input(
                t("ret_to"), value=datetime.now().date() + timedelta(days=47), format="YYYY-MM-DD", key="ec_rt",
            )

        ecn1, ecn2 = st.columns(2)
        with ecn1:
            exact_nmin = st.number_input(t("min_nights"), value=3, min_value=1, key="ec_nmin")
        with ecn2:
            exact_nmax = st.number_input(t("max_nights"), value=10, min_value=1, key="ec_nmax")

        # Weekday filters
        _sync_weekdays_with_date_range(exact_date_from, exact_date_to, "ec_owd", "ec_prev_out_range")
        _sync_weekdays_with_date_range(exact_ret_from, exact_ret_to, "ec_rwd", "ec_prev_ret_range")

        st.markdown(f"**{t('dep_weekdays')}:**")
        out_weekdays = st.multiselect(
            t("dep_weekdays"),
            options=WEEKDAYS_PL,
            format_func=lambda wd: WEEKDAY_PL_TO_EN.get(wd, wd) if st.session_state.get("lang", "EN") == "EN" else wd,
            key="ec_owd",
            label_visibility="collapsed",
        )
        st.markdown(f"**{t('ret_weekdays')}:**")
        ret_weekdays = st.multiselect(
            t("ret_weekdays"),
            options=WEEKDAYS_PL,
            format_func=lambda wd: WEEKDAY_PL_TO_EN.get(wd, wd) if st.session_state.get("lang", "EN") == "EN" else wd,
            key="ec_rwd",
            label_visibility="collapsed",
        )

    with ec4:
        st.markdown(f"**{t('mode_cost')}**")
        search_mode = st.radio(
            t("mode"), [t("mode_oneway"), t("mode_rt")], key="ec_mode",
        )
        exact_direct = st.checkbox(t("direct_only"), key="ec_dir")

        exact_dryrun = st.button(t("btn_dryrun"), key="ec_dr", use_container_width=True)
        exact_exec = st.button(t("btn_search"), key="ec_ex", use_container_width=True,
                                disabled=st.session_state.search_running, type="primary")
        exact_load_sql = st.button(t("btn_load_sql"), key="ec_load_sql", use_container_width=True)

    # Generate outbound dates
    if exact_origins and exact_dests:
        out_dates = _generate_dates_in_range(
            datetime.combine(exact_date_from, datetime.min.time()),
            datetime.combine(exact_date_to, datetime.min.time()),
            out_weekdays,
        )
    else:
        out_dates = []

    # Generate return dates from outbound + nights range, filtered by weekday and return bounds
    def _compute_return_dates(
        out_dates: list[str],
        nmin: int,
        nmax: int,
        ret_wd: list[str],
        ret_from_limit: str | None = None,
        ret_to_limit: str | None = None,
    ) -> list[str]:
        ret_set: set[str] = set()
        ret_indices = {WEEKDAY_INDEX_MAP[w] for w in ret_wd if w in WEEKDAY_INDEX_MAP}
        for od in out_dates:
            d = datetime.strptime(od, "%Y-%m-%d")
            for n in range(nmin, nmax + 1):
                rd = d + timedelta(days=n)
                rd_str = rd.strftime("%Y-%m-%d")
                if ret_from_limit and rd_str < ret_from_limit:
                    continue
                if ret_to_limit and rd_str > ret_to_limit:
                    continue
                if rd.weekday() in ret_indices:
                    ret_set.add(rd_str)
        return sorted(ret_set)

    ret_dates = _compute_return_dates(
        out_dates,
        int(exact_nmin),
        int(exact_nmax),
        ret_weekdays,
        ret_from_limit=str(exact_ret_from),
        ret_to_limit=str(exact_ret_to),
    ) if out_dates else []

    is_oneway = "One-Way" in search_mode or search_mode == t("mode_oneway")

    # Dry-run calculation
    if exact_dryrun:
        if not exact_origins or not exact_dests:
            st.error(t("select_airports_err"))
        elif not out_dates:
            st.error(t("no_out_dates"))
        else:
            origin_chunks = serpapi_client.chunk_airports(exact_origins, 6)
            dest_chunks = serpapi_client.chunk_airports(exact_dests, 6)
            n_airport_combos = len(origin_chunks) * len(dest_chunks)
            ret_indices = {WEEKDAY_INDEX_MAP[w] for w in ret_weekdays if w in WEEKDAY_INDEX_MAP}

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
                        if rd.weekday() in ret_indices:
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
                                if rd_dt.weekday() in ret_indices:
                                    rd = rd_dt.strftime("%Y-%m-%d")
                                    p = {"departure_id": dep_id, "arrival_id": arr_id,
                                         "outbound_date": od, "return_date": rd, "type": 1}
                                    if db.is_cache_valid(conn, db.compute_query_hash("serpapi_gf", p), cache_ttl):
                                        cached_count += 1
            conn.close()

            http_needed = total_q - cached_count

            if st.session_state.lang == "EN":
                st.info(
                    f"Airport chunks: {len(origin_chunks)}×{len(dest_chunks)} | "
                    f"Outbound dates: {len(out_dates)} | "
                    f"{'Return dates: ' + str(len(ret_dates)) if is_oneway else 'Date pairs: ' + str(total_q // max(n_airport_combos, 1))}\n\n"
                    f"**Total: {total_q} queries | Cache: {cached_count} | "
                    f"HTTP: {http_needed}**"
                )
            else:
                st.info(
                    f"Paczki lotnisk: {len(origin_chunks)}×{len(dest_chunks)} | "
                    f"Daty wylotu: {len(out_dates)} | "
                    f"{'Daty powrotu: ' + str(len(ret_dates)) if is_oneway else 'Par dat: ' + str(total_q // max(n_airport_combos, 1))}\n\n"
                    f"**Łącznie: {total_q} zapytań | Cache: {cached_count} | "
                    f"HTTP: {http_needed}**"
                )

            effective_max = min(user_max_calls, safety.HARD_MAX_CALLS_PER_SEARCH)
            if http_needed > effective_max:
                if st.session_state.lang == "EN":
                    st.error(
                        f"Selected range requires **{http_needed}** new HTTP requests "
                        f"(safety limit: {effective_max}). "
                        f"Narrow dates FROM–TO, pick specific weekdays (e.g. Fri/Sun only), "
                        f"or fetch in batches — cached queries cost 0 API calls next time!"
                    )
                else:
                    st.error(
                        f"Wybrany zakres wymaga **{http_needed}** nowych zapytań HTTP "
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

    # Load from SQLite (0 API)
    if exact_load_sql:
        if not exact_origins or not exact_dests:
            st.error(t("select_airports_err"))
        else:
            conn = db.get_connection()
            if is_oneway:
                matched = match_roundtrips(
                    conn,
                    origin_airports=exact_origins,
                    dest_airports=exact_dests,
                    min_nights=int(exact_nmin),
                    max_nights=int(exact_nmax),
                    allow_different_return_airport=allow_diff_return,
                    direct_only=exact_direct,
                    query_hashes_outbound=None,
                    query_hashes_inbound=None,
                    out_date_from=str(exact_date_from),
                    out_date_to=str(exact_date_to),
                    ret_date_from=str(exact_ret_from),
                    ret_date_to=str(exact_ret_to),
                    out_weekdays=out_weekdays,
                    ret_weekdays=ret_weekdays,
                    is_mock=st.session_state.mock_mode,
                )
                conn.close()
                st.session_state.exact_results = ("matched", matched)
                st.success(
                    f"Loaded from SQLite (0 API) - Matcher: {len(matched)} {t('combos')}"
                    if st.session_state.lang == "EN"
                    else f"Wczytano z bazy SQLite (0 API) - Matcher: {len(matched)} {t('combos')}"
                )
            else:
                loaded = db.query_flights_by_criteria(
                    conn,
                    origins=exact_origins,
                    dests=exact_dests,
                    direction="roundtrip",
                    date_from=str(exact_date_from),
                    date_to=str(exact_date_to),
                    is_mock=st.session_state.mock_mode,
                )
                conn.close()
                loaded = [
                    f for f in loaded
                    if f.get("orig_airport") in exact_origins
                    and f.get("dest_airport") in exact_dests
                    and (not f.get("flight_date") or (str(exact_date_from) <= str(f.get("flight_date")) <= str(exact_date_to)))
                ]
                loaded.sort(key=lambda x: x.get("price_eur", 9999))
                st.session_state.exact_results = ("rt_live" if not st.session_state.mock_mode else "kiwi", loaded)
                st.success(
                    f"Loaded {len(loaded)} {t('offers')} from SQLite (0 API)."
                    if st.session_state.lang == "EN"
                    else f"Wczytano {len(loaded)} {t('offers')} z bazy SQLite (0 API)."
                )

    # Execute
    if exact_exec:
        if st.session_state.search_running:
            st.error(t("search_in_progress"))
        elif not exact_origins or not exact_dests:
            st.error(t("select_airports_err"))
        elif not out_dates:
            st.error(t("no_out_dates"))
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
                            dest_airports=exact_dests,
                            min_nights=int(exact_nmin),
                            max_nights=int(exact_nmax),
                            allow_different_return_airport=allow_diff_return,
                            direct_only=exact_direct,
                            query_hashes_outbound=all_query_hashes_out,
                            query_hashes_inbound=all_query_hashes_in,
                            out_date_from=str(exact_date_from),
                            out_date_to=str(exact_date_to),
                            ret_date_from=str(exact_ret_from),
                            ret_date_to=str(exact_ret_to),
                            out_weekdays=out_weekdays,
                            ret_weekdays=ret_weekdays,
                            is_mock=True,
                        )
                        st.session_state.exact_results = ("matched", matched)
                        st.success(f"Matcher: {len(matched)} {t('combos')}")
                    else:
                        # RT mock
                        all_rt = []
                        for orig in exact_origins:
                            for dest in exact_dests:
                                if orig == dest:
                                    continue
                                for od in out_dates:
                                    res = generate_mock_kiwi_flights(
                                        origin_airport=orig,
                                        dest_airport=dest,
                                        date_from=od,
                                        date_to=od,
                                        return_from=str(exact_ret_from),
                                        return_to=str(exact_ret_to),
                                        nights_in_dst_from=int(exact_nmin),
                                        nights_in_dst_to=int(exact_nmax),
                                    )
                                    all_rt.extend(res)
                        all_rt = [
                            f for f in all_rt
                            if f.get("orig_airport") in exact_origins
                            and f.get("dest_airport") in exact_dests
                            and (not f.get("flight_date") or (str(exact_date_from) <= str(f.get("flight_date")) <= str(exact_date_to)))
                        ]
                        all_rt.sort(key=lambda x: x.get("price_eur", 9999))
                        st.session_state.exact_results = ("kiwi", all_rt)
                        st.success(f"{len(all_rt)} {t('offers')} RT")
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
                                        time.sleep(random.uniform(0.4, 1.1))
                                    except safety.APIError as e:
                                        st.warning(f"Out {dep_id}->{arr_id} {od}: {e}")
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
                                        time.sleep(random.uniform(0.4, 1.1))
                                    except safety.APIError as e:
                                        st.warning(f"In {arr_id}->{dep_id} {rd}: {e}")
                                        break

                        # Run matcher
                        matched = match_roundtrips(
                            conn,
                            origin_airports=exact_origins,
                            dest_airports=exact_dests,
                            min_nights=int(exact_nmin),
                            max_nights=int(exact_nmax),
                            allow_different_return_airport=allow_diff_return,
                            direct_only=exact_direct,
                            query_hashes_outbound=all_query_hashes_out,
                            query_hashes_inbound=all_query_hashes_in,
                            out_date_from=str(exact_date_from),
                            out_date_to=str(exact_date_to),
                            ret_date_from=str(exact_ret_from),
                            ret_date_to=str(exact_ret_to),
                            out_weekdays=out_weekdays,
                            ret_weekdays=ret_weekdays,
                            is_mock=False,
                        )
                        st.session_state.exact_results = ("matched", matched)
                        st.success(f"{http_sent} HTTP | Matcher: {len(matched)} {t('combos')}")

                    else:
                        # Round-Trip LIVE
                        all_rt_results: list[dict] = []
                        ret_indices = {WEEKDAY_INDEX_MAP[w] for w in ret_weekdays if w in WEEKDAY_INDEX_MAP}
                        for o_chunk in origin_chunks:
                            for d_chunk in dest_chunks:
                                dep_id = ",".join(o_chunk)
                                arr_id = ",".join(d_chunk)
                                for od in out_dates:
                                    d = datetime.strptime(od, "%Y-%m-%d")
                                    for n in range(int(exact_nmin), int(exact_nmax) + 1):
                                        rd_dt = d + timedelta(days=n)
                                        if rd_dt.weekday() not in ret_indices:
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
                                            time.sleep(random.uniform(0.4, 1.1))
                                        except safety.APIError as e:
                                            st.warning(f"RT {dep_id}->{arr_id} {od}/{rd}: {e}")
                                            break

                        all_rt_results = [
                            f for f in all_rt_results
                            if f.get("orig_airport") in exact_origins
                            and f.get("dest_airport") in exact_dests
                            and (not f.get("flight_date") or (str(exact_date_from) <= str(f.get("flight_date")) <= str(exact_date_to)))
                        ]
                        all_rt_results.sort(key=lambda x: x.get("price_eur", 9999))
                        st.session_state.exact_results = ("rt_live", all_rt_results)
                        st.success(f"{http_sent} HTTP | {len(all_rt_results)} {t('results')}")

                conn.close()
            finally:
                st.session_state.search_running = False

    # Display Exact results
    if st.session_state.exact_results:
        rtype, rdata = st.session_state.exact_results
        if rtype == "matched":
            df = _format_matched_results(rdata)
            if not df.empty:
                st.markdown(f"**{len(df)} {t('combos')}**")
                df = _apply_local_filters(df, "ec")
                st.dataframe(df, column_config=get_column_config(), use_container_width=True, hide_index=True)
            else:
                st.info(t("no_results"))
        elif rtype == "kiwi":
            df = _format_kiwi_results(rdata)
            if not df.empty:
                st.markdown(f"**{len(df)} {t('offers')} RT**")
                df = _apply_local_filters(df, "ec_rt")
                st.dataframe(df, column_config=get_column_config(), use_container_width=True, hide_index=True)
            else:
                st.info(t("no_results"))
        elif rtype == "rt_live":
            # Live RT results are raw flight dicts
            if rdata:
                records = []
                for f in rdata:
                    records.append({
                        "Total EUR": round(float(f.get("price_eur", 0)), 2),
                        "Outbound": f"{f.get('orig_airport', '')}→{f.get('dest_airport', '')}",
                        "Out Date": f"{f.get('flight_date', '')} {f.get('departure_time', '')}".strip(),
                        "Out Airline": f"{f.get('airline', '')} {f.get('flight_no', '')}".strip(),
                        "Return": f"{f.get('return_orig', '')}→{f.get('return_dest', '')}",
                        "Ret Date": f"{f.get('return_date', '')} {f.get('return_dep_time', '')}".strip(),
                        "Ret Airline": f"{f.get('return_airline', '')}".strip(),
                        "Stops": f.get("stops", 0),
                        "Source": "SerpApi",
                    })
                df = pd.DataFrame(records)
                st.markdown(f"**{len(df)} {t('results')} RT**")
                df = _apply_local_filters(df, "ec_rtl")
                st.dataframe(df, column_config=get_column_config(), use_container_width=True, hide_index=True)
            else:
                st.info(t("no_results"))


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    f"{t('footer_info')} | {CURRENCY} | "
    f"Mock: {'YES' if (st.session_state.lang == 'EN' and st.session_state.mock_mode) else ('TAK' if st.session_state.mock_mode else 'NO' if st.session_state.lang == 'EN' else 'NIE')} | "
    f"Cache: {cache_ttl}h | Limit: {safety.HARD_MAX_CALLS_PER_SEARCH}"
)

# ---------------------------------------------------------------------------
# Full SQLite Cache Viewer + Interactive SQL Console
# ---------------------------------------------------------------------------
with st.expander(t("sql_expander_title"), expanded=False):
    st.caption(t("sql_caption"))

    preset_queries = {
        t("preset_all_live"): (
            "SELECT id, provider, direction, orig_airport, dest_airport, flight_date, "
            "departure_time, arrival_time, airline, flight_no, price_eur, stops, raw_json "
            "FROM flights WHERE is_mock = 0 ORDER BY price_eur ASC"
        ),
        t("preset_direct_100"): (
            "SELECT provider, direction, orig_airport, dest_airport, flight_date, "
            "departure_time, airline, flight_no, price_eur, stops, raw_json "
            "FROM flights WHERE is_mock = 0 AND stops = 0 AND price_eur <= 100 "
            "ORDER BY price_eur ASC"
        ),
        t("preset_oneway_matcher"): (
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
        t("preset_price_stats"): (
            "SELECT orig_airport, dest_airport, direction, provider, COUNT(*) AS offers, "
            "ROUND(MIN(price_eur), 0) AS min_eur, ROUND(AVG(price_eur), 0) AS avg_eur, "
            "ROUND(MAX(price_eur), 0) AS max_eur "
            "FROM flights WHERE is_mock = 0 "
            "GROUP BY orig_airport, dest_airport, direction, provider ORDER BY min_eur ASC"
        ),
        t("preset_query_history"): (
            "SELECT query_hash, provider, result_count, fetched_at, is_mock, params_json "
            "FROM query_cache ORDER BY fetched_at DESC"
        ),
        t("preset_all_records"): (
            "SELECT id, provider, direction, orig_airport, dest_airport, flight_date, "
            "departure_time, airline, flight_no, price_eur, stops, is_mock, raw_json "
            "FROM flights ORDER BY price_eur ASC LIMIT 500"
        ),
    }

    if "custom_sql_query" not in st.session_state:
        st.session_state.custom_sql_query = list(preset_queries.values())[0]

    # Quick presets
    p_cols = st.columns(3)
    for idx, (label, q_str) in enumerate(preset_queries.items()):
        with p_cols[idx % 3]:
            if st.button(label, key=f"sql_preset_btn_{idx}", use_container_width=True):
                st.session_state.custom_sql_query = q_str
                st.session_state.sql_editor_area = q_str

    # SQL Text Area
    sql_input = st.text_area(
        t("sql_editor_label"),
        value=st.session_state.custom_sql_query,
        height=110,
        key="sql_editor_area",
    )

    clean_sql = sql_input.strip()
    first_word = clean_sql.split()[0].upper() if clean_sql else ""

    if first_word not in ("SELECT", "WITH", "PRAGMA"):
        st.error(
            "Dozwolone są wyłącznie zapytania odczytujące (SELECT, WITH, PRAGMA)."
            if st.session_state.lang == "PL"
            else "Only read queries (SELECT, WITH, PRAGMA) are allowed."
        )
    else:
        conn_sql = db.get_connection()
        try:
            df_sql = pd.read_sql_query(clean_sql, conn_sql)

            # Auto-extract return fields from raw_json if column present
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
                df_sql["nights"] = pd.to_numeric(
                    df_sql["raw_json"].apply(lambda r: _extract_raw_field(r, "nights")),
                    errors="coerce",
                )
                df_sql = df_sql.drop(columns=["raw_json"])
            elif "nights" in df_sql.columns:
                df_sql["nights"] = pd.to_numeric(df_sql["nights"], errors="coerce")

            if "booking_url" in df_sql.columns:
                df_sql = df_sql.drop(columns=["booking_url"])

            df_sql = _apply_column_value_extractor(df_sql, "sql_console")

            st.caption(f"{t('sql_rows_displayed')} **{len(df_sql)}**")
            st.dataframe(
                df_sql,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "price_eur": st.column_config.NumberColumn("Price EUR", format="%.2f €"),
                    "total_eur": st.column_config.NumberColumn("Total EUR", format="%.2f €"),
                    "out_eur": st.column_config.NumberColumn("Out EUR", format="%.2f €"),
                    "ret_eur": st.column_config.NumberColumn("Ret EUR", format="%.2f €"),
                    "min_eur": st.column_config.NumberColumn("Min EUR", format="%.2f €"),
                    "avg_eur": st.column_config.NumberColumn("Avg EUR", format="%.2f €"),
                    "max_eur": st.column_config.NumberColumn("Max EUR", format="%.2f €"),
                    "offers": st.column_config.NumberColumn("Offers", format="%d"),
                    "nights": st.column_config.NumberColumn("Nights", format="%d"),
                    "stops": st.column_config.NumberColumn("Stops", format="%d"),
                },
            )
        except Exception as e:
            st.error(f"SQL Error: {e}" if st.session_state.lang == "EN" else f"Błąd składni SQL: {e}")
        finally:
            conn_sql.close()
