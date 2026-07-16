import urllib.request
import json

URL = "http://127.0.0.1:8000/api/state/mutate"
payload = {
    "botnet_load": 55000
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(URL, data=data, headers={'Content-Type': 'application/json'}, method='POST')

print("\033[91m\033[1m========================================================\033[0m")
print("\033[91m☠️  INJECTING CREDENTIAL STUFFING BOTNET LOAD...\033[0m")
print("\033[91m========================================================\033[0m")

try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print("\033[91m☠️ [ATTACK FINGERPRINT] Botnet load injected.\033[0m")
        print(f"\033[97mCohort Profile: \033[91mcohort-91 (Static TTL)\033[0m")
        print(f"\033[97mBotnet Load Size: \033[91m{res['state']['botnet_load']:,} req/min\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure backend_twin.py is running. Detail: {e}\033[0m")
print("\033[91m========================================================\033[0m\n")
