from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Chess Title Players", layout="wide")

# ---------------------------------------------------------------------------
# PATHS / DATABASE SETUP
# ---------------------------------------------------------------------------

# Always find files next to this one, no matter where Streamlit is launched
HERE = Path(__file__).parent
DB_PATH = str(HERE / "chess_ratings.db")
GEOJSON_PATH = str(HERE / "geoBoundaries-GBR-ADM1_simplified.geojson")
SOURCE_TABLE = "chess_ratings"

if not Path(DB_PATH).exists():
    st.error(f"Database not found at {DB_PATH}")
    st.stop()


@st.cache_data
def load_lists():
    """Which (year, rating_type) lists exist in the table, with player counts."""
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            f"SELECT year, rating_type, COUNT(*) FROM {SOURCE_TABLE} "
            "GROUP BY year, rating_type ORDER BY year DESC, rating_type"
        ).fetchall()
    finally:
        conn.close()


lists = load_lists()
if not lists:
    st.error("The table is empty.")
    st.stop()

# Sidebar: choose which rating list to analyse
years = list(dict.fromkeys(row[0] for row in lists))
year = st.sidebar.selectbox("Rating list year", years)
types = [row[1] for row in lists if row[0] == year]
default_idx = next((i for i, t in enumerate(types) if "stand" in str(t).lower()), 0)
rating_type = st.sidebar.selectbox("Rating type", types, index=default_idx)
LIST_KEY = (str(year), str(rating_type))  # keeps Streamlit's cache correct per list


def _lit(value) -> str:
    """Escape a value for use inside a SQL string literal."""
    return str(value).replace("'", "''")


def make_ratings_view(conn: sqlite3.Connection) -> None:
    """Create a temp view called 'ratings' using the column names the queries expect."""
    conn.execute(f"""
        CREATE TEMP VIEW ratings AS
        SELECT player_id    AS "ID Number",
               name         AS Name,
               federation   AS Fed,
               sex          AS Sex,
               title        AS Tit,
               women_title  AS WTit,
               other_title  AS OTit,
               foa          AS FOA,
               rating       AS NOV22,
               games        AS Gms,
               k_factor     AS K,
               birthday     AS "B-day",
               flag         AS Flag
        FROM {SOURCE_TABLE}
        WHERE CAST(year AS TEXT) = '{_lit(LIST_KEY[0])}'
          AND CAST(rating_type AS TEXT) = '{_lit(LIST_KEY[1])}'
    """)


# ---------------------------------------------------------------------------
# COUNTRY QUERIES
# FED_FILTER is swapped for "Fed IN (?, ?, ...)" so one country or several
# can be passed in as a list.
# ---------------------------------------------------------------------------

COUNTRY_SUMMARY = """
    SELECT COUNT(*) AS players,
           SUM(CASE WHEN CAST(NOV22 AS INTEGER) > 0 THEN 1 ELSE 0 END) AS rated,
           SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
           SUM(CASE WHEN TRIM(Tit) = 'GM' THEN 1 ELSE 0 END) AS gms,
           SUM(CASE WHEN TRIM(Tit) = 'GM' AND Sex = 'F' THEN 1 ELSE 0 END) AS women_gms,
           ROUND(AVG(CASE WHEN CAST(NOV22 AS INTEGER) > 0
                          THEN CAST(NOV22 AS INTEGER) END), 0) AS avg_rating
    FROM ratings
    WHERE FED_FILTER
"""

COUNTRY_TITLES = """
    SELECT TRIM(Tit) AS title, Sex, COUNT(*) AS players
    FROM ratings
    WHERE FED_FILTER
      AND Tit IS NOT NULL AND TRIM(Tit) <> ''
    GROUP BY TRIM(Tit), Sex
"""

COUNTRY_TOP = """
    SELECT Name, Sex, TRIM(Tit) AS Tit,
           CAST(NOV22 AS INTEGER) AS rating,
           2022 - CAST("B-day" AS INTEGER) AS age
    FROM ratings
    WHERE FED_FILTER
      AND CAST(NOV22 AS INTEGER) > 0
      EXTRA_FILTER
    ORDER BY rating DESC
    LIMIT 10
"""


@st.cache_data
def _run_cached(sql: str, params: tuple, list_key: tuple) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        make_ratings_view(conn)
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _run_cached(sql, params, LIST_KEY)


