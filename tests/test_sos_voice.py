import sqlite3
import io
import json
import sys

import pytest

from scripts import sos_voice
from scripts import sos_token_store
from scripts.direct_laptop_receiver import Receiver
from fastapi.testclient import TestClient
from safesense.main import app


def _alert(event_id="tx-real-alert-001", simulated=False):
    return {"event_id": event_id, "room": "laboratory", "channel": "temperature",
            "horizon_minutes": 15, "simulated": simulated}


def _tx(event_id, simulated):
    return {
        "schema_version": 1, "event_id": event_id, "tx_device_id": "safesense-tx-01",
        "sequence": 1, "observed_at": None, "simulated": simulated,
        "bme680": {"sensor_healthy": True, "temperature_c": 23.0,
                   "humidity_pct": 43.0, "pressure_pa": 101300.0,
                   "gas_resistance_ohm": 59000.0, "gas_valid": True,
                   "heat_stable": True},
        "mq135": {"adc_raw": 705, "calibrated": False},
        "gas_risk": "UNAVAILABLE",
        "forecast_alert": {"room": 1, "horizon_minutes": 15, "channel": 0},
    }


def test_real_voice_message_is_once_per_contact_and_synthetic_is_excluded(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sos_voice, "_internet_reachable", lambda: True)
    monkeypatch.setattr(sos_voice, "_render_voice_mp3", lambda alert: b"mp3")
    monkeypatch.setattr(sos_voice, "_send_voice",
                        lambda config, chat, audio, alert: calls.append((chat, audio)) or len(calls))
    config = sos_voice.VoiceConfig("1234:" + "x" * 25, ("12345678", "87654321"))
    journal = tmp_path / "sos.db"
    assert sos_voice.dispatch(_alert(simulated=True), journal, config)["messages_sent"] == 0
    assert not journal.exists()
    assert sos_voice.dispatch(_alert(), journal, config)["messages_sent"] == 2
    assert sos_voice.dispatch(_alert(), journal, config)["messages_sent"] == 0
    assert calls == [("12345678", b"mp3"), ("87654321", b"mp3")]
    rows = sos_voice.status(journal, "tx-real-alert-001")
    assert {row["state"] for row in rows} == {"ACCEPTED_BY_TELEGRAM"}
    with sqlite3.connect(journal) as db:
        stored = str(db.execute("SELECT * FROM voice_messages").fetchall())
    assert "12345678" not in stored and "87654321" not in stored


