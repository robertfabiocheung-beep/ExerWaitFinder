import math
import re
import time
import urllib.parse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from streamlit_js_eval import get_geolocation

EXER_URL = "https://exerurgentcare.com/exer-locations/"
HEADERS = {"User-Agent": "ExerWaitFinder/1.0"}

PHONE_RE = re.compile(r"(\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}|\d{10})")
WAIT_RE = re.compile(r"(\d+)\s+patients?\s+in\s+line", re.IGNORECASE)


FALLBACK_COORDS = {
    # Common SoCal cities
    "arcadia": (34.1397, -118.0353),
    "san gabriel": (34.0961, -118.1058),
    "alhambra": (34.0953, -118.1270),
    "pasadena": (34.1478, -118.1445),
    "covina": (34.0900, -117.8903),
    "west covina": (34.0686, -117.9390),
    "glendora": (34.1361, -117.8653),
    "azusa": (34.1336, -117.9076),
    "baldwin park": (34.0853, -117.9609),
    "monrovia": (34.1481, -118.0019),
    "duarte": (34.1395, -117.9773),
    "el monte": (34.0686, -118.0276),
    "temple city": (34.1072, -118.0578),
    "rosemead": (34.0806, -118.0728),
    "montebello": (34.0165, -118.1138),
    "whittier": (33.9792, -118.0328),
    "inglewood": (33.9617, -118.3531),
    "los angeles": (34.0522, -118.2437),
    "burbank": (34.1808, -118.3090),
    "glendale": (34.1425, -118.2551),
    "la canada": (34.1992, -118.1879),
    "la canada flintridge": (34.1992, -118.1879),
    "eagle rock": (34.1390, -118.2148),
    "beverly hills": (34.0736, -118.4004),
    "calabasas": (34.1367, -118.6615),
    "culver city": (34.0211, -118.3965),
    "santa monica": (34.0195, -118.4912),
    "torrance": (33.8358, -118.3406),
    "redondo beach": (33.8492, -118.3884),
    "manhattan beach": (33.8847, -118.4109),
    "long beach": (33.7701, -118.1937),
    "anaheim": (33.8366, -117.9143),
    "irvine": (33.6846, -117.8265),
    "beaumont": (33.9295, -116.9772),

    # Common ZIPs around you
    "91722": (34.0975, -117.9067),
    "91723": (34.0900, -117.8903),
    "91724": (34.0878, -117.8553),
    "91776": (34.0961, -118.1058),
    "91775": (34.1150, -118.0900),
    "91801": (34.0953, -118.1270),
    "91803": (34.0743, -118.1456),
    "91007": (34.1250, -118.0578),
    "91006": (34.1397, -118.0353),
}


def wait_to_number(text):
    text = text or ""

    if "no patients" in text.lower():
        return 0

    match = WAIT_RE.search(text)
    return int(match.group(1)) if match else 999


def miles_between(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 3958.8

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    h = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    return 2 * radius * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def clean_lines(text):
    return [line.strip() for line in text.split("\n") if line.strip()]


def looks_like_address(line):
    line_lower = line.lower()

    return (
        bool(re.search(r"\d+", line))
        and any(
            word in line_lower
            for word in [
                "street",
                "st",
                "avenue",
                "ave",
                "boulevard",
                "blvd",
                "road",
                "rd",
                "drive",
                "dr",
                "highway",
                "hwy",
                "pico",
                "pch",
                "lincoln",
                "sepulveda",
                "foothill",
                "campus",
                "western",
                "westlake",
                "silver spur",
                "the old road",
                "euclid",
                "college",
                "robertson",
                "agoura",
                "grand",
                "rowland",
            ]
        )
    )


@st.cache_data(ttl=86400)
def geocode_text(text):
    text = (text or "").strip()
    if not text:
        return None

    key = text.lower().strip()

    # First: local hardcoded fallback
    if key in FALLBACK_COORDS:
        return FALLBACK_COORDS[key]

    try:
        # Second: ZIP code lookup
        if re.fullmatch(r"\d{5}", key):
            response = requests.get(
                f"https://api.zippopotam.us/us/{key}",
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                place = data["places"][0]
                return float(place["latitude"]), float(place["longitude"])

        # Third: city lookup using Open-Meteo
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": text,
                "count": 1,
                "language": "en",
                "format": "json",
                "countryCode": "US",
            },
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()

            if "results" in data and data["results"]:
                result = data["results"][0]
                return float(result["latitude"]), float(result["longitude"])

        # Fourth: address lookup using Nominatim
        query = text
        if "california" not in query.lower() and ", ca" not in query.lower():
            query += ", California, USA"

        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers=HEADERS,
            timeout=15,
        )

        if response.status_code == 200:
            data = response.json()

            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])

    except Exception:
        return None

    return None