def country_query(template: str, feds: list[str], extra_filter: str = "") -> pd.DataFrame:
    placeholders = ",".join("?" for _ in feds)
    sql = template.replace("FED_FILTER", f"Fed IN ({placeholders})")
    sql = sql.replace("EXTRA_FILTER", extra_filter)
    return run_query(sql, tuple(feds))


def get_fed_codes(fide_code: str) -> list[str]:
    """Map the selected map/dropdown code to the FIDE federation codes to query.

    England, Scotland and Wales are separate shapes on the map (each with its
    own FIDE code), so every selection maps to exactly one federation.
    """
    return [fide_code]


# ---------------------------------------------------------------------------
# MAP PROCESSING
# ---------------------------------------------------------------------------

countries = {
    "AFG": {"name": "Afghanistan", "iso": "AFG"},
    "AHO": {"name": "Netherlands Antilles", "iso": None},  # dissolved 2010
    "ALB": {"name": "Albania", "iso": "ALB"},
    "ALG": {"name": "Algeria", "iso": "DZA"},
    "AND": {"name": "Andorra", "iso": "AND"},
    "ANG": {"name": "Angola", "iso": "AGO"},
    "ANT": {"name": "Antigua and Barbuda", "iso": "ATG"},
    "ARG": {"name": "Argentina", "iso": "ARG"},
    "ARM": {"name": "Armenia", "iso": "ARM"},
    "ARU": {"name": "Aruba", "iso": "ABW"},
    "AUS": {"name": "Australia", "iso": "AUS"},
    "AUT": {"name": "Austria", "iso": "AUT"},
    "AZE": {"name": "Azerbaijan", "iso": "AZE"},
    "BAH": {"name": "Bahamas", "iso": "BHS"},
    "BAN": {"name": "Bangladesh", "iso": "BGD"},
    "BAR": {"name": "Barbados", "iso": "BRB"},
    "BDI": {"name": "Burundi", "iso": "BDI"},
    "BEL": {"name": "Belgium", "iso": "BEL"},
    "BER": {"name": "Bermuda", "iso": "BMU"},
    "BHU": {"name": "Bhutan", "iso": "BTN"},
    "BIH": {"name": "Bosnia and Herzegovina", "iso": "BIH"},
    "BLR": {"name": "Belarus", "iso": "BLR"},
    "BOL": {"name": "Bolivia", "iso": "BOL"},
    "BOT": {"name": "Botswana", "iso": "BWA"},
    "BRA": {"name": "Brazil", "iso": "BRA"},
    "BRN": {"name": "Bahrain", "iso": "BHR"},
    "BRU": {"name": "Brunei", "iso": "BRN"},
    "BUL": {"name": "Bulgaria", "iso": "BGR"},
    "CAF": {"name": "Central African Republic", "iso": "CAF"},
    "CAM": {"name": "Cambodia", "iso": "KHM"},
    "CAN": {"name": "Canada", "iso": "CAN"},
    "CAY": {"name": "Cayman Islands", "iso": "CYM"},
    "CGO": {"name": "Congo", "iso": "COG"},
    "CHA": {"name": "Chad", "iso": "TCD"},
    "CHI": {"name": "Chile", "iso": "CHL"},
    "CHN": {"name": "China", "iso": "CHN"},
    "CIV": {"name": "Côte d'Ivoire", "iso": "CIV"},
    "CMR": {"name": "Cameroon", "iso": "CMR"},
    "COD": {"name": "DR Congo", "iso": "COD"},
    "COL": {"name": "Colombia", "iso": "COL"},
    "CPV": {"name": "Cape Verde", "iso": "CPV"},
    "CRC": {"name": "Costa Rica", "iso": "CRI"},
    "CRO": {"name": "Croatia", "iso": "HRV"},
    "CUB": {"name": "Cuba", "iso": "CUB"},
    "CUR": {"name": "Curaçao", "iso": "CUW"},
    "CYP": {"name": "Cyprus", "iso": "CYP"},
    "CZE": {"name": "Czech Republic", "iso": "CZE"},
    "DEN": {"name": "Denmark", "iso": "DNK"},
    "DJI": {"name": "Djibouti", "iso": "DJI"},
    "DMA": {"name": "Dominica", "iso": "DMA"},
    "DOM": {"name": "Dominican Republic", "iso": "DOM"},
    "ECU": {"name": "Ecuador", "iso": "ECU"},
    "EGY": {"name": "Egypt", "iso": "EGY"},
    "ENG": {"name": "England", "iso": "GBR"},  # no ISO code of its own
    "ERI": {"name": "Eritrea", "iso": "ERI"},
    "ESA": {"name": "El Salvador", "iso": "SLV"},
    "ESP": {"name": "Spain", "iso": "ESP"},
    "EST": {"name": "Estonia", "iso": "EST"},
    "ETH": {"name": "Ethiopia", "iso": "ETH"},
    "FAI": {"name": "Faroe Islands", "iso": "FRO"},
    "FID": {"name": "FIDE (no federation)", "iso": None},
    "FIJ": {"name": "Fiji", "iso": "FJI"},
    "FIN": {"name": "Finland", "iso": "FIN"},
    "FRA": {"name": "France", "iso": "FRA"},
    "GAB": {"name": "Gabon", "iso": "GAB"},
    "GAM": {"name": "Gambia", "iso": "GMB"},
    "GCI": {"name": "Guernsey", "iso": "GGY"},
    "GEO": {"name": "Georgia", "iso": "GEO"},
    "GEQ": {"name": "Equatorial Guinea", "iso": "GNQ"},
    "GER": {"name": "Germany", "iso": "DEU"},
    "GHA": {"name": "Ghana", "iso": "GHA"},
    "GRE": {"name": "Greece", "iso": "GRC"},
    "GRL": {"name": "Greenland", "iso": "GRL"},
    "GUA": {"name": "Guatemala", "iso": "GTM"},
    "GUI": {"name": "Guinea", "iso": "GIN"},
    "GUM": {"name": "Guam", "iso": "GUM"},
    "GUY": {"name": "Guyana", "iso": "GUY"},
    "HAI": {"name": "Haiti", "iso": "HTI"},
    "HKG": {"name": "Hong Kong", "iso": "HKG"},
    "HON": {"name": "Honduras", "iso": "HND"},
    "HUN": {"name": "Hungary", "iso": "HUN"},
    "INA": {"name": "Indonesia", "iso": "IDN"},
    "IND": {"name": "India", "iso": "IND"},
    "IOM": {"name": "Isle of Man", "iso": "IMN"},
    "IRI": {"name": "Iran", "iso": "IRN"},
    "IRL": {"name": "Ireland", "iso": "IRL"},
    "IRQ": {"name": "Iraq", "iso": "IRQ"},
    "ISL": {"name": "Iceland", "iso": "ISL"},
    "ISR": {"name": "Israel", "iso": "ISR"},
    "ISV": {"name": "US Virgin Islands", "iso": "VIR"},
    "ITA": {"name": "Italy", "iso": "ITA"},
    "IVB": {"name": "British Virgin Islands", "iso": "VGB"},
    "JAM": {"name": "Jamaica", "iso": "JAM"},
    "JCI": {"name": "Jersey", "iso": "JEY"},
    "JOR": {"name": "Jordan", "iso": "JOR"},
    "JPN": {"name": "Japan", "iso": "JPN"},
    "KAZ": {"name": "Kazakhstan", "iso": "KAZ"},
    "KEN": {"name": "Kenya", "iso": "KEN"},
    "KGZ": {"name": "Kyrgyzstan", "iso": "KGZ"},
    "KOR": {"name": "South Korea", "iso": "KOR"},
    "KOS": {"name": "Kosovo", "iso": "XKX"},  # user-assigned code, see notes
    "KSA": {"name": "Saudi Arabia", "iso": "SAU"},
    "KUW": {"name": "Kuwait", "iso": "KWT"},
    "LAO": {"name": "Laos", "iso": "LAO"},
    "LAT": {"name": "Latvia", "iso": "LVA"},
    "LBA": {"name": "Libya", "iso": "LBY"},
    "LBN": {"name": "Lebanon", "iso": "LBN"},
    "LBR": {"name": "Liberia", "iso": "LBR"},
    "LCA": {"name": "Saint Lucia", "iso": "LCA"},
    "LES": {"name": "Lesotho", "iso": "LSO"},
    "LIE": {"name": "Liechtenstein", "iso": "LIE"},
    "LTU": {"name": "Lithuania", "iso": "LTU"},
    "LUX": {"name": "Luxembourg", "iso": "LUX"},
    "MAC": {"name": "Macau", "iso": "MAC"},
    "MAD": {"name": "Madagascar", "iso": "MDG"},
    "MAR": {"name": "Morocco", "iso": "MAR"},
    "MAS": {"name": "Malaysia", "iso": "MYS"},
    "MAW": {"name": "Malawi", "iso": "MWI"},
    "MDA": {"name": "Moldova", "iso": "MDA"},
    "MDV": {"name": "Maldives", "iso": "MDV"},
    "MEX": {"name": "Mexico", "iso": "MEX"},
    "MGL": {"name": "Mongolia", "iso": "MNG"},
    "MKD": {"name": "North Macedonia", "iso": "MKD"},
    "MLI": {"name": "Mali", "iso": "MLI"},
    "MLT": {"name": "Malta", "iso": "MLT"},
    "MNC": {"name": "Monaco", "iso": "MCO"},
    "MNE": {"name": "Montenegro", "iso": "MNE"},
    "MOZ": {"name": "Mozambique", "iso": "MOZ"},
    "MRI": {"name": "Mauritius", "iso": "MUS"},
    "MTN": {"name": "Mauritania", "iso": "MRT"},
    "MYA": {"name": "Myanmar", "iso": "MMR"},
    "NAM": {"name": "Namibia", "iso": "NAM"},
    "NCA": {"name": "Nicaragua", "iso": "NIC"},
    "NCL": {"name": "New Caledonia", "iso": "NCL"},
    "NED": {"name": "Netherlands", "iso": "NLD"},
    "NEP": {"name": "Nepal", "iso": "NPL"},
    "NGR": {"name": "Nigeria", "iso": "NGA"},
    "NIG": {"name": "Niger", "iso": "NER"},
    "NON": {"name": "No federation", "iso": None},
    "NOR": {"name": "Norway", "iso": "NOR"},
    "NRU": {"name": "Nauru", "iso": "NRU"},
    "NZL": {"name": "New Zealand", "iso": "NZL"},
    "OMA": {"name": "Oman", "iso": "OMN"},
    "PAK": {"name": "Pakistan", "iso": "PAK"},
    "PAN": {"name": "Panama", "iso": "PAN"},
    "PAR": {"name": "Paraguay", "iso": "PRY"},
    "PER": {"name": "Peru", "iso": "PER"},
    "PHI": {"name": "Philippines", "iso": "PHL"},
    "PLE": {"name": "Palestine", "iso": "PSE"},
    "PLW": {"name": "Palau", "iso": "PLW"},
    "PNG": {"name": "Papua New Guinea", "iso": "PNG"},
    "POL": {"name": "Poland", "iso": "POL"},
    "POR": {"name": "Portugal", "iso": "PRT"},
    "PUR": {"name": "Puerto Rico", "iso": "PRI"},
    "QAT": {"name": "Qatar", "iso": "QAT"},
    "ROU": {"name": "Romania", "iso": "ROU"},
    "RSA": {"name": "South Africa", "iso": "ZAF"},
    "RUS": {"name": "Russia", "iso": "RUS"},
    "RWA": {"name": "Rwanda", "iso": "RWA"},
    "SCO": {"name": "Scotland", "iso": "GBR"},  # no ISO code of its own
    "SEN": {"name": "Senegal", "iso": "SEN"},
    "SEY": {"name": "Seychelles", "iso": "SYC"},
    "SGP": {"name": "Singapore", "iso": "SGP"},
    "SKN": {"name": "Saint Kitts and Nevis", "iso": "KNA"},
    "SLE": {"name": "Sierra Leone", "iso": "SLE"},
    "SLO": {"name": "Slovenia", "iso": "SVN"},
    "SMR": {"name": "San Marino", "iso": "SMR"},
    "SOM": {"name": "Somalia", "iso": "SOM"},
    "SRB": {"name": "Serbia", "iso": "SRB"},
    "SRI": {"name": "Sri Lanka", "iso": "LKA"},
    "SSD": {"name": "South Sudan", "iso": "SSD"},
    "STP": {"name": "São Tomé and Príncipe", "iso": "STP"},
    "SUD": {"name": "Sudan", "iso": "SDN"},
    "SUI": {"name": "Switzerland", "iso": "CHE"},
    "SUR": {"name": "Suriname", "iso": "SUR"},
    "SVK": {"name": "Slovakia", "iso": "SVK"},
    "SWE": {"name": "Sweden", "iso": "SWE"},
    "SWZ": {"name": "Eswatini", "iso": "SWZ"},
    "SYR": {"name": "Syria", "iso": "SYR"},
    "TAN": {"name": "Tanzania", "iso": "TZA"},
    "TGA": {"name": "Tonga", "iso": "TON"},
    "THA": {"name": "Thailand", "iso": "THA"},
    "TJK": {"name": "Tajikistan", "iso": "TJK"},
    "TKM": {"name": "Turkmenistan", "iso": "TKM"},
    "TLS": {"name": "Timor-Leste", "iso": "TLS"},
    "TOG": {"name": "Togo", "iso": "TGO"},
    "TPE": {"name": "Chinese Taipei", "iso": "TWN"},
    "TTO": {"name": "Trinidad and Tobago", "iso": "TTO"},
    "TUN": {"name": "Tunisia", "iso": "TUN"},
    "TUR": {"name": "Turkey", "iso": "TUR"},
    "UAE": {"name": "United Arab Emirates", "iso": "ARE"},
    "UGA": {"name": "Uganda", "iso": "UGA"},
    "UKR": {"name": "Ukraine", "iso": "UKR"},
    "URU": {"name": "Uruguay", "iso": "URY"},
    "USA": {"name": "United States", "iso": "USA"},
    "UZB": {"name": "Uzbekistan", "iso": "UZB"},
    "VAN": {"name": "Vanuatu", "iso": "VUT"},
    "VEN": {"name": "Venezuela", "iso": "VEN"},
    "VIE": {"name": "Vietnam", "iso": "VNM"},
    "VIN": {"name": "Saint Vincent and the Grenadines", "iso": "VCT"},
    "WLS": {"name": "Wales", "iso": "GBR"},  # no ISO code of its own
    "YEM": {"name": "Yemen", "iso": "YEM"},
    "ZAM": {"name": "Zambia", "iso": "ZMB"},
    "ZIM": {"name": "Zimbabwe", "iso": "ZWE"},
}

