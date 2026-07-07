import re
import requests
import streamlit as st
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

URL = "https://exerurgentcare.com/exer-locations/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def wait_to_number(text):
    if "No patients" in text:
        return 0
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 999

@st.cache_data(ttl=300)
def geocode(place):
    geolocator = Nominatim(user_agent="exer_wait_finder")
    location = geolocator.geocode(place)
    if location:
        return location.latitude, location.longitude
    return None

@st.cache_data(ttl=300)
def get_clinics():
    html = requests.get(URL, headers=HEADERS).text
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
            "Unknown"
        )

        xray = not any("No X-Ray Available" in x for x in lines)

        key = name + "|" + address
        clinics[key] = {
            "name": name,
            "address": address,
            "wait": wait,
            "wait_num": wait_to_number(wait),
            "xray": xray,
        }

    return list(clinics.values())

st.title("Exer Wait Finder")

location = st.text_input(
    "Enter your current location",
    placeholder="Example: Covina, CA or 91723"
)

xray_only = st.checkbox("X-ray only", value=True)
max_miles = st.slider("Max distance", 5, 60, 25)

if st.button("Find best Exer"):
    if not location:
        st.warning("Enter your location first.")
        st.stop()

    user_coords = geocode(location)

    if not user_coords:
        st.error("Could not find that location. Try a ZIP code.")
        st.stop()

    results = []

    for clinic in get_clinics():
        if xray_only and not clinic["xray"]:
            continue

        clinic_coords = geocode(clinic["address"])
        if not clinic_coords:
            continue

        miles = geodesic(user_coords, clinic_coords).miles

        if miles <= max_miles:
            estimated_wait = clinic["wait_num"] * 8
            estimated_drive = miles * 2.2
            score = estimated_wait + estimated_drive

            clinic["miles"] = miles
            clinic["estimated_wait"] = estimated_wait
            clinic["score"] = score
            results.append(clinic)

    results.sort(key=lambda x: x["score"])

    if not results:
        st.warning("No nearby Exer locations found.")
    else:
        for i, clinic in enumerate(results, start=1):
            st.subheader(f"{i}. {clinic['name']}")
            st.write(clinic["address"])
            st.write(f"Distance: {clinic['miles']:.1f} miles")
            st.write(f"Line: {clinic['wait']}")
            st.write(f"Estimated wait: {clinic['estimated_wait']} minutes")
            st.write(f"X-ray: {'YES' if clinic['xray'] else 'NO'}")

            maps_url = "https://www.google.com/maps/search/?api=1&query=" + clinic["address"].replace(" ", "+")
            st.markdown(f"[Open in Google Maps]({maps_url})")
            st.divider()