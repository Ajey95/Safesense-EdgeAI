import pytest
from pydantic import ValidationError

from scripts.direct_serial_bridge import FIRMWARE_TAG, make_telemetry


def sample():
    return {
        "sample_id": 394, "sensor_status": "OK", "bme_temperature_c": 33.623,
        "bme_humidity_pct": 65.955, "bme_pressure_hpa": 978.009,
        "bme_gas_resistance_ohm": 305607.719, "mq135_adc_raw": 2505,
    }


def test_direct_sample_preserves_real_sensor_units_without_rx_claims():
    event = make_telemetry(sample(), "a1b2c3", "safesense-tx-usb-8c94df901fec")
    assert event.event_id == "usb-a1b2c3-394"
    assert event.firmware_version == FIRMWARE_TAG
    assert event.environment.pressure_pa == pytest.approx(97800.9)
    assert event.environment.gas_adc_raw == 2505
    assert event.environment.heat_stable is False
    assert event.communication is None
    assert event.csi.rx_node == "UNKNOWN"


def test_direct_sample_rejects_bad_status_and_invalid_values():
    broken = sample()
    broken["sensor_status"] = "ERROR"
    with pytest.raises(ValueError):
        make_telemetry(broken, "a1b2c3", "safesense-tx-usb-8c94df901fec")
    broken = sample()
    broken["bme_temperature_c"] = float("nan")
    with pytest.raises(ValueError):
        make_telemetry(broken, "a1b2c3", "safesense-tx-usb-8c94df901fec")
    broken = sample()
    broken["mq135_adc_raw"] = 5000
    with pytest.raises(ValidationError):
        make_telemetry(broken, "a1b2c3", "safesense-tx-usb-8c94df901fec")
