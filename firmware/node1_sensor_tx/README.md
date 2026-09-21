# Node 1 — BME680 sensor and CSI probe transmitter

Node 1 creates the `SafeSense-V2` SoftAP, samples the BME680 through the
project's custom I2C driver, builds the relative gas-resistance baseline, and
sends checksum-protected environmental snapshots at 50 packets/s after Node 2
registers. The controlled traffic is also the CSI stimulus.

Configure pins, address, AP settings, gas thresholds, and UDP ports with
`idf.py menuconfig`. Set the target before the first build:

```text
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
```

The status LED is on only after a valid environmental read. Gas remains
`UNAVAILABLE` through warm-up or whenever the heater/gas-valid flags fail.
Physical I2C, heater, LED polarity, radio rate, and packet-loss behavior must be
checked on the actual board.
