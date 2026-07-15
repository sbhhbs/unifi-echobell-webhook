from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from typing import Any
from urllib.parse import urlparse

from .config import Config
from .echobell import EchoBellClient, EchoBellError
from .payload import InvalidPayload
from .service import WebhookService
from .storage import ClientStore
from .unifi import UniFiClient, UniFiError


WEBHOOK_PATH = "/webhook/unifi"


def make_handler(
    service: WebhookService,
    webhook_secret: str,
    max_body_bytes: int,
) -> type[BaseHTTPRequestHandler]:
    class UniFiWebhookHandler(BaseHTTPRequestHandler):
        server_version = "unifi-echobell-webhook/0.1"

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/health":
                self._write_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                client_count = service.store.client_count()
            except Exception as error:
                self._write_json(
                    {"ok": False, "error": f"database unavailable: {error}"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            self._write_json({"ok": True, "webhook_path": WEBHOOK_PATH, "known_clients": client_count})

        def do_POST(self) -> None:
            if urlparse(self.path).path.rstrip("/") != WEBHOOK_PATH:
                self._write_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if webhook_secret and not self._authorized():
                self._write_json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return

            raw_length = self.headers.get("Content-Length")
            try:
                content_length = int(raw_length or "0")
            except ValueError:
                self._write_json({"ok": False, "error": "invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
                return
            if content_length <= 0:
                self._write_json({"ok": False, "error": "JSON body required"}, HTTPStatus.BAD_REQUEST)
                return
            if content_length > max_body_bytes:
                self._write_json({"ok": False, "error": "request body too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return

            try:
                payload = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._write_json({"ok": False, "error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(payload, dict):
                self._write_json({"ok": False, "error": "JSON object required"}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return

            try:
                result = service.process(payload)
            except InvalidPayload as error:
                self._write_json({"ok": False, "error": str(error)}, HTTPStatus.UNPROCESSABLE_ENTITY)
                return
            except EchoBellError as error:
                self._write_json(
                    {
                        "ok": False,
                        "error": str(error),
                        "notification_will_not_be_retried": True,
                    },
                    HTTPStatus.BAD_GATEWAY,
                )
                return
            except Exception as error:
                self.log_error("unexpected webhook failure: %s", error)
                self._write_json({"ok": False, "error": "internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return

            self._write_json(result.to_dict())

        def _authorized(self) -> bool:
            supplied_secret = self.headers.get("X-Webhook-Secret", "")
            authorization = self.headers.get("Authorization", "")
            if not supplied_secret and authorization.casefold().startswith("bearer "):
                supplied_secret = authorization[7:].strip()
            return hmac.compare_digest(supplied_secret, webhook_secret)

        def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, message: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), message % args))

    return UniFiWebhookHandler


def main() -> None:
    try:
        config = Config.from_env()
    except ValueError as error:
        raise SystemExit(f"configuration error: {error}") from error

    store = ClientStore(config.db_path)
    if config.unifi_host:
        unifi = UniFiClient(
            host=config.unifi_host,
            api_key=config.unifi_api_key,
            site=config.unifi_site,
            verify_ssl=config.unifi_verify_ssl,
            timeout_seconds=config.unifi_timeout_seconds,
        )
        try:
            known_clients = unifi.list_known_clients()
        except UniFiError as error:
            raise SystemExit(f"UniFi bootstrap failed; refusing to start without deduplication: {error}") from error
        seeded = store.seed_clients(known_clients)
        print(
            f"Loaded {len(known_clients)} known UniFi clients ({seeded} newly seeded)",
            flush=True,
        )
    notifier = EchoBellClient(
        base_url=config.echobell_base_url,
        direct_key=config.echobell_direct_key,
        notification_type=config.notification_type,
        external_link=config.external_link,
        timeout_seconds=config.echobell_timeout_seconds,
    )
    service = WebhookService(store, notifier)
    handler = make_handler(service, config.webhook_secret, config.max_body_bytes)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    print(f"UniFi webhook listening on http://{config.host}:{config.port}{WEBHOOK_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
