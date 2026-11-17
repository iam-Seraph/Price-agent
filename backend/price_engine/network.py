"""Approved HTTPS target validation; network access is never enabled by default.

This preflight does not pin DNS across the connection. A DNS-pinning transport is
required before enabling ingestion of untrusted or dynamically chosen hosts.
"""
from __future__ import annotations
import ipaddress
import socket
from urllib.parse import urlparse


def validate_target(url: str, approved_domains: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Invalid port') from exc
    if (parsed.scheme != 'https' or port not in (None, 443)
            or parsed.username or parsed.password
            or not any(host == d or host.endswith('.' + d) for d in approved_domains)):
        raise ValueError('Target must be an approved HTTPS retailer')
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError('Retailer DNS lookup failed') from exc
    if not answers or any(not ipaddress.ip_address(item[4][0]).is_global for item in answers):
        raise ValueError('Retailer resolved to a non-public IP')
