import urllib.request
import json

URL = "http://localhost:8001/admin/config"
payload = {"max_retries": 15}

print("\033[93m\033[1m========================================================\033[0m")
print("\033[93m💥 DEPLOYING COMMIT a7f31c2 (max_retries: 15)...       \033[0m")
print("\033[93m========================================================\033[0m")

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(URL, data=data, headers={'Content-Type': 'application/json'}, method='POST')

try:
    with urllib.request.urlopen(req, timeout=2.0) as response:
        res = json.loads(response.read().decode())
        print("\033[92m✓ Configuration updated on target.\033[0m")
        print(f"\033[97mCurrent Max Retries: \033[91m{res['config']['retry_config']}x\033[0m")
except Exception as e:
    print(f"\033[91m✗ Connection error: Make sure target_platform.py is running. Detail: {e}\033[0m")
print("\033[93m========================================================\033[0m\n")
