import urllib.request
import json

URL = "http://127.0.0.1:8000/api/state/mutate"
payload = {
    "current_context": "MERCH_DROP",
    "legitimate_fans": 14500
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(URL, data=data, headers={'Content-Type': 'application/json'}, method='POST')

print("\033[96m\033[1m========================================================\033[0m")
print("\033[92m🛍️  INITIATING FLASH MERCH DROP SURGE LOADING...\033[0m")
print("\033[96m========================================================\033[0m")

try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print("\033[92m✓ State mutated successfully on twin engine.\033[0m")
        print(f"\033[97mContext: \033[93m{res['state']['current_context']}\033[0m")
        print(f"\033[97mLegitimate Fans:  \033[92m{res['state']['legitimate_fans']:,} connections\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure backend_twin.py is running. Detail: {e}\033[0m")
print("\033[96m========================================================\033[0m\n")
