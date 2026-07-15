from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from unifi_webhook.echobell import EchoBellError, build_notification
from unifi_webhook.payload import Client
from unifi_webhook.service import WebhookService
from unifi_webhook.storage import ClientStore


class FakeNotifier:
    def __init__(self, error: EchoBellError | None = None):
        self.error = error
        self.clients: list[Client] = []

    def notify_new_client(self, client: Client) -> tuple[int, str]:
        self.clients.append(client)
        if self.error:
            raise self.error
        return 200, "ok"


class WebhookServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "clients.sqlite3")
        self.notifier = FakeNotifier()
        self.store = ClientStore(self.db_path)
        self.service = WebhookService(self.store, self.notifier)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_notifies_only_on_first_sighting_and_persists(self) -> None:
        first = self.service.process({"clientMac": "AA-BB-CC-DD-EE-FF", "clientHostname": "phone"})
        second = self.service.process({"clientMac": "aa:bb:cc:dd:ee:ff", "clientHostname": "phone"})
        restarted_service = WebhookService(ClientStore(self.db_path), self.notifier)
        third = restarted_service.process({"clientMac": "aabb.ccdd.eeff", "clientHostname": "phone"})

        self.assertEqual(first.action, "notified")
        self.assertEqual(second.reason, "known_client")
        self.assertEqual(third.reason, "known_client")
        self.assertEqual(len(self.notifier.clients), 1)
        self.assertEqual(self.store.get_client("aa:bb:cc:dd:ee:ff")["sightings"], 3)

    def test_notifies_different_clients(self) -> None:
        self.service.process({"clientMac": "00:00:00:00:00:01"})
        self.service.process({"clientMac": "00:00:00:00:00:02"})

        self.assertEqual(len(self.notifier.clients), 2)
        self.assertEqual(self.store.client_count(), 2)

    def test_simultaneous_duplicate_webhooks_notify_once(self) -> None:
        payload = {"clientMac": "00:00:00:00:00:01", "clientHostname": "phone"}

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(self.service.process, [payload] * 16))

        self.assertEqual(sum(result.action == "notified" for result in results), 1)
        self.assertEqual(sum(result.reason == "known_client" for result in results), 15)
        self.assertEqual(len(self.notifier.clients), 1)
        self.assertEqual(self.store.get_client("00:00:00:00:00:01")["sightings"], 16)

    def test_seeded_unifi_client_does_not_notify(self) -> None:
        seeded = self.store.seed_clients(
            [Client(mac="00:00:00:00:00:01", name="Existing phone")]
        )

        result = self.service.process(
            {"clientMac": "00:00:00:00:00:01", "clientHostname": "Existing phone"}
        )

        self.assertEqual(seeded, 1)
        self.assertEqual(result.reason, "known_client")
        self.assertEqual(self.notifier.clients, [])
        self.assertEqual(
            self.store.get_client("00:00:00:00:00:01")["notification_status"],
            "seeded",
        )

    def test_ignores_disconnect_without_recording_client(self) -> None:
        result = self.service.process(
            {"eventName": "WiFi Client Disconnected", "clientMac": "00:00:00:00:00:01"}
        )

        self.assertEqual(result.reason, "disconnect_event")
        self.assertEqual(self.store.client_count(), 0)
        self.assertEqual(self.notifier.clients, [])

    def test_failed_delivery_is_not_retried_for_duplicate_webhooks(self) -> None:
        failing_notifier = FakeNotifier(EchoBellError("offline"))
        service = WebhookService(self.store, failing_notifier)
        payload = {"clientMac": "00:00:00:00:00:01"}

        with self.assertRaises(EchoBellError):
            service.process(payload)
        duplicate = service.process(payload)

        self.assertEqual(duplicate.reason, "known_client")
        self.assertEqual(len(failing_notifier.clients), 1)
        self.assertEqual(self.store.get_client("00:00:00:00:00:01")["notification_status"], "failed")

    def test_builds_echo_bell_notification(self) -> None:
        notification = build_notification(
            Client(mac="aa:bb:cc:dd:ee:ff", name="Phone", ip_address="192.168.1.2", wifi_name="Home"),
            "time-sensitive",
            "https://example.test/clients",
        )

        self.assertEqual(notification["title"], "New UniFi client: Phone")
        self.assertIn("MAC: aa:bb:cc:dd:ee:ff", notification["body"])
        self.assertEqual(notification["notificationType"], "time-sensitive")
        self.assertEqual(notification["externalLink"], "https://example.test/clients")


if __name__ == "__main__":
    unittest.main()