@st.cache_data(ttl=86400)
def geocode_clinic_address(address):
    address = (address or "").strip()
    if not address:
        return None

    for query in [f"Exer Urgent Care, {address}", address]:
        coords = geocode_text(query)

        if coords:
            return coords

        time.sleep(0.5)

    return None


@st.cache_data(ttl=300)
def get_clinics_raw():
    response = requests.get(EXER_URL, headers=HEADERS, timeout=25)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select(".location-card")

    clinics = {}

    for card in cards:
        lines = clean_lines(card.get_text("\n", strip=True))

        if len(lines) < 2:
            continue

        name = lines[0]

        address = None
        for line in lines[1:8]:
            if looks_like_address(line):
                address = line
                break

        if not address:
            continue

        wait = next(
            (line for line in lines if "patient" in line.lower() and "line" in line.lower()),
            "Unknown",
        )

        phone = next((line for line in lines if PHONE_RE.search(line)), "")
        xray = not any("no x-ray available" in line.lower() for line in lines)

        key = f"{name}|{address}"

        clinics[key] = {
            "name": name,
            "address": address,
            "wait": wait,
            "wait_num": wait_to_number(wait),
            "xray": xray,
            "phone": phone,
        }

    return list(clinics.values())


@st.cache_data(ttl=86400)
def get_clinics_with_coords():
    clinics = []

    for clinic in get_clinics_raw():
        coords = geocode_clinic_address(clinic["address"])

        if coords:
            clinic = clinic.copy()
            clinic["coords"] = coords
            clinics.append(clinic)

    return clinics


def maps_url(destination_coords, origin=None):
    params = {
        "api": "1",
        "destination": f"{destination_coords[0]},{destination_coords[1]}",
        "travelmode": "driving",
    }

    if origin:
        params["origin"] = f"{origin[0]},{origin[1]}"

    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)


st.set_page_config(page_title="Exer", page_icon="🏥", layout="centered")

st.title("Exer Wait Finder")
st.caption("Shortest wait first, then nearest distance. Directions use clinic GPS coordinates.")

xray_only = st.checkbox("X-ray only", value=True)
max_miles = st.slider("Max distance", 5, 100, 25)

st.subheader("Choose location source")

location_source = st.radio(
    "Location source",
    ["Use typed location", "Use GPS location"],
    index=0,
)

typed_location = st.text_input(
    "City, ZIP, or address",
    value="Arcadia",
    placeholder="Arcadia, 91722, Inglewood, Pasadena, or full address",
)

gps_location = get_geolocation()

gps_coords = None

if gps_location and "coords" in gps_location:
    gps_coords = (
        gps_location["coords"]["latitude"],
        gps_location["coords"]["longitude"],
    )
    st.success("GPS location received.")

elif gps_location and "error" in gps_location:
    st.warning("GPS was blocked or unavailable. You can still use typed location.")

if location_source == "Use GPS location":
    user_coords = gps_coords
else:
    user_coords = geocode_text(typed_location)

if not user_coords:
    st.error(
        "No usable location yet. Try a full ZIP code, city, or address. "
        "Example: Arcadia, 91722, Inglewood, Pasadena, or Covina."
    )

if st.button("Find best Exer", type="primary"):
    if not user_coords:
        st.stop()

    with st.spinner("Checking Exer locations... first run may take a minute."):
        clinics = get_clinics_with_coords()

    results = []

    for clinic in clinics:
        if xray_only and not clinic["xray"]:
            continue

        miles = miles_between(user_coords, clinic["coords"])

        if miles <= max_miles:
            clinic = clinic.copy()
            clinic["miles"] = miles
            results.append(clinic)

    results.sort(key=lambda x: (x["wait_num"], x["miles"]))

    if not results:
        st.warning(
            f"No Exer within a reasonable distance. Try increasing the distance above "
            f"{max_miles} miles or turning off X-ray only."
        )

    else:
        best = results[0]

        st.success(
            f"Best match: {best['name']} — {best['wait']} — {best['miles']:.1f} miles away"
        )

        for i, clinic in enumerate(results, start=1):
            st.subheader(f"{i}. {clinic['name']}")
            st.write(clinic["address"])

            if clinic["phone"]:
                st.write(f"Phone: {clinic['phone']}")

            st.write(f"Line: {clinic['wait']}")
            st.write(f"Distance: {clinic['miles']:.1f} miles")
            st.write(f"X-ray: {'YES' if clinic['xray'] else 'NO'}")

            st.markdown(
                f"[Open correct directions in Google Maps]({maps_url(clinic['coords'], user_coords)})"
            )

            st.divider()