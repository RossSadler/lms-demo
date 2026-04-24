import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("HEYGEN_API_KEY", "").strip()

headers = {
    "X-Api-Key": api_key,
    "Accept": "application/json",
}

resp = requests.get(
    "https://api.heygen.com/v3/avatars",
    headers=headers,
    timeout=60,
)

print("AVATAR STATUS:", resp.status_code)
avatars = resp.json().get("data", [])

found = []

for avatar in avatars:
    group_id = avatar.get("id")
    name = avatar.get("name")

    looks_resp = requests.get(
        "https://api.heygen.com/v3/avatars/looks",
        headers=headers,
        params={"group_id": group_id},
        timeout=60,
    )

    if looks_resp.status_code != 200:
        print(f"Skipping {name} - looks request failed: {looks_resp.status_code}")
        continue

    looks = looks_resp.json().get("data", [])

    for look in looks:
        engines = look.get("supported_api_engines") or []
        if engines:
            found.append({
                "avatar_name": name,
                "look_name": look.get("name"),
                "look_id": look.get("id"),
                "engines": engines,
                "avatar_type": look.get("avatar_type"),
            })

print()
print("WORKING LOOKS:")
print("=" * 60)

for item in found:
    print("Avatar:", item["avatar_name"])
    print("Look:", item["look_name"])
    print("Look ID:", item["look_id"])
    print("Type:", item["avatar_type"])
    print("Engines:", item["engines"])
    print("-" * 60)