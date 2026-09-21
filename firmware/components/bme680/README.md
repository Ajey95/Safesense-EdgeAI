# SafeSense custom BME680 driver

This component is a from-scratch BME680 driver for the project review. It uses
only fixed-width C types and, in its ESP-IDF adapter, the generic I2C master
API. It does **not** link Bosch BSEC, Bosch's Sensor API, Adafruit, Arduino, or
another sensor library.

The portable core implements the BME680 low-gas-variant compensation path:

- chip ID `0x61` at I2C address `0x76` or `0x77`;
- the 42-byte logical calibration block assembled from `0x89..0xA1`,
  `0xE1..0xF0`, and the heater/range trim registers;
- temperature, pressure, relative-humidity, and gas-resistance compensation;
- heater-resistance and heater-duration register encoding; and
- explicit rejection of missing data, invalid ranges, and invalid primary
  calibration values.

Gas resistance is expressed in ohms. It is not a certified concentration or
an IAQ score; SafeSense applies a separate, transparent relative-baseline
policy in `gas_risk`.

## Formula provenance

Register meanings and equations were derived from the Bosch BME680 datasheet.
The resulting implementation and fixed-vector tests were cross-checked against
Bosch Sensortec's BSD-3-Clause BME68x Sensor API, version 4.4.8. No Bosch source
file is compiled or copied into the firmware.

- Datasheet: <https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme680-ds001.pdf>
- Reference API: <https://github.com/boschsensortec/BME68x_SensorAPI>

The ESP-IDF bus/configuration adapter is documented alongside its header. Host
verification covers the pure compensation core; actual I2C timing, heater
behavior, and sensor accuracy require the physical BME680 acceptance test.
