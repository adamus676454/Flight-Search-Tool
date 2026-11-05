"""
config.py – Airport dictionaries, origin/destination groups, metro groups,
             EXPLORE_KGMID, and city names.
             All data hard-coded locally (zero external downloads).
"""

# ---------------------------------------------------------------------------
# Currency – hard-wired for the entire application
# ---------------------------------------------------------------------------
CURRENCY = "EUR"

# ---------------------------------------------------------------------------
# Cache settings (default; user can adjust in UI)
# ---------------------------------------------------------------------------
DEFAULT_CACHE_TTL_HOURS = 24

# ---------------------------------------------------------------------------
# Origin groups (Polish airports + nearby hubs)
# ---------------------------------------------------------------------------
ORIGIN_GROUPS = {
    "PL_SOUTH": ["KRK", "KTW"],
    "PL_SOUTH_EXT": ["KRK", "KTW", "RZE", "WRO"],
    "PL_CENTRAL": ["WAW", "WMI"],
    "PL_ALL": ["KRK", "KTW", "RZE", "WRO", "WAW", "WMI", "GDN", "POZ"],
    "NEARBY_HUBS": ["VIE", "BUD", "BTS", "OSR"],
}

# ---------------------------------------------------------------------------
# Metropolitan groups – airports serving the same metro area
# ---------------------------------------------------------------------------
METRO_GROUPS = {
    "MILAN": ["BGY", "MXP", "LIN"],
    "ROME": ["FCO", "CIA"],
    "VENICE": ["VCE", "TSF"],
    "BARCELONA": ["BCN", "GRO", "REU"],
    "ISTANBUL": ["SAW", "IST"],
    "TEL_AVIV_AREA": ["TLV"],
    "TENERIFE": ["TFS", "TFN"],
    "CYPRUS": ["PFO", "LCA"],
    "SICILY_EAST": ["CTA", "CIY"],
    "SICILY_WEST": ["PMO", "TPS"],
    "UAE_HUB": ["AUH", "DXB", "DWC", "SHJ"],
}

# ---------------------------------------------------------------------------
# Destination regions (Southern Europe, Balkans, Caucasus, Middle East,
# Maghreb) – only south-oriented directions
# ---------------------------------------------------------------------------
DESTINATION_REGIONS = {
    "ITALY_NORTH": ["BGY", "MXP", "LIN", "VCE", "TSF", "BLQ", "TRN", "VRN", "GOA", "TRS", "RMI"],
    "ITALY_CENTER_SOUTH": ["FCO", "CIA", "NAP", "BRI", "BDS", "PSR", "PSA", "PEG", "SUF", "QSR"],
    "ITALY_ISLANDS": ["CTA", "CIY", "PMO", "TPS", "CAG", "AHO", "OLB", "LMP"],
    "SPAIN_MAINLAND": ["BCN", "GRO", "REU", "MAD", "AGP", "ALC", "VLC", "SVQ", "LEI", "RMU", "CDT", "SDR", "ZAZ", "BIO", "OVD", "SCQ"],
    "SPAIN_BALEARICS": ["PMI", "IBZ", "MAH"],
    "SPAIN_CANARIES": ["TFS", "TFN", "LPA", "ACE", "FUE", "SPC"],
    "PORTUGAL": ["LIS", "OPO", "FAO", "FNC", "PDL"],
    "FRANCE_SOUTH": ["NCE", "MRS", "MPL", "TLS", "BZR", "PGF", "BIQ", "FSC", "BIA"],
    "GREECE_MAINLAND": ["ATH", "SKG", "PVK", "VOL", "KLX", "GPA"],
    "GREECE_ISLANDS": ["CHQ", "HER", "RHO", "CFU", "ZTH", "KGS", "JTR", "JMK", "EFL", "JSI", "MJT", "SMI"],
    "CYPRUS_MALTA": ["PFO", "LCA", "MLA"],
    "CROATIA_MONTENEGRO_SLOVENIA": ["ZAD", "SPU", "DBV", "PUY", "RJK", "ZAG", "TGD", "TIV", "LJU"],
    "ALBANIA_MACEDONIA_BOSNIA": ["TIA", "SKP", "OHD", "SJJ", "BNX", "TZL", "PRN"],
    "BULGARIA_ROMANIA_BLACK_SEA": ["SOF", "BOJ", "VAR", "PDV", "OTP", "CND"],
    "TURKEY": ["SAW", "IST", "AYT", "DLM", "BJV", "ADB", "ESB", "GZT", "TZX"],
    "CAUCASUS": ["KUT", "TBS", "BUS", "EVN", "GYD"],
    "MIDDLE_EAST_LEVANT": ["AMM", "AQJ", "TLV", "BEY"],
    "MIDDLE_EAST_GULF_EGYPT": ["AUH", "DXB", "DWC", "SHJ", "DOH", "KWI", "BAH", "MCT", "RUH", "JED", "DMM", "SLL", "HRG", "SSH", "SPX", "CAI", "RMF"],
    "MAGHREB_MOROCCO": ["RAK", "AGA", "FEZ", "TNG", "RBA", "NDR", "OUD", "ESU", "CMN", "TTU"],
    "MAGHREB_TUNISIA_ALGERIA": ["TUN", "MIR", "DJE", "NBE", "ALG", "ORN"],
}

