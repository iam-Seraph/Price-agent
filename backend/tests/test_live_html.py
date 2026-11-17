import asyncio
import unittest
from unittest.mock import patch
import httpx
from price_engine.adapters import Listing
from price_engine.live_html import StructuredHTMLClient
from price_engine.models import Status

L = Listing('listing-1', 'croma', 'SKU123', 'https://www.croma.com/example', 'product-1')
class TestHTML(unittest.TestCase):
    def setUp(self):
        self.client = StructuredHTMLClient(allowed_domains=('croma.com',))
    def html(self, sku='SKU123', price='1,49,999.00', availability='InStock'):
        return f'<script type="application/ld+json">{{"@type":"Product","sku":"{sku}","offers":{{"price":"{price}","priceCurrency":"INR","availability":"https://schema.org/{availability}"}}}}</script>'
    def test_valid_price(self):
        o = self.client.parse(L, self.html(), 'record-1')
        self.assertEqual((o.status, o.price_paisa), (Status.VALID_PRICE, 14999900))
    def test_identity_fail_closed(self):
        self.assertEqual(self.client.parse(L, self.html(sku='OTHER'), 'r').status, Status.QUARANTINED)
    def test_multi_product_fixture_selects_only_exact_identifier(self):
        combined=self.html(sku='OTHER',price='1.00')+self.html(sku='SKU123',price='1,299.99')
        observation=self.client.parse(L, combined, 'mixed-product-list')
        self.assertEqual((observation.status,observation.price_paisa),
                         (Status.VALID_PRICE,129999))
        huge=self.client.parse(L,'X'*3_000_001,'oversized')
        self.assertEqual((huge.status,huge.reason),(Status.DOM_CHANGED,'HTML_TOO_LARGE'))

    def test_emi_rejected(self):
        self.assertEqual(self.client.parse(L, self.html(price='4999/month EMI'), 'r').status, Status.QUARANTINED)
    def test_stock(self):
        o = self.client.parse(L, self.html(availability='OutOfStock'), 'r')
        self.assertEqual((o.status, o.price_paisa), (Status.OUT_OF_STOCK, None))
    def test_dom_change(self):
        self.assertEqual(self.client.parse(L, '<html></html>', 'r').status, Status.DOM_CHANGED)
    def test_httpx_transport_shared_and_nonblocking(self):
        seen=[]
        async def respond(request):
            seen.append(request.url.path)
            await asyncio.sleep(0)
            return httpx.Response(200, headers={'content-type':'text/html'},
                                  text=self.html(price='1234.50'))
        transport=httpx.MockTransport(respond)
        timeout=httpx.Timeout(connect=1,read=1,write=1,pool=1)
        limits=httpx.Limits(max_connections=4,max_keepalive_connections=2)
        async def run():
            async with httpx.AsyncClient(transport=transport,timeout=timeout,limits=limits,
                                         follow_redirects=False,trust_env=False) as http_client:
                a=StructuredHTMLClient(allowed_domains=('croma.com',),enabled=True,
                    policy_approved=True,http_client=http_client)
                b=StructuredHTMLClient(allowed_domains=('croma.com',),enabled=True,
                    policy_approved=True,http_client=http_client)
                self.assertIs(a.http_client,b.http_client)
                with patch('price_engine.live_html.validate_target',return_value=None):
                    result=await asyncio.gather(a.fetch_price(L),b.fetch_price(L))
                self.assertEqual([o.price_paisa for o in result],[123450,123450])
        asyncio.run(run())
        self.assertEqual(len(seen),2)

    def test_throttle_and_access_denial_with_mock_transport(self):
        async def run():
            for code, headers, status in [
                (429,{'retry-after':'7'},Status.API_THROTTLED),
                (503,{'retry-after':'9'},Status.API_THROTTLED),
                (403,{},Status.ACCESS_DENIED),
                (503,{},Status.TRANSIENT_ERROR),
            ]:
                async def respond(request):
                    return httpx.Response(code,headers=headers)
                async with httpx.AsyncClient(transport=httpx.MockTransport(respond),
                   timeout=httpx.Timeout(connect=1,read=1,write=1,pool=1),
                   limits=httpx.Limits(max_connections=2,max_keepalive_connections=1),
                   trust_env=False,follow_redirects=False) as session:
                    adapter=StructuredHTMLClient(allowed_domains=('croma.com',),
                        enabled=True,policy_approved=True,http_client=session)
                    with patch('price_engine.live_html.validate_target',return_value=None):
                        result=await adapter.fetch_price(L)
                    self.assertEqual(result.status,status)
                    if 'retry-after' in headers:
                        self.assertEqual(result.retry_after_seconds,float(headers['retry-after']))
        asyncio.run(run())

    def test_default_disabled(self):
        self.assertFalse(self.client.enabled)
