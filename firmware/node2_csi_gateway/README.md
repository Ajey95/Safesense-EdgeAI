# Node 2 — CSI receiver and safety gateway

Node 2 joins Node 1's SoftAP, registers its UDP endpoint, validates every
versioned/CRC-protected environmental probe, captures ESP32-S3 CSI, constructs
100-by-48 feature windows, and runs deterministic fusion. A released INT8 model
is optional; the default stub returns `UNKNOWN` because the current candidate
did not pass the release gate.

State transitions are stored in a 16-record NVS queue before MQTT QoS 1
publish. Only an application ACK containing the exact event ID and
`"status":"ACCEPTED"` advances the queue. Wrong, duplicate, fragmented, or
malformed ACKs leave the record intact.

The app uses a 64 KiB NVS partition so all 16 maximum-size queue records fit
with NVS metadata and page overhead.

Configure SoftAP credentials, laptop broker URI, pins/polarity, active versus
passive buzzer, freshness windows, and confidence policy with
`idf.py menuconfig`, then build with target `esp32s3`.

Physical CSI capture, reboot persistence, broker delivery, LED polarity,
buzzer mode, memory use, and inference latency remain device acceptance tests.
