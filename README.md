# UniFi new-client notifications for EchoBell

This service receives **Client Connected** webhooks from UniFi Network and sends an EchoBell notification only the first time it sees each client MAC address. Later connections from that client are recorded but do not notify again.

The known-client list is stored in SQLite. Keep the Docker volume mounted or all clients will appear new after the database is lost.

For a clean first deployment, configure `UNIFI_HOST` and `UNIFI_API_KEY`. The service then imports UniFi's historical client list before it starts accepting webhooks, so old devices are already known and remain silent.

## Run with Docker Compose

1. Copy the environment template and fill in your [EchoBell Direct](https://echobell.one/) key:

   ```sh
   cp .env.example .env
   ```

2. Start the service:

   ```sh
   docker compose up -d --build
   ```

3. Check it:

   ```sh
   curl http://localhost:8080/health
   ```

The webhook URL is `http://<docker-host>:8080/webhook/unifi`.

A prebuilt multi-architecture image is published at `ghcr.io/sbhhbs/unifi-echobell-webhook:latest`. The production compose file, [compose.portainer.yaml](compose.portainer.yaml), publishes it on host port `8077`.

## Configure UniFi Network

Alarm Manager webhooks require UniFi Network 9.3 or newer. In UniFi Network:

1. Open **Alarm Manager** and create an alarm.
2. Select the **Monitoring > Client Connected** trigger. The exact label may be **WiFi Client Connected** or **Wired Client Connected** on some versions; create both alarms if necessary.
3. Add a **Webhook** action using `POST` and set the URL to `http://<docker-host>:8080/webhook/unifi`.
4. Use JSON content and add `X-Webhook-Secret: <your WEBHOOK_SECRET>` if you configured the recommended secret.
5. Test the webhook from UniFi.

UniFi's [Alarm Manager guide](https://help.ui.com/hc/en-us/articles/27721287753239-UniFi-Alarm-Manager-Customize-Alerts-Integrations-and-Automations-Across-UniFi) describes the alarm and webhook setup. Its [system-log reference](https://help.ui.com/hc/en-us/articles/33349041044119-UniFi-System-Logs-SIEM-Integration) lists the client fields used by the parser.

If UniFi does not include a client MAC in its default body, set custom JSON containing at least that field, for example:

```json
{
  "eventName": "Client Connected",
  "clientMac": "aa:bb:cc:dd:ee:ff",
  "clientHostname": "phone",
  "clientIp": "192.168.1.25",
  "networkName": "LAN",
  "wifiName": "Home"
}
```

The parser also accepts nested objects, different capitalization, `macAddress`, and CEF-style keys such as `UNIFIclientMac`.

## Test the endpoint manually

```sh
curl -X POST http://localhost:8080/webhook/unifi \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: replace-with-a-long-random-value' \
  -d '{
    "eventName": "WiFi Client Connected",
    "clientMac": "aa:bb:cc:dd:ee:ff",
    "clientHostname": "phone",
    "clientIp": "192.168.1.25",
    "wifiName": "Home"
  }'
```

The first request returns `"action":"notified"`; repeats return `"action":"ignored"` and `"reason":"known_client"`.

## Behavior and configuration

- A client is new the first time this service observes its normalized MAC address. Without UniFi bootstrap credentials, existing clients are learned as they connect after initial deployment.
- When UniFi bootstrap credentials are configured, historical clients are seeded first and do not generate a one-time notification after deployment. Startup fails closed if the historical list cannot be loaded, preventing accidental alert floods.
- Explicit disconnect events are ignored. This endpoint is intended only for UniFi Client Connected alarms.
- Set `ALWAYS_NOTIFY=true` temporarily to send EchoBell for every valid connection webhook, including known clients. Disconnect events remain ignored.
- The client is recorded before EchoBell is called. This gives at-most-once notification attempts: a failed/ambiguous EchoBell delivery is not retried when UniFi repeats the webhook, avoiding duplicate alerts.
- To forget all clients, stop the container and remove the `unifi-webhook-data` volume. The next connection from every client will then be considered new.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ECHOBELL_DIRECT_KEY` | required | EchoBell Direct key |
| `WEBHOOK_SECRET` | empty | Optional `X-Webhook-Secret` or Bearer token required from UniFi |
| `ECHOBELL_NOTIFICATION_TYPE` | `time-sensitive` | `active`, `time-sensitive`, or `calling` |
| `ECHOBELL_EXTERNAL_LINK` | empty | Optional notification tap URL |
| `ECHOBELL_TIMEOUT_SECONDS` | `5` | EchoBell request timeout |
| `ECHOBELL_DIRECT_BASE_URL` | `https://hook.echobell.one/d/` | Override for testing |
| `DB_PATH` | `/data/unifi-webhook.sqlite3` | Persistent SQLite path |
| `HOST` | `0.0.0.0` | Listen address |
| `PORT` | `8080` | Listen port |
| `MAX_BODY_BYTES` | `1048576` | Maximum webhook body size |
| `ALWAYS_NOTIFY` | `false` | Send every valid connection event instead of only new clients |
| `UNIFI_HOST` | empty | Optional UniFi console URL used to seed historical clients |
| `UNIFI_API_KEY` | empty | UniFi Network integration API key; required with `UNIFI_HOST` |
| `UNIFI_SITE` | `default` | UniFi site name used for bootstrap |
| `UNIFI_VERIFY_SSL` | `true` | Verify the UniFi console TLS certificate |
| `UNIFI_TIMEOUT_SECONDS` | `15` | UniFi bootstrap request timeout |

## Local development

```sh
poetry install
poetry run python -m unittest discover -v
ECHOBELL_DIRECT_KEY=your-key DB_PATH=/tmp/unifi-webhook.sqlite3 \
  poetry run python -m unifi_webhook
```
