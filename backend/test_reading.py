
import json
from urllib.request import Request, urlopen

url = "http://127.0.0.1:5000/api/readings"

# TEST DATA ONLY — not a real water measurement.
payload = {
    "ph": 7.0,
    "turbidity": 1.0,
    "tds": 100.0,
    "temp": 25.0,
    "oxygen": 6.0
}

request = Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

with urlopen(request) as response:
    print("HTTP status:", response.status)
    print(response.read().decode("utf-8"))
