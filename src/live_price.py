"""Read a live public product page and display verified fields; no invented price history."""
import argparse
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
# Explicitly limited to well-known retail hosts; extend only after reviewing site policies.
ALLOWED_DOMAINS = (
    'amazon.in', 'amazon.com', 'flipkart.com', 'croma.com',
    'reliancedigital.in', 'myntra.com', 'bestbuy.com', 'walmart.com'
)


def validate_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Use a standard HTTPS product URL without credentials or custom ports.')
    if not any(host == domain or host.endswith('.' + domain) for domain in ALLOWED_DOMAINS):
        raise ValueError('Retailer not on the supported-domain list; do not bypass this safety check.')
    # Block internal IP addresses even if a retailer hostname resolves unexpectedly.
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Host resolves to a non-public address.')
    except socket.gaierror as exc:
        raise ValueError('Unable to resolve retailer hostname.') from exc
    return url


def products_from_jsonld(soup):
    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                yield from walk(item)
        elif isinstance(obj, dict):
            types = obj.get('@type', [])
            if isinstance(types, str):
                types = [types]
            if 'Product' in types:
                yield obj
            for key in ('@graph', 'mainEntity'):
                if key in obj:
                    yield from walk(obj[key])
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            yield from walk(json.loads(tag.string or tag.get_text()))
        except (ValueError, TypeError):
            continue


def parse_price(raw):
    if raw is None or isinstance(raw, bool):
        return None
    s = str(raw).strip().replace(',', '')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', s):
        return None
    value = float(s)
    return round(value, 2) if 0 < value < 100_000_000 else None


def extract_product(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    def meta(*names):
        for name in names:
            tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                return tag['content'].strip()
        return None
    result = {'url': url, 'name': None, 'price': None, 'currency': None,
              'availability': 'unknown', 'source': None,
              'checked_at': datetime.now(timezone.utc).isoformat()}
    for product in products_from_jsonld(soup):
        offers = product.get('offers', {})
        if isinstance(offers, list):
            offers = next((x for x in offers if isinstance(x, dict) and (x.get('price') or x.get('lowPrice'))), {})
        if not isinstance(offers, dict):
            offers = {}
        price = parse_price(offers.get('price') or offers.get('lowPrice'))
        currency = offers.get('priceCurrency')
        if price is not None and isinstance(currency, str) and re.fullmatch(r'[A-Z]{3}', currency):
            result.update(name=str(product.get('name') or '')[:140] or None,
                          price=price, currency=currency, source='Product JSON-LD')
            availability = str(offers.get('availability') or '').lower()
            if 'instock' in availability:
                result['availability'] = 'in stock (page claims)'
            elif 'outofstock' in availability:
                result['availability'] = 'out of stock (page claims)'
            break
    if result['price'] is None:
        price = parse_price(meta('product:price:amount', 'og:price:amount'))
        currency = meta('product:price:currency', 'og:price:currency')
        if price is not None and currency and re.fullmatch(r'[A-Z]{3}', currency):
            result.update(price=price, currency=currency, source='Product meta tags')
    result['name'] = result['name'] or meta('og:title') or (soup.h1.get_text(' ', strip=True)[:140] if soup.h1 else None)
    return result


def fetch_product(url):
    validate_url(url)
    # No redirects: prevents a retailer redirect to an untrusted/internal URL.
    # Requests can still be blocked by the retailer, which is reported explicitly.
    response = requests.get(url, timeout=(5, 15), allow_redirects=False,
                            headers={'User-Agent': 'Mozilla/5.0 (compatible; PriceAgentEducational/1.0)'})
    if 300 <= response.status_code < 400:
        raise ValueError('Retailer redirected this URL. Supply the final product URL directly.')
    response.raise_for_status()
    if 'html' not in response.headers.get('Content-Type', '').lower():
        raise ValueError('URL did not return an HTML product page.')
    if len(response.content) > 3_000_000:
        raise ValueError('Page exceeds the 3 MB parsing limit.')
    return extract_product(response.text, url)


def show_result(item, budget, currency):
    table = Table(title='LIVE PRICE CHECK', show_header=False, border_style='cyan')
    table.add_column('Field', style='bold')
    table.add_column('Value')
    table.add_row('Product', item['name'] or 'Not found')
    table.add_row('Price', f"{item['currency']} {item['price']:,.2f}" if item['price'] is not None else 'Unavailable')
    table.add_row('Availability', item['availability'])
    table.add_row('Source', item['source'] or 'No structured price found')
    table.add_row('Checked (UTC)', item['checked_at'])
    table.add_row('Price history', 'Not available; discount authenticity NOT verified')
    console.print(table)
    if item['price'] is None:
        console.print(Panel('NO PRICE DATA — site may block automation or omit price metadata.', style='yellow'))
    elif currency != item['currency']:
        console.print(Panel(f"CURRENCY MISMATCH: Budget is {currency}, price is {item['currency']}. No comparison made.", style='yellow'))
    elif item['price'] <= budget:
        console.print(Panel('WITHIN BUDGET — price only; not a verified deal alert.', style='green'))
    else:
        console.print(Panel('OVER BUDGET', style='red'))


def main():
    parser = argparse.ArgumentParser(description='Live retail price checker (verified page data only)')
    parser.add_argument('--url', required=True, help='HTTPS product page on a supported retailer')
    parser.add_argument('--budget', required=True, type=float)
    parser.add_argument('--currency', default='INR', help='Budget currency, e.g. INR or USD')
    args = parser.parse_args()
    if not (0 <= args.budget < 100_000_000):
        parser.error('Budget must be between 0 and 100 million')
    currency = args.currency.upper()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        parser.error('Currency must be a three-letter code')
    try:
        show_result(fetch_product(args.url), args.budget, currency)
    except (ValueError, requests.RequestException) as exc:
        console.print(Panel(f'LIVE CHECK FAILED: {exc}', style='red'))
        raise SystemExit(1) from None

if __name__ == '__main__':
    main()
