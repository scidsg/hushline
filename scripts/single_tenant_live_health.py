"""Read-only public DNS and pinned-address HTTPS checks; no redirect or proxy."""

from __future__ import annotations

import contextlib
import http.client
import ipaddress
import json
import socket
import ssl
from http import HTTPStatus
from typing import Any

import requests

from hushline.single_tenant import valid_customer_domain

RESOLVERS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")
ROUTING = {"162.159.140.98", "172.66.0.96"}
MAX_BYTES = 16384
TXT_TYPE = 16
CNAME_TYPE = 5


def answers(origin: str, hostname: str, kind: str) -> list[dict[str, Any]]:
    if origin not in RESOLVERS or kind not in {"A", "AAAA", "TXT", "CNAME"}:
        raise ValueError("Unsupported DNS trust root or record")
    with requests.Session() as client:
        client.trust_env = False
        with client.get(
            origin,
            params={"name": hostname, "type": kind},
            headers={"Accept": "application/dns-json"},
            timeout=(5, 8),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != HTTPStatus.OK:
                raise ValueError("Public DNS lookup failed")
            body = bytearray()
            for chunk in response.iter_content(4096):
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("Public DNS response exceeded safety limit")
    data = json.loads(body)
    if data.get("Status") != 0:
        raise ValueError("Public DNS lookup did not resolve")
    return data.get("Answer", [])


def dns(domain: str, ingress: str, verification: str) -> bool:
    if not valid_customer_domain(domain) or not ingress.endswith(".ondigitalocean.app"):
        return False
    try:
        for origin in RESOLVERS:
            txt = answers(origin, "_hushline." + domain, "TXT")
            if not any(
                item.get("type") == TXT_TYPE
                and item.get("data", "").strip('"') == "hushline-verification=" + verification
                for item in txt
            ):
                return False
            cname = answers(origin, domain, "CNAME")
            direct = any(
                item.get("type") == CNAME_TYPE and item.get("data", "").rstrip(".") == ingress
                for item in cname
            )
            addresses = {
                item.get("data") for item in answers(origin, domain, "A") if item.get("type") == 1
            }
            if not direct and addresses != ROUTING:
                return False
        return True
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return False


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, domain: str, address: str) -> None:
        self.tls_context = ssl.create_default_context()
        super().__init__(domain, timeout=8, context=self.tls_context)
        self.address = address

    def connect(self) -> None:
        transport = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self.tls_context.wrap_socket(transport, server_hostname=self.host)
        except BaseException:
            transport.close()
            raise


def healthy(domain: str) -> bool:
    if not valid_customer_domain(domain):
        return False
    try:
        # Resolve through a fixed public resolver and connect to that exact IP.
        # A second DNS lookup cannot redirect the request to a private network.
        records = answers(RESOLVERS[0], domain, "A")
        addresses = [item["data"] for item in records if item.get("type") == 1]
        if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
            return False
        with contextlib.closing(PinnedHTTPS(domain, addresses[0])) as connection:
            connection.request("GET", "/health.json", headers={"Accept": "application/json"})
            response = connection.getresponse()
            body = response.read(MAX_BYTES + 1)
            return (
                response.status == HTTPStatus.OK
                and len(body) <= MAX_BYTES
                and json.loads(body) == {"status": "ok"}
            )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        http.client.HTTPException,
        requests.RequestException,
    ):
        return False
