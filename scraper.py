import re
import requests
from bs4 import BeautifulSoup

URL = "https://exerurgentcare.com/exer-locations/"
headers = {"User-Agent": "Mozilla/5.0"}

NEARBY_KEYWORDS = [
    "Covina",
    "West Covina",
    "Glendora",
    "Arcadia",
    "Pasadena",
    "Pomona",
    "La Verne",
    "Montclair",
    "Chino",
    "Claremont",
]

def wait_to_number(text):
    if "No patients" in text:
        return 0
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 999

html = requests.get(URL, headers=headers).text
soup = BeautifulSoup(html, "html.parser")

cards = soup.select(".location-card")
clinics = {}
for card in cards:
    lines = card.get_text("\n", strip=True).split("\n")

    name = lines[0]
    address = lines[1] if len(lines) > 1 else ""

    wait_line = next((x for x in lines if "patient" in x.lower() and "line" in x.lower()), "Unknown")
    xray_available = not any("No X-Ray Available" in x for x in lines)

    nearby = any(
        city.lower() in name.lower() or city.lower() in address.lower()
        for city in NEARBY_KEYWORDS
    )

    if nearby and xray_available:
        key = name + "|" + address
        clinics[key] = {
            "name": name,
            "address": address,
            "wait": wait_line,
            "wait_num": wait_to_number(wait_line),
            "xray": xray_available
        }

clinics = sorted(clinics.values(), key=lambda x: x["wait_num"])

print("Nearby Exer locations with X-ray, sorted by shortest line:\n")

for c in clinics:
    print(f"{c['name']}")
    print(f"{c['address']}")
    print(f"Wait: {c['wait']}")
    print("--------------------")