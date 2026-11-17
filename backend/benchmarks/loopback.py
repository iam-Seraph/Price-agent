"""Offline socket-pool benchmark. Binds only to 127.0.0.1, never a retailer.

Usage from backend/: python -m benchmarks.loopback
By default: 120 calls, 25 ms injected latency, 20 concurrent clients.
"""
from __future__ import annotations

import asyncio
import json
import math
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx

from price_engine.adapters import BaseRetailerClient, Listing
from price_engine.models import Observation, Paisa, Status
from price_engine.router import CircuitBreaker, HybridRouter, Policy, TokenBucket


class LocalServer(ThreadingHTTPServer):
    request_queue_size = 128
    mode: str = 'healthy'


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_GET(self) -> None:
        time.sleep(0.025)
        item = int(self.path.split('/')[-1])
        code = 503 if item % 20 in (0, 1) else 429 if item % 20 == 2 else 403 if item % 20 == 3 else 200
        if isinstance(self.server, LocalServer) and self.server.mode == 'healthy':
            code = 200
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', '2')
        if code == 429:
            self.send_header('Retry-After', '1')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format: str, *args: object) -> None:
        pass


class SyntheticAdapter(BaseRetailerClient):
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.calls = 0

    async def health_check(self) -> bool:
        return True

    async def fetch_price(self, listing: Listing) -> Observation:
        self.calls += 1
        response = await self.client.get('/item/' + listing.listing_id)
        statuses = {200:Status.VALID_PRICE, 503:Status.TRANSIENT_ERROR,
                    429:Status.API_THROTTLED, 403:Status.ACCESS_DENIED}
        status = statuses.get(response.status_code, Status.UNAVAILABLE)
        return Observation(listing.listing_id,status,datetime.now(timezone.utc),
            'API',uuid4().hex,price_paisa=Paisa(499900) if status == Status.VALID_PRICE else None,
            availability='IN_STOCK' if status == Status.VALID_PRICE else 'UNKNOWN',
            identity_verified=status == Status.VALID_PRICE,
            retry_after_seconds=1.0 if status == Status.API_THROTTLED else None)


async def measure(port: int, mode: str) -> dict[str, object]:
    client_timeout=httpx.Timeout(connect=2,read=2,write=2,pool=2)
    limits=httpx.Limits(max_connections=20,max_keepalive_connections=20)
    async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',timeout=client_timeout,
        limits=limits,trust_env=False) as client:
        api=SyntheticAdapter(client)
        html=SyntheticAdapter(client)
        router=HybridRouter(api,html,Policy(True,False,False,max_attempts=3),
            TokenBucket(100000,burst=1200),TokenBucket(100000,burst=1200),
            CircuitBreaker(threshold=100000),CircuitBreaker(threshold=100000),
            max_in_flight=20,per_host_in_flight=20)
        active=asyncio.Semaphore(20)
        async def one(n: int) -> tuple[float,str]:
            async with active:
                listing=Listing(str(n),'fake','sku',f'https://demo.example.org/{n}','p')
                start=time.perf_counter()
                result=await router.ingest(listing,[])
                return (time.perf_counter()-start,result.status.value if result else 'NONE')
        started=time.perf_counter()
        results=await asyncio.gather(*(one(n) for n in range(120)))
        elapsed=time.perf_counter()-started
    latencies=sorted(duration*1000 for duration,_ in results)
    statuses: dict[str,int]={}
    for _,status in results:
        statuses[status]=statuses.get(status,0)+1
    return {'scenario':mode,'items':120,'throughput_items_sec':round(120/elapsed,2),
            'p95_ms':round(latencies[math.ceil(len(latencies)*.95)-1],1),
            'elapsed_sec':round(elapsed,3),'http_attempts':api.calls,'outcomes':statuses}


def main() -> None:
    server=LocalServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        for mode in ('healthy','mixed'):
            server.mode=mode
            print(json.dumps(asyncio.run(measure(server.server_port,mode))))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

if __name__ == '__main__':
    main()
