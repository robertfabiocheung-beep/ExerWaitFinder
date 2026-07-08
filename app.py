import math
import re
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
    "orange": (33.7879, -117.8531),
    "irvine": (33.6846, -117.8265),
    "beaumont": (33.9295, -116.9772),

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

# Used only for distance sorting. Directions now use Exer's own Google Maps link.
CLINIC_COORDS = {
    "Anaheim – Euclid St": (33.7952, -117.9419),
    "Anaheim – State College Blvd": (33.8227, -117.8892),
    "Beaumont": (33.9364, -116.9444),
    "Beverly Hills": (34.0613, -118.3834),
    "Calabasas – Agoura Rd": (34.1441, -118.7087),
    "Covina": (34.0789, -117.8947),
    "Glendora": (34.1138, -117.8720),
    "Orange": (33.7824, -117.8674),

    "Pasadena – Allen Ave": (34.1502, -118.1135),
    "Pasadena – East Del Mar Blvd": (34.1413, -118.0846),
    "Pasadena – Lake Ave": (34.1359, -118.1321),
    "Pasadena – South Fair Oaks Ave": (34.1308, -118.1507),

    "La Canada Flintridge": (34.1995, -118.1880),
    "La Cañada Flintridge": (34.1995, -118.1880),
    "Eagle Rock": (34.1260, -118.2171),
    "Glendale": (34.1467, -118.2600),
    "Montebello": (34.0336, -118.1217),
    "Whittier": (33.9698, -118.0422),

    "Culver City": (34.0250, -118.3950),
    "Manhattan Beach": (33.8847, -118.4109),
    "Redondo Beach": (33.8492, -118.3884),
    "Torrance": (33.8358, -118.3406),
    "Santa Monica": (34.0195, -118.4912),
    "Westlake Village": (34.1458, -118.8056),
    "Northridge": (34.2381, -118.5301),
    "Sherman Oaks": (34.1511, -118.4492),
    "Stevenson Ranch": (34.3905, -118.5736),
    "Porter Ranch": (34.2822, -118.5614),
}


def normalize_name(name):
    return (
        name.strip()
        .replace("—", "–")
        .replace("-", "–")
        .replace("  ", " ")
    )


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
                "main",
                "fair oaks",
                "del mar",
                "lake",
                "allen",
            ]
        )
    )


@st.cache_data(ttl=86400)
def geocode_user_location(text):
    text = (text or "").strip()
    if not text:
        return None

    key = text.lower().strip()

    if key in FALLBACK_COORDS:
        return FALLBACK_COORDS[key]

    try:
        if re.fullmatch(r"\d{5}", key):
            response = requests.get(
                f"https://api.zippopotam.us/us/{key}",
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                place = data["places"][0]
                return float(place["latitude"]), float(place["longitude"])

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


def fallback_maps_url(address):
    query = urllib.parse.quote_plus(address)
    return f"https://www.google.com/maps/search/?api=1&query={query}"


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

        name = normalize_name(lines[0])

        address = None
        for line in lines[1:10]:
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

        # Manual correction: Orange should not be treated as X-ray available.
        if name.lower().strip() == "orange":
            xray = False

        coords = CLINIC_COORDS.get(name)

        if not coords:
            for known_name, known_coords in CLINIC_COORDS.items():
                if name.lower() == known_name.lower():
                    coords = known_coords
                    break

        if not coords:
            continue

        # IMPORTANT:
        # Use Exer's own Get directions link if present.
        # This avoids wrong destinations caused by our own generated Google Maps URLs.
        directions_url = None
        for a in card.find_all("a", href=True):
            label = a.get_text(" ", strip=True).lower()
            href = a["href"]
            if "directions" in label or "google.com/maps" in href:
                directions_url = href
                break

        if not directions_url:
            directions_url = fallback_maps_url(address)

        key = f"{name}|{address}"

        clinics[key] = {
            "name": name,
            "address": address,
            "wait": wait,
            "wait_num": wait_to_number(wait),
            "xray": xray,
            "phone": phone,
            "coords": coords,
            "directions_url": directions_url,
        }

    return list(clinics.values())


st.set_page_config(page_title="Exer", page_icon="🏥", layout="centered")

st.title("Exer Wait Finder")
st.caption("Shortest wait first, then nearest distance. Directions use Exer's own map links.")

xray_only = st.checkbox("Show only locations currently marked X-ray available", value=False)
st.caption(
    "X-ray availability may change by time of day or staffing. "
    "Call the clinic before going for X-ray."
)

max_miles = st.slider("Max distance", 5, 100, 25)

st.subheader("Choose location source")

location_source = st.radio(
    "Location source",
    ["Use typed location", "Use GPS location"],
    index=0,
)

typed_location = st.text_input(
    "City, ZIP, or address",
    value="Alhambra",
    placeholder="Alhambra, Arcadia, 91722, Inglewood, Pasadena, or full address",
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
    user_coords = geocode_user_location(typed_location)

if not user_coords:
    st.error(
        "No usable location yet. Try a full ZIP code, city, or address. "
        "Example: Alhambra, Arcadia, 91722, Inglewood, Pasadena, or Covina."
    )

if st.button("Find best Exer", type="primary"):
    if not user_coords:
        st.stop()

    with st.spinner("Checking Exer locations..."):
        clinics = get_clinics_raw()

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
                f"[Open directions in Google Maps]({clinic['directions_url']})"
            )

            st.divider()