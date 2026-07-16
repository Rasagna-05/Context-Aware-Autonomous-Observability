import urllib.request
import json

URL = "http://127.0.0.1:8000/api/state/mutate"
payload = {
    "retry_factor": 8.8,
    "latency_base": 420
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(URL, data=data, headers={'Content-Type': 'application/json'}, method='POST')

print("\033[93m\033[1m========================================================\033[0m")
print("\033[93m💥 INJECTING payment-service RPC RETRY LOOP FAULT...    \033[0m")
print("\033[93m========================================================\033[0m")

try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print("\033[93m💥 [CONFIG DEVIATION] Code fault injected successfully.\033[0m")
        print(f"\033[97mRetry Multiplier Factor: \033[91m{res['state']['retry_factor']}x amplification\033[0m")
        print(f"\033[97mBase Latency Anchor:      \033[91m{res['state']['latency_base']} ms\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure backend_twin.py is running. Detail: {e}\033[0m")
print("\033[93m========================================================\033[0m\n")
