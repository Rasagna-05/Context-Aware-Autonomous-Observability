import asyncio
import aiohttp
import time

async def send_req(session, url, json_payload=None, sem=None):
    async with sem:
        try:
            # Set botnet identification header
            headers = {"X-Botnet": "true"}
            async with session.post(url, json=json_payload, headers=headers, timeout=0.8) as resp:
                await resp.read()
        except Exception:
            pass

async def main():
    print("\033[91m☠️ INJECTING CREDENTIAL STUFFING BOTNET: 80,000 login requests...\033[0m")
    
    # 1. Flip botnet active
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("http://localhost:8001/admin/botnet", json={"active": True}) as resp:
                print(f"Target response: {await resp.json()}")
        except Exception as e:
            print(f"Failed to activate botnet state: {e}")
            return

    start = time.time()
    
    # Configure high-performance connector pooling and semaphore limit
    connector = aiohttp.TCPConnector(limit=500, ttl_dns_cache=300)
    sem = asyncio.Semaphore(150)  # Safe concurrent socket limit
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Loop for 5 seconds, sending 5 equal batches (16,000 logins per second)
        for second in range(5):
            batch_start = time.time()
            tasks = []
            
            for _ in range(16000):
                tasks.append(send_req(session, "http://localhost:8001/login", json_payload={"username": "hacker", "password": "badpassword"}, sem=sem))
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
            elapsed = time.time() - batch_start
            sleep_time = max(0.0, 1.0 - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                
    print(f"\033[91m☠️ Botnet Attack completed in {time.time() - start:.2f} seconds.\033[0m")

if __name__ == "__main__":
    asyncio.run(main())
