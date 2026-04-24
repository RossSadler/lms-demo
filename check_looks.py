import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("HEYGEN_API_KEY", "").strip()

GROUP_ID = "cf9c0a84333b48e2a6e09bebf25d42d3"  # Rebecca

headers = {
    "X-Api-Key": api_key,
    "Accept": "application/json",
}

resp = requests.get(
    "https://api.heygen.com/v3/avatars/looks",
    headers=headers,
    params={"group_id": GROUP_ID},
    timeout=60,
)

print("STATUS:", resp.status_code)
print("RAW:", resp.text[:1000])

data = resp.json()

for look in data.get("data", []):
    print("LOOK NAME:", look.get("name"))
    print("LOOK ID:", look.get("id"))
    print("ENGINES:", look.get("supported_api_engines"))
    print("-" * 40)