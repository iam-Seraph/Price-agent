"""Explicit local alert transports. Credentials are read from the environment only."""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr

import httpx


class AlertConfigurationError(ValueError):
    """The operator has not configured a permitted alert transport."""


class AlertDeliveryError(RuntimeError):
    """The outbound service failed without exposing credentials."""


def _safe_email(value: str | None) -> str:
    if not isinstance(value, str) or not 3 <= len(value) <= 254:
        raise AlertConfigurationError("Missing email contact")
    if "\r" in value or "\n" in value or parseaddr(value)[1] != value or "@" not in value:
        raise AlertConfigurationError("Invalid email contact")
    return value


def send_email(message: str) -> None:
    host = os.getenv("PRICE_AGENT_SMTP_HOST")
    user = os.getenv("PRICE_AGENT_SMTP_USER")
    password = os.getenv("PRICE_AGENT_SMTP_PASSWORD")
    sender = _safe_email(os.getenv("PRICE_AGENT_EMAIL_FROM"))
    recipient = _safe_email(os.getenv("PRICE_AGENT_EMAIL_TO"))
    if not host or not user or not password or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
        raise AlertConfigurationError("SMTP configuration incomplete")
    port_text = os.getenv("PRICE_AGENT_SMTP_PORT", "587")
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        raise AlertConfigurationError("Invalid SMTP port")
    port = int(port_text)
    letter = EmailMessage()
    letter["From"] = sender
    letter["To"] = recipient
    letter["Subject"] = "Price Agent: price threshold alert"
    letter.set_content(message[:4000])
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15,
                                  context=ssl.create_default_context()) as smtp:
                smtp.login(user, password)
                smtp.send_message(letter)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(user, password)
                smtp.send_message(letter)
    except (OSError, smtplib.SMTPException) as exc:
        raise AlertDeliveryError("SMTP delivery failed") from None


def send_telegram(message: str) -> None:
    token = os.getenv("PRICE_AGENT_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("PRICE_AGENT_TELEGRAM_CHAT_ID")
    if (not token or not chat_id or
            not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", token) or
            not re.fullmatch(r"-?[0-9]{4,20}", chat_id)):
        raise AlertConfigurationError("Telegram bot token or chat ID missing")
    try:
        with httpx.Client(timeout=12.0, trust_env=False, follow_redirects=False) as client:
            response = client.post(
                "https://api.telegram.org/bot" + token + "/sendMessage",
                data={"chat_id": chat_id, "text": message[:3500],
                      "disable_web_page_preview": "true"})
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise AlertDeliveryError("Telegram service refused message")
    except (httpx.HTTPError, ValueError):
        raise AlertDeliveryError("Telegram delivery failed") from None


def send_alert(channel: str, message: str) -> None:
    if channel == "EMAIL":
        send_email(message)
    elif channel == "TELEGRAM":
        send_telegram(message)
    else:
        raise AlertConfigurationError("Unsupported alert transport")
