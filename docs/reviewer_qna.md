# SafeSense reviewer Q&A

## Custom library

**What makes the BME680 library custom?**

The project implements the sensor register protocol, chip-ID validation, Bosch calibration-byte decoding, compensation equations, heater settings, forced-mode sequence, and validation itself. ESP-IDF supplies only the generic I2C bus calls. No Bosch runtime driver or BSEC library is linked.

**How do you prove the equations work without hardware?**

Fixed raw/calibration vectors verify decoding, compensation, range handling, and invalid inputs on the host. That proves deterministic software behavior, not the electrical bus or physical sensor accuracy; those remain device tests.

**Is the gas value an IAQ score or ppm?**

No. It is gas resistance in ohms. SafeSense uses a relative ratio against a warmed clean-air baseline. It does not identify a gas or claim BSEC IAQ, ppm, or certification.

## Persistence and communication

**What survives reboot?**

Up to sixteen unacknowledged transition records plus queue metadata are stored in Node 2 NVS. Startup validates and restores them. Corrupt metadata causes a visible startup failure rather than silent erasure.

**Why is MQTT QoS 1 not enough?**

It confirms broker receipt, not successful API validation and SQLite storage. SafeSense waits for an application ACK with the exact `event_id` and `ACCEPTED` state.

**What if the same MQTT message is delivered twice?**

The backend treats `event_id` as idempotent and returns the prior accepted result. The queue removes only its current head, so an old or mismatched ACK cannot skip records.

**What breaks first during a long outage?**

The bounded 16-record NVS queue fills. The node reports the failure and keeps existing evidence rather than overwriting it. Production sizing or flash-friendly external storage would be needed for longer outages.

## CSI and TinyML

**What preprocessing runs at the edge?**

The Wi-Fi callback copies fixed-size CSI data into a queue. A worker rejects invalid frames, converts interleaved imaginary/real bytes to amplitude, retains 48 data subcarriers in the trained order, and accumulates 100 frames.

**Why not run the current INT8 model?**

It achieved about 0.326 macro-F1 on an untouched real room, below the 0.80 gate. Enabling it would turn weak evidence into a misleading product claim. The adapter therefore returns `UNKNOWN` until a target-room model passes leakage, accuracy, quantization, memory, and latency checks.

**Does synthetic data solve the domain problem?**

It helps regularize training but does not replace real held-out target-room data. The existing real-plus-physics-synthetic experiment still failed to generalize, so model release remains blocked.

## Fusion and safety

**Can missing CSI suppress an alarm?**

No. Environmental `CRITICAL` has highest priority and becomes `INCIDENT` even when CSI is missing. Missing CSI only removes human-context confidence.

**Is `UNKNOWN` the same as an empty room?**

No. `VACANT` is a model class supported by evidence; `UNKNOWN` means insufficient evidence. Treating unknown as vacant would be an unsafe data substitution.

**Why use deterministic fusion?**

The priority table is inspectable, testable, and reproducible. It prevents the probabilistic model from owning the safety verdict.

**What happens if the laptop or broker fails?**

Node 2 continues local fusion and LED/buzzer output, while state transitions queue in NVS. Dashboard freshness/connectivity degrades instead of showing a false healthy state.

## Dashboard and evidence

**Why are some fields `UNAVAILABLE` or `PENDING DEVICE TEST`?**

The dashboard separates observed evidence from assumptions. No hardware value is fabricated while the boards are unavailable.

**How is dashboard text kept safe?**

Dynamic labels are validated or HTML-escaped. A contract test requires all rubric sections, honest unavailable values, and excludes internal development/setup language from the live view.

**What is complete today?**

Portable firmware logic, two target application sources, backend, persistence contract, simulator, dashboard, and automated tests are complete. ESP-IDF builds and physical electrical/radio/reboot proof wait for the actual hardware and toolchain.

**Is this production ready?**

No. It is a review-ready academic prototype. Production use would require calibrated hazard criteria, target-room CSI data, security hardening, long-duration reliability tests, electromagnetic/radio validation, and relevant safety certification.
