# Device persistence and delivery

## Owner and data path

Node 2 owns durable delivery. A fusion transition receives a stable `event_id`, is serialized, and is committed to the 16-record NVS ring before any network publish. The 64 KiB NVS partition accommodates sixteen 1536-byte payload records plus metadata/page overhead.

```text
fusion transition -> NVS record -> MQTT QoS 1 -> bridge -> FastAPI/SQLite
       retained until exact {"event_id":"...","status":"ACCEPTED"} ACK
```

Topics:

```text
safesense/{device_id}/event
safesense/{device_id}/ack
```

MQTT QoS 1 proves delivery to the broker, not durable backend acceptance. The queue advances only when the JSON ACK is complete, names the current head record exactly, and has status `ACCEPTED`. Malformed, fragmented, mismatched, duplicate, and negative ACKs do not remove data. The API also enforces idempotency on `event_id`, making safe redelivery possible.

Raw CSI is never written to NVS. Only low-frequency state transitions are persisted, limiting flash wear.

## Review demonstration

1. Start Node 2 with the broker offline and cause one transition.
2. Show the queue depth increase and `Persisted` log.
3. Reset Node 2 and show `Restored 1 persistent event(s)`.
4. Start the broker, bridge, and API.
5. Show the matching event and exact ACK, then show queue depth return to zero.

This sequence is host-tested through a portable storage adapter. The same-board reboot and real NVS/MQTT sequence remains a physical-device acceptance gate.
