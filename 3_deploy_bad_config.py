import requests

BACKEND_URL = "http://127.0.0.1:8000/mutate"

print("\033[93m\033[1m========================================================\033[0m")
print("\033[93m💥 DEPLOYING COMMIT a7f31c2 (max_retries: -1)...       \033[0m")
print("\033[93m========================================================\033[0m")

payload = {
    "retry_multiplier": 8.5,
    "mitigation_applied": False
}

try:
    response = requests.post(BACKEND_URL, json=payload)
    if response.status_code == 200:
        print("\033[93m💥 [CONFIG FAULT] Production deployment complete.\033[0m")
        print(f"\033[97mCommit Hash:  \033[93ma7f31c2\033[0m")
        print(f"\033[97mRetry Multiplier: \033[91m{response.json()['current_state']['retry_multiplier']}x amplification\033[0m")
    else:
        print(f"\033[91m✗ Failed to deploy config. Server returned code {response.status_code}\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure backend.py is running on port 8000. Detail: {e}\033[0m")
print("\033[93m========================================================\033[0m\n")
