import math
import re
import urllib.parse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from streamlit_js_eval import get_geolocation

URL = "https://exerurgentcare.com/exer-locations/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

KNOWN_LOCATIONS = {
    "san gabriel": (34.0961, -118.1058),
    "covina": (34.0900, -117.8903),
    "pasadena": (34.1478, -118.1445),
    "glendora": (34.1361, -117.8653),
    "arcadia": (34.1397, -118.0353),
    "alhambra": (34.0953, -118.1270),
    "montebello": (34.0165, -118.1138),
    "la canada": (34.1992, -118.1879),
    "la canada flintridge": (34.1992, -118.1879),
    "eagle rock": (34.1390, -118.2148),
    "glendale": (34.1425, -118.2551),
    "whittier": (33.9792, -118.0328),
    "west covina": (34.0686, -117.9390),
    "91776": (34.0961, -118.1058),
    "91775": (34.1150, -118.0900),
    "91723": (34.0900, -117.8903),
    "91724": (34.0878, -117.8553),
}

CLINIC_COORDS = {
    "Covina": (34.0789, -117.8947),
    "Glendora": (34.1138, -117.8720),
    "Pasadena – Allen Ave": (34.1502, -118.1135),
    "Pasadena – East Del Mar Blvd": (34.1413, -118.0846),
    "Pasadena – Lake Ave": (34.1359, -118.1321),
    "Pasadena – South Fair Oaks Ave": (34.1308, -118.1507),
    "La Canada Flintridge": (34.1995, -118.1880),
    "Montebello": (34.0336, -118.1217),
    "Eagle Rock": (34.1260, -118.2171),
    "Glendale": (34.1467, -118.2600),
    "Whittier": (33.9698, -118.0422),
}

def wait_to_number(text):
    text = text or ""
    if "no patients" in text.lower():
        return 0
    match = re.search(r"(\d+)", text)
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

def get_known_location(text):
    key = text.strip().lower()
    return KNOWN_LOCATIONS.get(key)

def maps_url(destination, origin=None):
    params = {"api": "1", "destination": destination}
    if origin:
        params["origin"] = f"{origin[0]},{origin[1]}"
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)

@st.cache_data(ttl=300)
def get_clinics():
    html = requests.get(URL, headers=HEADERS, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".location-card")

    clinics = {}

    for card in cards:
        lines = card.get_text("\n", strip=True).split("\n")
        if len(lines) < 2:
            continue

        name = lines[0]
        address = lines[1]

        wait = next(
            (x for x in lines if "patient" in x.lower() and "line" in x.lower()),
            "Unknown",
        )

        xray = not any("No X-Ray Available" in x for x in lines)

        coords = CLINIC_COORDS.get(name)
        if not coords:
            continue

        key = name + "|" + address
        clinics[key] = {
            "name": name,
            "address": address,
            "wait": wait,
            "wait_num": wait_to_number(wait),
            "xray": xray,
            "coords": coords,
        }

    return list(clinics.values())

st.set_page_config(page_title="Exer Wait Finder", page_icon="🏥", layout="centered")

st.title("Exer Wait Finder")
st.caption("Ranks Exer clinics by shortest wait first, then nearest distance.")

xray_only = st.checkbox("X-ray only", value=True)
max_miles = st.slider("Max distance", 5, 60, 25)

st.subheader("Use GPS")
gps_location = get_geolocation()

gps_coords = None
if gps_location and "coords" in gps_location:
    gps_coords = (
        gps_location["coords"]["latitude"],
        gps_location["coords"]["longitude"],
    )
    st.success("GPS location received.")
elif gps_location and "error" in gps_location:
    st.warning("GPS was blocked or unavailable. Use the location box below.")

st.subheader("Or enter a city / ZIP")
typed_location = st.text_input(
    "Location",
    value="San Gabriel",
    placeholder="San Gabriel, Covina, Pasadena, 91776",
)

user_coords = gps_coords or get_known_location(typed_location)

if not user_coords:
    st.error("I don't know that location yet. Try San Gabriel, Pasadena, Covina, Glendora, Arcadia, Alhambra, Montebello, or a nearby ZIP.")

if st.button("Find best Exer", type="primary"):
    if not user_coords:
        st.stop()

    results = []

    for clinic in get_clinics():
        if xray_only and not clinic["xray"]:
            continue

        miles = miles_between(user_coords, clinic["coords"])

        if miles <= max_miles:
            clinic = clinic.copy()
            clinic["miles"] = miles
            results.append(clinic)

    results.sort(key=lambda x: (x["wait_num"], x["miles"]))

    if not results:
        st.warning("No matching Exer locations found within the selected distance.")
    else:
        best = results[0]
        st.success(
            f"Best match: {best['name']} — {best['wait']} — {best['miles']:.1f} miles away"
        )

        for i, clinic in enumerate(results, start=1):
            st.subheader(f"{i}. {clinic['name']}")
            st.write(clinic["address"])
            st.write(f"Line: {clinic['wait']}")
            st.write(f"Distance: {clinic['miles']:.1f} miles")
            st.write(f"X-ray: {'YES' if clinic['xray'] else 'NO'}")

            st.markdown(
                f"[Open directions in Google Maps]({maps_url(clinic['address'], user_coords)})"
            )
            st.divider()