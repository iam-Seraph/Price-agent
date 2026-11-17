import unittest
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
    def test_emi_rejected(self):
        self.assertEqual(self.client.parse(L, self.html(price='4999/month EMI'), 'r').status, Status.QUARANTINED)
    def test_stock(self):
        o = self.client.parse(L, self.html(availability='OutOfStock'), 'r')
        self.assertEqual((o.status, o.price_paisa), (Status.OUT_OF_STOCK, None))
    def test_dom_change(self):
        self.assertEqual(self.client.parse(L, '<html></html>', 'r').status, Status.DOM_CHANGED)
    def test_default_disabled(self):
        self.assertFalse(self.client.enabled)
