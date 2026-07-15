from __future__ import annotations

import unittest

from unifi_webhook.payload import InvalidPayload, is_explicit_disconnect, normalize_mac, parse_client


class PayloadTests(unittest.TestCase):
    def test_parses_nested_unifi_fields(self) -> None:
        payload = {
            "event": {
                "eventName": "WiFi Client Connected",
                "data": {
                    "clientMac": "AA-BB-CC-DD-EE-FF",
                    "clientHostname": "phone",
                    "clientIp": "192.168.1.20",
                    "wifiName": "Home",
                    "connectedToDeviceName": "Hall AP",
                },
            }
        }

        client = parse_client(payload)

        self.assertEqual(client.mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(client.name, "phone")
        self.assertEqual(client.ip_address, "192.168.1.20")
        self.assertEqual(client.wifi_name, "Home")
        self.assertEqual(client.connected_to, "Hall AP")

    def test_parses_cef_prefixed_keys(self) -> None:
        client = parse_client(
            {
                "UNIFIclientMac": "aabb.ccdd.eeff",
                "UNIFIclientAlias": "Laptop",
                "UNIFIclientIP": "10.0.0.4",
                "UNIFInetworkName": "LAN",
            }
        )

        self.assertEqual(client.mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(client.name, "Laptop")
        self.assertEqual(client.ip_address, "10.0.0.4")
        self.assertEqual(client.network, "LAN")

    def test_rejects_missing_or_invalid_mac(self) -> None:
        with self.assertRaises(InvalidPayload):
            parse_client({"clientHostname": "no-mac"})
        with self.assertRaises(InvalidPayload):
            parse_client({"clientMac": "not-a-mac"})

    def test_normalizes_common_mac_formats(self) -> None:
        self.assertEqual(normalize_mac("AABBCCDDEEFF"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(normalize_mac("aa:bb:cc:dd:ee:ff"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(normalize_mac("aa-bb-cc-dd-ee-ff"), "aa:bb:cc:dd:ee:ff")

    def test_detects_disconnect_event(self) -> None:
        self.assertTrue(is_explicit_disconnect({"event": {"name": "WiFi Client Disconnected"}}))
        self.assertFalse(is_explicit_disconnect({"event": {"name": "WiFi Client Connected"}}))


if __name__ == "__main__":
    unittest.main()

