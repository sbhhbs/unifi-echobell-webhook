from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
from typing import Any, Iterable


class InvalidPayload(ValueError):
    pass


@dataclass(frozen=True)
class Client:
    mac: str
    name: str = ""
    ip_address: str = ""
    network: str = ""
    wifi_name: str = ""
    connected_to: str = ""
    site: str = ""
    manufacturer: str = ""


_MAC_KEYS = ("clientmac", "clientmacaddress", "stationmac", "stamac", "macaddress", "mac")
_NAME_KEYS = ("clientalias", "clientname", "clienthostname", "hostname")
_IP_KEYS = ("clientip", "clientipaddress", "ipaddress", "ip")
_NETWORK_KEYS = ("networkname", "clientnetwork", "network")
_WIFI_KEYS = ("wifiname", "ssid")
_CONNECTED_TO_KEYS = (
    "connectedtodevicename",
    "lastconnectedtodevicename",
    "uplinkdevicename",
    "accesspointname",
    "apname",
)
_SITE_KEYS = ("sitename", "site", "host")
_MANUFACTURER_KEYS = ("clientmanufacturer", "manufacturer", "vendor")
_EVENT_TEXT_KEYS = ("eventname", "eventtype", "name", "key", "type", "msg", "message", "description")


def parse_client(payload: dict[str, Any]) -> Client:
    mac_value = _find_first(payload, _MAC_KEYS)
    if not mac_value:
        raise InvalidPayload(
            "client MAC address not found; include a clientMac, clientMacAddress, macAddress, or mac field"
        )
    mac = normalize_mac(mac_value)
    if not mac:
        raise InvalidPayload(f"invalid client MAC address: {mac_value!r}")

    return Client(
        mac=mac,
        name=_find_first(payload, _NAME_KEYS),
        ip_address=_find_first(payload, _IP_KEYS),
        network=_find_first(payload, _NETWORK_KEYS),
        wifi_name=_find_first(payload, _WIFI_KEYS),
        connected_to=_find_first(payload, _CONNECTED_TO_KEYS),
        site=_find_first(payload, _SITE_KEYS),
        manufacturer=_find_first(payload, _MANUFACTURER_KEYS),
    )


def is_explicit_disconnect(payload: dict[str, Any]) -> bool:
    for value in _find_all(payload, _EVENT_TEXT_KEYS):
        normalized = value.casefold().replace("_", " ").replace("-", " ")
        if "disconnect" in normalized:
            return True
    return False


def normalize_mac(value: str) -> str:
    raw_value = value.strip().casefold()
    if not re.fullmatch(r"[0-9a-f.:-]+", raw_value):
        return ""
    hex_value = re.sub(r"[^0-9a-f]", "", raw_value)
    if len(hex_value) != 12:
        return ""
    return ":".join(hex_value[index : index + 2] for index in range(0, 12, 2))


def _find_first(payload: dict[str, Any], aliases: Iterable[str]) -> str:
    dictionaries = tuple(_walk_dicts(payload))
    for alias in aliases:
        for dictionary in dictionaries:
            for key, value in dictionary.items():
                if _normalize_key(str(key)) == alias and _is_scalar(value):
                    text = str(value).strip()
                    if text:
                        return text
    return ""


def _find_all(payload: dict[str, Any], aliases: Iterable[str]) -> list[str]:
    normalized_aliases = set(aliases)
    values: list[str] = []
    for dictionary in _walk_dicts(payload):
        for key, value in dictionary.items():
            if _normalize_key(str(key)) in normalized_aliases and _is_scalar(value):
                text = str(value).strip()
                if text:
                    values.append(text)
    return values


def _walk_dicts(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    queue: deque[Any] = deque([payload])
    while queue:
        value = queue.popleft()
        if isinstance(value, dict):
            yield value
            queue.extend(value.values())
        elif isinstance(value, list):
            queue.extend(value)


def _normalize_key(key: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    if normalized.startswith("unifi"):
        normalized = normalized[5:]
    return normalized


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)
