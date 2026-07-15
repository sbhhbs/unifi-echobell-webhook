from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .echobell import EchoBellError
from .payload import Client, InvalidPayload, is_explicit_disconnect, parse_client
from .storage import ClientStore


class Notifier(Protocol):
    def notify_new_client(self, client: Client) -> tuple[int, str]: ...


@dataclass(frozen=True)
class ProcessResult:
    action: str
    reason: str = ""
    client: Client | None = None
    sightings: int = 0
    echobell_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": True, "action": self.action}
        if self.reason:
            result["reason"] = self.reason
        if self.client:
            result["client"] = asdict(self.client)
        if self.sightings:
            result["sightings"] = self.sightings
        if self.echobell_status is not None:
            result["echobell_status"] = self.echobell_status
        return result


class WebhookService:
    def __init__(self, store: ClientStore, notifier: Notifier):
        self.store = store
        self.notifier = notifier

    def process(self, payload: dict[str, Any]) -> ProcessResult:
        if is_explicit_disconnect(payload):
            return ProcessResult(action="ignored", reason="disconnect_event")

        client = parse_client(payload)
        sighting = self.store.register_sighting(client, payload)
        if not sighting.is_new:
            return ProcessResult(
                action="ignored",
                reason="known_client",
                client=client,
                sightings=sighting.sightings,
            )

        try:
            status, _ = self.notifier.notify_new_client(client)
        except EchoBellError as error:
            self.store.mark_notification(client.mac, "failed", str(error))
            raise

        self.store.mark_notification(client.mac, "delivered")
        return ProcessResult(
            action="notified",
            client=client,
            sightings=sighting.sightings,
            echobell_status=status,
        )


__all__ = ["InvalidPayload", "ProcessResult", "WebhookService"]

