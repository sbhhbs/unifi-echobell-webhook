from __future__ import annotations

import unittest

from unifi_webhook.unifi import _client_from_row


class UniFiClientTests(unittest.TestCase):
    def test_builds_client_from_historical_row(self) -> None:
        client = _client_from_row(
            {
                "mac": "AA-BB-CC-DD-EE-FF",
                "name": "Existing phone",
                "last_ip": "192.168.1.20",
                "last_connection_network_name": "Home",
                "last_connection_device_name": "Hall AP",
                "oui": "Example Inc.",
            }
        )

        self.assertIsNotNone(client)
        self.assertEqual(client.mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(client.name, "Existing phone")
        self.assertEqual(client.ip_address, "192.168.1.20")
        self.assertEqual(client.connected_to, "Hall AP")

    def test_skips_row_without_valid_mac(self) -> None:
        self.assertIsNone(_client_from_row({"name": "No MAC"}))


if __name__ == "__main__":
    unittest.main()