BASE_COLOR = "#9ecae1"
FLAT_SCALE = [[0, BASE_COLOR], [1, BASE_COLOR]]

# GeoJSON shapeName -> FIDE code 
UK_NATIONS = [
    ("England", "ENG"),
    ("Scotland", "SCO"),
    ("Wales", "WLS"),
]

if "fide_code" not in st.session_state:
    st.session_state.fide_code = "USA"


def _ring_area(ring):
    # Signed area via the shoelace formula: > 0 means counter-clockwise
    return sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        for i in range(len(ring) - 1)
    ) / 2


def _rewind_polygon(rings):
    # Plotly/d3 wants the outer ring clockwise and any holes counter-clockwise
    fixed = []
    for i, ring in enumerate(rings):
        is_ccw = _ring_area(ring) > 0
        want_ccw = i > 0  # holes CCW, outer ring CW
        fixed.append(ring if is_ccw == want_ccw else ring[::-1])
    return fixed


def rewind_geojson(geojson):
    for feature in geojson["features"]:
        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            geom["coordinates"] = _rewind_polygon(geom["coordinates"])
        elif geom["type"] == "MultiPolygon":
            geom["coordinates"] = [_rewind_polygon(p) for p in geom["coordinates"]]
    return geojson


@st.cache_data
def build_figure(values=None, colorscale="YlOrRd", colorbar_title="Value",
                 show_colorbar=True):
    """values: {FIDE code: number}. Countries missing from it are drawn gray."""
    values = values or {}

    with open(GEOJSON_PATH, encoding="utf-8") as f:
        uk_geojson = rewind_geojson(json.load(f))

    selected = dict(marker=dict(opacity=1))
    unselected = dict(marker=dict(opacity=0.35))
    gray = [[0, "#d9d9d9"], [1, "#d9d9d9"]]

    # Two layers: world countries by ISO code, UK nations by GeoJSON name.
    # Each layer is (location ids, display names, FIDE codes, extra kwargs)
    world = [(c, i) for c, i in countries.items() if i["iso"] not in (None, "GBR")]
    layers = [
        (
            [i["iso"] for _, i in world],
            [i["name"] for _, i in world],
            [c for c, _ in world],
            {},
        ),
        (
            [name for name, _ in UK_NATIONS],
            [name for name, _ in UK_NATIONS],
            [code for _, code in UK_NATIONS],
            dict(geojson=uk_geojson, featureidkey="properties.shapeName"),
        ),
    ]

    fig = go.Figure()
    for locs, names, codes, extra in layers:
        # Split into countries with a value (heat trace) and without (gray trace)
        has = [i for i, c in enumerate(codes) if c in values]
        no = [i for i in range(len(codes)) if i not in has]

        def pick(seq, idx):
            return [seq[i] for i in idx]

        if no:
            fig.add_trace(go.Choropleth(
                locations=pick(locs, no),
                z=[1] * len(no),
                text=pick(names, no),
                customdata=[[codes[i]] for i in no],
                hovertemplate="%{text}<br>No data<extra></extra>",
                colorscale=gray,
                showscale=False,
                selected=selected,
                unselected=unselected,
                **extra,
            ))
        if has:
            fig.add_trace(go.Choropleth(
                locations=pick(locs, has),
                z=[values[codes[i]] for i in has],
                text=pick(names, has),
                customdata=[[codes[i]] for i in has],
                hovertemplate="%{text}<br>" + colorbar_title + ": %{z}<extra></extra>",
                coloraxis="coloraxis",  # shared scale across both layers
                selected=selected,
                unselected=unselected,
                **extra,
            ))

    fig.update_geos(projection_type="cylindrical stereographic", uirevision="keep")
    fig.update_layout(
        coloraxis=dict(
            colorscale=colorscale,
            colorbar=dict(title=colorbar_title),
            showscale=show_colorbar,
        ),
        uirevision="keep",
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return fig


def handle_map_click():
    # Runs before the script reruns, so it can safely update the selectbox's state
    points = st.session_state.country_map["selection"]["points"]
    if points:
        clicked = points[0]["customdata"][0]
        st.session_state.fide_code = clicked


# ---------------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------------

st.title("Chess Title Players")


# Flat base color for every country that can be clicked; pass real numbers here
# instead (e.g. {"USA": 123, ...}) to turn the map into a heat map.
flat_values = {c: 1 for c, i in countries.items() if i["iso"] is not None}

st.plotly_chart(
    build_figure(
        flat_values,
        colorscale=FLAT_SCALE,
        colorbar_title="Federation",
        show_colorbar=False,
    ),
    key="country_map",
    on_select=handle_map_click,
    selection_mode="points",
)

st.selectbox(
    "Or pick from a list",
    options=sorted(countries, key=lambda c: countries[c]["name"]),
    format_func=lambda code: countries[code]["name"],
    key="fide_code",
)

fide_code = st.session_state.fide_code
feds = get_fed_codes(fide_code)
st.subheader(countries[fide_code]["name"])

summary = country_query(COUNTRY_SUMMARY, feds).iloc[0]

if summary["players"] == 0:
    st.info("No players registered for this federation in the dataset.")
else:
    if summary["players"] < 50:
        st.caption(
            f"Only {int(summary['players'])} players here, so the numbers "
            "below are small. Read them with care."
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Players", f"{int(summary['players']):,}")
    c2.metric("Grandmasters", int(summary["gms"]))
    c3.metric(
        "Avg rating",
        "n/a" if pd.isna(summary["avg_rating"]) else int(summary["avg_rating"]),
    )

    titles = country_query(COUNTRY_TITLES, feds)
    if not titles.empty:
        st.plotly_chart(
            px.bar(titles, x="title", y="players", color="Sex",
                   barmode="group", title="Titled players by sex"),
            key="chart_titles",
        )

    left, right = st.columns(2)
    with left:
        st.markdown("**Top 10 overall**")
        st.dataframe(country_query(COUNTRY_TOP, feds), hide_index=True)
    with right:
        st.markdown("**Top 10 women**")
        st.dataframe(
            country_query(COUNTRY_TOP, feds, extra_filter="AND Sex = 'F'"),
            hide_index=True,
        )