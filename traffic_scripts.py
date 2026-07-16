import argparse
import asyncio
import random
import sys
import aiohttp

# Helper to generate random client IPs for legitimate user simulation
def get_random_ip():
    return f"{random.randint(10, 240)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"

async def send_stream_request(session, ip):
    url = "http://localhost:8001/stream"
    headers = {"X-Forwarded-For": ip}
    try:
        async with session.get(url, headers=headers, timeout=0.5) as resp:
            await resp.read()
    except Exception:
        pass

async def send_login_request(session, ip):
    url = "http://localhost:8001/login"
    headers = {"X-Forwarded-For": ip}
    payload = {"username": f"user_{random.randint(1,10000)}", "password": "securepassword123"}
    try:
        async with session.post(url, headers=headers, json=payload, timeout=0.5) as resp:
            await resp.read()
    except Exception:
        pass

async def run_merch_surge():
    print("\033[92m🛍️  Legitimate Merchandise Drop Surge Started...")
    print("⚡ Sending 500 req/sec to /stream and 50 req/sec to /login (Distributed IPs)...")
    print("Press Ctrl+C to terminate.\033[0m")
    
    async with aiohttp.ClientSession() as session:
        while True:
            start_time = asyncio.get_event_loop().time()
            tasks = []
            
            # 500 req/sec to /stream -> 50 per 0.1s
            for _ in range(50):
                tasks.append(send_stream_request(session, get_random_ip()))
            
            # 50 req/sec to /login -> 5 per 0.1s
            for _ in range(5):
                tasks.append(send_login_request(session, get_random_ip()))
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Rate limiting sleep to maintain ~550 req/sec
            elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = max(0.0, 0.1 - elapsed)
            await asyncio.sleep(sleep_time)

async def run_botnet_attack():
    print("\033[91m☠️  Botnet Credential Stuffing Attack Activated...")
    print("☠️  First POSTing botnet_active=True to /admin/botnet...")
    
    async with aiohttp.ClientSession() as session:
        # Flip botnet active
        try:
            async with session.post("http://localhost:8001/admin/botnet", json={"active": True}) as resp:
                data = await resp.json()
                print(f"Target response: {data}")
        except Exception as e:
            print(f"Failed to activate botnet state: {e}")
            sys.exit(1)
            
        print("⚡ Sending 800 req/sec to /login from static IP: 198.51.100.41...")
        print("Press Ctrl+C to terminate.\033[0m")
        
        static_ip = "198.51.100.41"
        while True:
            start_time = asyncio.get_event_loop().time()
            tasks = []
            
            # 800 req/sec to /login -> 80 per 0.1s
            for _ in range(80):
                tasks.append(send_login_request(session, static_ip))
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
            elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = max(0.0, 0.1 - elapsed)
            await asyncio.sleep(sleep_time)

async def deploy_retry_fault():
    print("\033[93m💥 Deploying Retry Config Fault Commit a7f31c2...")
    print("💥 POSTing max_retries: 8 to /admin/config...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("http://localhost:8001/admin/config", json={"max_retries": 8}) as resp:
                data = await resp.json()
                print(f"\033[92m✓ Configuration updated successfully. Target state: {data['config']}\033[0m")
        except Exception as e:
            print(f"\033[91m✗ Failed to deploy configuration: {e}\033[0m")

def main():
    parser = argparse.ArgumentParser(description="Target platform traffic injection toolkit.")
    parser.add_argument("--mode", choices=["merch", "botnet", "fault"], required=True, 
                        help="Choose simulation traffic mode.")
    args = parser.parse_args()
    
    try:
        if args.mode == "merch":
            asyncio.run(run_merch_surge())
        elif args.mode == "botnet":
            asyncio.run(run_botnet_attack())
        elif args.mode == "fault":
            asyncio.run(deploy_retry_fault())
    except KeyboardInterrupt:
        print("\n\033[96mTraffic injection halted.\033[0m")

if __name__ == "__main__":
    main()
