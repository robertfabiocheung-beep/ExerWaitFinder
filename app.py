import re
import requests
import streamlit as st
from bs4 import BeautifulSoup

URL = "https://exerurgentcare.com/exer-locations/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def wait_to_number(text):
    if "No patients" in text:
        return 0
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 999

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

    return sorted(clinics.values(), key=lambda x: x["wait_num"])

st.title("Exer Wait Finder")

search_area = st.text_input(
    "Enter city or nearby area",
    value="Covina",
    placeholder="Example: Covina, Pasadena, Glendora"
)

xray_only = st.checkbox("X-ray only", value=True)

if st.button("Find Exer locations"):
    clinics = get_clinics()
    results = []

    for clinic in clinics:
        if xray_only and not clinic["xray"]:
            continue

        text = (clinic["name"] + " " + clinic["address"]).lower()

        if search_area.lower() in text:
            results.append(clinic)

    if not results:
        st.warning("No matching Exer locations found. Try another nearby city like Pasadena or Glendora.")
    else:
        for i, clinic in enumerate(results, start=1):
            st.subheader(f"{i}. {clinic['name']}")
            st.write(clinic["address"])
            st.write(f"Line: {clinic['wait']}")
            st.write(f"X-ray: {'YES' if clinic['xray'] else 'NO'}")

            maps_url = "https://www.google.com/maps/search/?api=1&query=" + clinic["address"].replace(" ", "+")
            st.markdown(f"[Open in Google Maps]({maps_url})")
            st.divider()