import math
import re
import time
import urllib.parse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from streamlit_js_eval import get_geolocation

EXER_URL = "https://exerurgentcare.com/exer-locations/"
HEADERS = {"User-Agent": "ExerWaitFinder/1.0 robert personal Streamlit app"}

PHONE_RE = re.compile(r"(\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}|\d{10})")
WAIT_RE = re.compile(r"(\d+)\s+patients?\s+in\s+line", re.IGNORECASE)


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
            ]
        )
    )


@st.cache_data(ttl=86400)
def geocode_text(text):
    text = (text or "").strip()
    if not text:
        return None

    try:
        if re.fullmatch(r"\d{5}", text):
            response = requests.get(
                f"https://api.zippopotam.us/us/{text}",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                place = data["places"][0]
                return float(place["latitude"]), float(place["longitude"])

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

        if response.status_code != 200:
            return None

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

    # Try the plain street address first. If that fails, try with the brand name.
    for query in [address, f"Exer Urgent Care, {address}"]:
        coords = geocode_text(query)
        if coords:
            return coords

        # Be polite to the free geocoder on first cache build.
        time.sleep(1)

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
        for line in lines[1:6]:
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
    value="91722",
    placeholder="Inglewood, 91722, Covina, Pasadena, 123 Main St",
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
        "Example: 91722, Inglewood, Pasadena, or Covina."
    )

if st.button("Find best Exer", type="primary"):
    if not user_coords:
        st.stop()

    with st.spinner("Checking Exer locations... first run can take a minute while addresses are verified."):
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
            f"No Exer within a reasonable distance. Try increasing the distance above {max_miles} miles "
            "or turning off X-ray only."
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