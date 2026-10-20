import base64
import json

from scripts import csi_count_receiver


def test_receiver_discards_malformed_csi_before_it_can_poison_a_batch():
    valid_payload = base64.b64encode(bytes([3, 4] * 50)).decode()
    valid = f"WISDOM_CSI,1,1,1000000,-42,0,0,{valid_payload}"
    malformed = "WISDOM_CSI,1,2,1040000,-42,0,0,not-base64"
    assert csi_count_receiver.validated_csi_line(valid.encode() + b"\n") == valid
    assert csi_count_receiver.validated_csi_line(malformed.encode() + b"\n") is None


def test_receiver_extracts_only_matching_persisted_sensor_event():
    tx = {"schema_version": 1, "event_id": "tx-test-12345678",
          "tx_device_id": "safesense-tx-01", "sequence": 4,
          "bme680": {"sensor_healthy": True, "temperature_c": 30.4,
                     "humidity_pct": 73.8, "pressure_pa": 97847.5,
                     "gas_resistance_ohm": 3954, "gas_valid": True,
                     "heat_stable": True},
          "mq135": {"adc_raw": 0}, "gas_risk": "UNAVAILABLE"}
    line = f'I (1234) safesense_tx: Persisted event=tx-test-12345678 pending=2 JSON={json.dumps(tx)}'
    assert csi_count_receiver.parse_persisted_sensor_line(line.encode()) == tx
    sample_line = f'I (1234) safesense_tx: Sensor sample event=tx-test-12345678 JSON={json.dumps(tx)}'
    assert csi_count_receiver.parse_persisted_sensor_line(sample_line.encode()) == tx
    assert csi_count_receiver.parse_persisted_sensor_line(
        line.replace("event=tx-test-12345678", "event=tx-other-12345678").encode()) is None
    assert csi_count_receiver.parse_persisted_sensor_line(b"WISDOM_CSI,1,2") is None


def test_noisy_serial_status_can_be_logged_as_ascii():
    raw = b"\xff safesense_tx: noisy line\n"
    message = csi_count_receiver.safe_serial_log(raw)
    assert message.startswith("\\xff")
    message.encode("cp1252")
