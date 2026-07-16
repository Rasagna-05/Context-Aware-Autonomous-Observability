import asyncio
import aiohttp
import time

async def send_req(session, url, method="GET", json_payload=None, sem=None):
    # Use Semaphore to throttle concurrent sockets
    async with sem:
        try:
            if method == "GET":
                async with session.get(url, timeout=0.8) as resp:
                    await resp.read()
            else:
                async with session.post(url, json=json_payload, timeout=0.8) as resp:
                    await resp.read()
        except Exception:
            pass

async def main():
    print("\033[92m🛍️ INITIATING MERCHANDISE SURGE: 15,000 stream & 1,000 login requests...\033[0m")
    start = time.time()
    
    # Configure high-performance connector pooling and semaphore limit
    connector = aiohttp.TCPConnector(limit=500, ttl_dns_cache=300)
    sem = asyncio.Semaphore(150)  # Safe concurrent socket limit
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Loop for 5 seconds, sending 5 equal batches (3,000 stream + 200 login per second)
        for second in range(5):
            batch_start = time.time()
            tasks = []
            
            # Add 3,000 stream requests
            for _ in range(3000):
                tasks.append(send_req(session, "http://localhost:8001/stream", sem=sem))
                
            # Add 200 login requests
            for _ in range(200):
                tasks.append(send_req(session, "http://localhost:8001/login", method="POST", json_payload={"username": "customer", "password": "psw"}, sem=sem))
                
            await asyncio.gather(*tasks, return_exceptions=True)
            
            elapsed = time.time() - batch_start
            sleep_time = max(0.0, 1.0 - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                
    print(f"\033[92m🛍️ Merchandise Surge completed in {time.time() - start:.2f} seconds.\033[0m")

if __name__ == "__main__":
    asyncio.run(main())
