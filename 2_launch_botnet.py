import requests

BACKEND_URL = "http://127.0.0.1:8000/mutate"

print("\033[91m\033[1m========================================================\033[0m")
print("\033[91m☠️  INJECTING CREDENTIAL STUFFING BOTNET (COHORT-91)... \033[0m")
print("\033[91m========================================================\033[0m")

payload = {
    "botnet_ips": 45000,
    "mitigation_applied": False
}

try:
    response = requests.post(BACKEND_URL, json=payload)
    if response.status_code == 200:
        print("\033[91m☠️ [ATTACK VECTOR] Malicious traffic payload deployed.\033[0m")
        print(f"\033[97mBotnet Cohort: \033[91mcohort-91\033[0m")
        print(f"\033[97mBotnet Traffic Size: \033[91m{response.json()['current_state']['botnet_ips']:,} requests/min\033[0m")
    else:
        print(f"\033[91m✗ Failed to inject botnet. Server returned code {response.status_code}\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure backend.py is running on port 8000. Detail: {e}\033[0m")
print("\033[91m========================================================\033[0m\n")
