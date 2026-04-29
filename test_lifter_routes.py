import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

WP_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

auth = HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)

routes = [
    "/wp-json/llms/v1/courses",
    "/wp-json/llms/v1/lessons",
    "/wp-json/wp/v2/course",
    "/wp-json/wp/v2/lesson",
]

for route in routes:
    url = f"{WP_URL.rstrip('/')}{route}"
    print("\nTesting:", url)

    get_res = requests.get(url, auth=auth)
    print("GET:", get_res.status_code)

    options_res = requests.options(url, auth=auth)
    print("OPTIONS:", options_res.status_code)
    print(options_res.text[:500])