from __future__ import annotations

import json
import ssl
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import quote

from .payload import Client, normalize_mac


class UniFiError(RuntimeError):
    pass


class UniFiClient:
    def __init__(
        self,
        host: str,
        api_key: str,
        site: str,
        verify_ssl: bool,
        timeout_seconds: float,
    ):
        base_url = host if "://" in host else f"https://{host}"
        self.url = (
            base_url.rstrip("/")
            + "/proxy/network/api/s/"
            + quote(site, safe="")
            + "/rest/user"
        )
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.ssl_context = None if verify_ssl else ssl._create_unverified_context()

    def list_known_clients(self) -> list[Client]:
        request = urllib.request.Request(
            self.url,
            headers={
                "Accept": "application/json",
                "User-Agent": "unifi-echobell-webhook/0.1",
                "X-API-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=self.ssl_context,
            ) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            error.close()
            raise UniFiError(f"UniFi returned HTTP {error.code}: {body[:500]}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise UniFiError(f"could not load known clients from UniFi: {error}") from error

        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise UniFiError("UniFi client response did not contain a data list")
        return [client for row in rows if isinstance(row, dict) if (client := _client_from_row(row))]


def _client_from_row(row: dict[str, Any]) -> Client | None:
    mac = normalize_mac(str(row.get("mac") or ""))
    if not mac:
        return None
    return Client(
        mac=mac,
        name=str(row.get("name") or row.get("display_name") or row.get("hostname") or ""),
        ip_address=str(row.get("last_ip") or row.get("ip") or ""),
        network=str(row.get("last_connection_network_name") or row.get("network") or ""),
        wifi_name=str(row.get("last_connection_network_name") or row.get("essid") or ""),
        connected_to=str(row.get("last_connection_device_name") or ""),
        manufacturer=str(row.get("oui") or ""),
    )
