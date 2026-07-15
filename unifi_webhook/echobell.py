from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import quote

from .payload import Client


class EchoBellError(RuntimeError):
    pass


class EchoBellClient:
    def __init__(
        self,
        base_url: str,
        direct_key: str,
        notification_type: str,
        external_link: str,
        timeout_seconds: float,
    ):
        self.url = base_url.rstrip("/") + "/" + quote(direct_key, safe="")
        self.notification_type = notification_type
        self.external_link = external_link
        self.timeout_seconds = timeout_seconds

    def notify_new_client(self, client: Client) -> tuple[int, str]:
        notification = build_notification(client, self.notification_type, self.external_link)
        request = urllib.request.Request(
            self.url,
            data=json.dumps(notification, separators=(",", ":"), sort_keys=True).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "unifi-echobell-webhook/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                return int(response.status), body
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            error.close()
            raise EchoBellError(f"EchoBell returned HTTP {error.code}: {body[:500]}") from error
        except OSError as error:
            raise EchoBellError(f"could not reach EchoBell: {error}") from error


def build_notification(client: Client, notification_type: str, external_link: str) -> dict[str, str]:
    display_name = client.name or "Unnamed device"
    body_lines = [f"Name: {display_name}", f"MAC: {client.mac}"]
    optional_fields = (
        ("IP", client.ip_address),
        ("Network", client.network),
        ("Wi-Fi", client.wifi_name),
        ("Connected via", client.connected_to),
        ("Site", client.site),
        ("Manufacturer", client.manufacturer),
    )
    body_lines.extend(f"{label}: {value}" for label, value in optional_fields if value)
    notification = {
        "title": f"New UniFi client: {display_name}",
        "body": "\n".join(body_lines),
        "notificationType": notification_type,
    }
    if external_link:
        notification["externalLink"] = external_link
    return notification