def test_forecast_scenario_voice_uses_context_and_keeps_source(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(sos_voice.VoiceConfig, "from_environment", classmethod(
        lambda cls: sos_voice.VoiceConfig("1234:" + "x" * 25, ("12345678",))))
    monkeypatch.setattr(sos_voice, "dispatch_scenario_voice",
                        lambda alert, database, config: sent.append(alert) or
                        {"state": "PROCESSED", "messages_sent": 1})
    with TestClient(app) as client:
        denied = client.post("/api/v1/forecast/voice-scenario",
                             json={"scenario": "freezer_rebound", "minute": 82, "seed": 17})
        assert denied.status_code == 403
        response = client.post("/api/v1/forecast/voice-scenario",
                               headers={"X-SafeSense-Control": "dashboard"},
                               json={"scenario": "freezer_rebound", "minute": 82, "seed": 17})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "SYNTHETIC_FORECAST_SCENARIO"
    assert body["messages_sent"] == 1
    assert sent[0]["simulated"] is True and sent[0]["scenario_voice"] is True
    assert sent[0]["horizon_minutes"] == 25
    assert "Inspect compressor cycling and door traffic" in body["message"]
    assert "25 minutes" in body["message"]


def test_scenario_voice_cannot_enter_real_alert_dispatch(tmp_path):
    alert = {**_alert(simulated=True), "scenario_voice": True}
    assert sos_voice.dispatch(alert, tmp_path / "sos.db")["state"] == "SKIPPED_UNVERIFIED_ORIGIN"
    assert not (tmp_path / "sos.db").exists()


def test_receiver_queues_real_alert_after_storage_and_never_queues_demo(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(sos_voice, "dispatch",
                        lambda alert, database: sent.append(alert["event_id"])
                        or {"state": "PROCESSED", "messages_sent": 1})
    receiver = Receiver(tmp_path / "events.db", "http://127.0.0.1:1",
                        sos_voice=True, sos_database=tmp_path / "sos.db")
    receiver.accept(_tx("tx-real-alert-002", False), speak_alert=False)
    receiver.accept(_tx("tx-demo-alert-003", True), speak_alert=False)
    with sqlite3.connect(receiver.database) as db:
        pending = dict(db.execute("SELECT event_id,sos_pending FROM events"))
    assert pending == {"tx-real-alert-002": 1, "tx-demo-alert-003": 0}
    assert receiver.dispatch_sos_once() == 1
    assert receiver.dispatch_sos_once() == 0
    assert sent == ["tx-real-alert-002"]


def test_receiver_retains_pending_alert_when_internet_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(sos_voice, "dispatch",
                        lambda alert, database: {"state": "DEFERRED_OFFLINE", "messages_sent": 0})
    receiver = Receiver(tmp_path / "events.db", "http://127.0.0.1:1", sos_voice=True)
    receiver.accept(_tx("tx-offline-alert-004", False), speak_alert=False)
    receiver.dispatch_sos_once()
    with sqlite3.connect(receiver.database) as db:
        assert db.execute("SELECT sos_pending FROM events WHERE event_id='tx-offline-alert-004'").fetchone() == (1,)


def test_ambiguous_send_is_recorded_without_automatic_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(sos_voice, "_internet_reachable", lambda: True)
    monkeypatch.setattr(sos_voice, "_render_voice_mp3", lambda alert: b"mp3")
    def timeout(*_):
        raise TimeoutError("after request")
    monkeypatch.setattr(sos_voice, "_send_voice", timeout)
    config = sos_voice.VoiceConfig("1234:" + "x" * 25, ("12345678",))
    journal = tmp_path / "sos.db"
    assert sos_voice.dispatch(_alert(), journal, config)["messages_sent"] == 0
    assert sos_voice.status(journal, "tx-real-alert-001")[0]["state"] == "OUTCOME_UNKNOWN"
    assert sos_voice.dispatch(_alert(), journal, config)["state"] == "DUPLICATE"


def test_offline_alert_waits_without_reserving_or_sending(tmp_path, monkeypatch):
    monkeypatch.setattr(sos_voice, "_internet_reachable", lambda: False)
    config = sos_voice.VoiceConfig("1234:" + "x" * 25, ("12345678",))
    journal = tmp_path / "sos.db"
    assert sos_voice.dispatch(_alert(), journal, config)["state"] == "DEFERRED_OFFLINE"
    assert not journal.exists()


def test_telegram_request_contains_voice_file_and_only_selected_chat(monkeypatch):
    requests = []
    class Response(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *_):
            self.close()
    def fake_urlopen(request, timeout):
        requests.append(request)
        return Response(json.dumps({"ok": True, "result": {"message_id": 42}}).encode())
    monkeypatch.setattr(sos_voice, "urlopen", fake_urlopen)
    config = sos_voice.VoiceConfig("1234:" + "x" * 25, ("12345678",))
    assert sos_voice._send_voice(config, "12345678", b"ID3fake", _alert()) == 42
    request = requests[0]
    assert request.full_url.endswith("/sendVoice")
    assert b'name="chat_id"\r\n\r\n12345678' in request.data
    assert b'name="voice"; filename="alert.mp3"' in request.data
    assert b"ID3fake" in request.data


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_windows_token_store_round_trip_keeps_plaintext_out_of_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SAFESENSE_TELEGRAM_BOT_TOKEN", raising=False)
    token = "123456:" + "A" * 30
    path = tmp_path / "bot.dpapi"
    sos_token_store.store_token(token, path)
    assert token not in path.read_text(encoding="ascii")
    assert sos_token_store.load_token(path) == token


@pytest.mark.skipif(sys.platform != "win32", reason="Windows voice support")
def test_saved_contact_configuration_loads_without_environment(tmp_path, monkeypatch):
    path = tmp_path / "contacts.json"
    path.write_text('{"chat_ids":["12345678"]}', encoding="utf-8")
    monkeypatch.setattr(sos_voice, "CONTACT_FILE", path)
    monkeypatch.setenv("SAFESENSE_TELEGRAM_BOT_TOKEN", "123456:" + "A" * 30)
    monkeypatch.delenv("SAFESENSE_SOS_CHAT_IDS", raising=False)
    assert sos_voice.VoiceConfig.from_environment().chat_ids == ("12345678",)