# ---------------------------------------------------------------------------
# Google Travel Explore – Knowledge-Graph Machine IDs for countries/regions
# ---------------------------------------------------------------------------
EXPLORE_KGMID = {
    "Włochy": "/m/03rjj",
    "Hiszpania": "/m/06mkj",
    "Portugalia": "/m/05r4w",
    "Grecja": "/m/035qy",
    "Chorwacja": "/m/01pj7",
    "Albania": "/m/0jdx",
    "Czarnogóra": "/m/056vv",
    "Cypr": "/m/01str",
    "Malta": "/m/04v3q",
    "Bułgaria": "/m/015qh",
    "Turcja": "/m/01znc_",
    "Gruzja": "/m/0d0vqn",
    "Armenia": "/m/0jgx",
    "Azerbejdżan": "/m/0jhd",
    "Maroko": "/m/04wgh",
    "Tunezja": "/m/07fj_",
    "Jordania": "/m/03_y",
    "Izrael": "/m/03spz",
    "Egipt": "/m/02k54",
    "Zjednoczone Emiraty Arabskie": "/m/0j1z8",
    "Arabia Saudyjska": "/m/01z215",
    "Oman": "/m/05k4w",
    "Europa Południowa": "/m/02j9z",
}

# ---------------------------------------------------------------------------
# Human-readable city names for IATA codes
# ---------------------------------------------------------------------------
AIRPORT_CITY_NAMES = {
    # Poland
    "KRK": "Kraków",
    "KTW": "Katowice",
    "RZE": "Rzeszów",
    "WRO": "Wrocław",
    "WAW": "Warszawa Chopin",
    "WMI": "Warszawa Modlin",
    "GDN": "Gdańsk",
    "POZ": "Poznań",
    # Nearby hubs
    "VIE": "Wiedeń",
    "BUD": "Budapeszt",
    "BTS": "Bratysława",
    "OSR": "Ostrawa",
    # Italy North
    "BGY": "Mediolan Bergamo",
    "MXP": "Mediolan Malpensa",
    "LIN": "Mediolan Linate",
    "VCE": "Wenecja Marco Polo",
    "TSF": "Wenecja Treviso",
    "BLQ": "Bolonia",
    "TRN": "Turyn",
    "VRN": "Werona",
    "GOA": "Genua",
    "TRS": "Triest",
    "RMI": "Rimini",
    # Italy Center/South
    "FCO": "Rzym Fiumicino",
    "CIA": "Rzym Ciampino",
    "NAP": "Neapol",
    "BRI": "Bari",
    "BDS": "Brindisi",
    "PSR": "Pescara",
    "PSA": "Piza",
    "PEG": "Perugia",
    "SUF": "Lamezia Terme",
    "QSR": "Salerno",
    # Italy Islands
    "CTA": "Katania",
    "CIY": "Comiso",
    "PMO": "Palermo",
    "TPS": "Trapani",
    "CAG": "Cagliari",
    "AHO": "Alghero",
    "OLB": "Olbia",
    "LMP": "Lampedusa",
    # Spain Mainland
    "BCN": "Barcelona El Prat",
    "GRO": "Barcelona Girona",
    "REU": "Barcelona Reus",
    "MAD": "Madryt",
    "AGP": "Malaga",
    "ALC": "Alicante",
    "VLC": "Walencja",
    "SVQ": "Sewilla",
    "LEI": "Almeria",
    "RMU": "Murcia",
    "CDT": "Castellón",
    "SDR": "Santander",
    "ZAZ": "Saragossa",
    "BIO": "Bilbao",
    "OVD": "Oviedo/Asturia",
    "SCQ": "Santiago de Compostela",
    # Spain Balearics
    "PMI": "Palma de Mallorca",
    "IBZ": "Ibiza",
    "MAH": "Menorca",
    # Spain Canaries
    "TFS": "Teneryfa Południe",
    "TFN": "Teneryfa Północ",
    "LPA": "Gran Canaria",
    "ACE": "Lanzarote",
    "FUE": "Fuerteventura",
    "SPC": "La Palma",
    # Portugal
    "LIS": "Lizbona",
    "OPO": "Porto",
    "FAO": "Faro",
    "FNC": "Madera Funchal",
    "PDL": "Azory Ponta Delgada",
    # France South
    "NCE": "Nicea",
    "MRS": "Marsylia",
    "MPL": "Montpellier",
    "TLS": "Tuluza",
    "BZR": "Béziers",
    "PGF": "Perpignan",
    "BIQ": "Biarritz",
    "FSC": "Figari (Korsyka)",
    "BIA": "Bastia (Korsyka)",
    # Greece Mainland
    "ATH": "Ateny",
    "SKG": "Saloniki",
    "PVK": "Preveza/Lefkada",
    "VOL": "Wolos",
    "KLX": "Kalamata",
    "GPA": "Patras/Araxos",
    # Greece Islands
    "CHQ": "Chania (Kreta)",
    "HER": "Heraklion (Kreta)",
    "RHO": "Rodos",
    "CFU": "Korfu",
    "ZTH": "Zakynthos",
    "KGS": "Kos",
    "JTR": "Santorini",
    "JMK": "Mykonos",
    "EFL": "Kefalonia",
    "JSI": "Skiathos",
    "MJT": "Lesbos",
    "SMI": "Samos",
    # Cyprus & Malta
    "PFO": "Pafos",
    "LCA": "Larnaka",
    "MLA": "Malta",
    # Croatia, Montenegro, Slovenia
    "ZAD": "Zadar",
    "SPU": "Split",
    "DBV": "Dubrownik",
    "PUY": "Pula",
    "RJK": "Rijeka",
    "ZAG": "Zagrzeb",
    "TGD": "Podgorica",
    "TIV": "Tivat",
    "LJU": "Lublana",
    # Albania, North Macedonia, Bosnia, Kosovo
    "TIA": "Tirana",
    "SKP": "Skopje",
    "OHD": "Ohrid",
    "SJJ": "Sarajewo",
    "BNX": "Banja Luka",
    "TZL": "Tuzla",
    "PRN": "Prisztina",
    # Bulgaria, Romania, Black Sea
    "SOF": "Sofia",
    "BOJ": "Burgas",
    "VAR": "Warna",
    "PDV": "Płowdiw",
    "OTP": "Bukareszt",
    "CND": "Konstanca",
    # Turkey
    "SAW": "Stambuł Sabiha",
    "IST": "Stambuł",
    "AYT": "Antalya",
    "DLM": "Dalaman",
    "BJV": "Bodrum",
    "ADB": "Izmir",
    "ESB": "Ankara",
    "GZT": "Gaziantep",
    "TZX": "Trabzon",
    # Caucasus
    "KUT": "Kutaisi",
    "TBS": "Tbilisi",
    "BUS": "Batumi",
    "EVN": "Erywań",
    "GYD": "Baku",
    # Middle East Levant
    "AMM": "Amman",
    "AQJ": "Akaba",
    "TLV": "Tel Awiw",
    "BEY": "Bejrut",
    # Middle East Gulf & Egypt
    "AUH": "Abu Zabi",
    "DXB": "Dubaj",
    "DWC": "Dubaj Al Maktoum",
    "SHJ": "Szardża",
    "DOH": "Doha",
    "KWI": "Kuwejt",
    "BAH": "Bahrajn",
    "MCT": "Maskat",
    "RUH": "Rijad",
    "JED": "Dżudda",
    "DMM": "Dammam",
    "SLL": "Salalah",
    "HRG": "Hurghada",
    "SSH": "Sharm el-Sheikh",
    "SPX": "Sfinks (Kair)",
    "CAI": "Kair",
    "RMF": "Marsa Alam",
    # Maghreb Morocco
    "RAK": "Marrakesz",
    "AGA": "Agadir",
    "FEZ": "Fez",
    "TNG": "Tanger",
    "RBA": "Rabat",
    "NDR": "Nador",
    "OUD": "Oudja",
    "ESU": "Essaouira",
    "CMN": "Casablanca",
    "TTU": "Tetouan",
    # Maghreb Tunisia & Algeria
    "TUN": "Tunis",
    "MIR": "Monastir",
    "DJE": "Dżerba",
    "NBE": "Enfidha",
    "ALG": "Algier",
    "ORN": "Oran",
}


def get_metro_group(iata_code: str) -> str:
    """Return the metro-group name for an airport code.

    If the airport belongs to a defined METRO_GROUP (e.g. BGY → MILAN),
    return that group name.  Otherwise the airport IS its own group.
    """
    for group_name, codes in METRO_GROUPS.items():
        if iata_code in codes:
            return group_name
    return iata_code


def get_city_name(iata_code: str) -> str:
    """Return a human-readable city name for an IATA code, or the code itself."""
    return AIRPORT_CITY_NAMES.get(iata_code, iata_code)


def get_all_origin_airports() -> list[str]:
    """Return a sorted, deduplicated list of every origin airport code."""
    all_codes: set[str] = set()
    for codes in ORIGIN_GROUPS.values():
        all_codes.update(codes)
    return sorted(all_codes)


def get_all_destination_airports() -> list[str]:
    """Return a sorted, deduplicated list of every destination airport code."""
    all_codes: set[str] = set()
    for codes in DESTINATION_REGIONS.values():
        all_codes.update(codes)
    return sorted(all_codes)
