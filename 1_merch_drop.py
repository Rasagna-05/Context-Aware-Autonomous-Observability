import requests

BACKEND_URL = "http://127.0.0.1:8000/mutate"

print("\033[96m\033[1m========================================================\033[0m")
print("\033[92m🛍️  INITIATING FLASH MERCH DROP SURGE LOAD EVENT...\033[0m")
print("\033[96m========================================================\033[0m")

payload = {
    "context": "MERCH_DROP",
    "legitimate_fans": 15000,
    "botnet_ips": 0,
    "retry_multiplier": 1.0,
    "mitigation_applied": False
}

try:
    response = requests.post(BACKEND_URL, json=payload)
    if response.status_code == 200:
        print("\033[92m✓ State mutated successfully on control plane.\033[0m")
        print(f"\033[97mCurrent Context: \033[93m{response.json()['current_state']['context']}\033[0m")
        print(f"\033[97mExpected Users:  \033[92m{response.json()['current_state']['legitimate_fans']:,}\033[0m")
    else:
        print(f"\033[91m✗ Failed to mutate state. Server returned code {response.status_code}\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure backend.py is running on port 8000. Detail: {e}\033[0m")
print("\033[96m========================================================\033[0m\n")
