import subprocess
import sys
import socket
import pytest

from fastapi.testclient import TestClient

from safesense import live_api
from safesense.main import app
from scripts import wifi_demo_session
from scripts import bt_alert_receiver
from scripts import transport_handoff, transport_events


@pytest.fixture(autouse=True)
def isolated_transport_history(monkeypatch, tmp_path):
    monkeypatch.setattr(transport_events, "HISTORY", tmp_path / "transport_events.jsonl")


def test_current_ssid_uses_ssid_field_not_bssid(monkeypatch):
    sample = " State : connected\n SSID : Amrita\n AP BSSID : 30:86:2d:91:5b:b0\n"
    monkeypatch.setattr(wifi_demo_session.subprocess, "run",
                        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, sample, ""))
    assert wifi_demo_session.current_ssid() == "Amrita"


def test_missing_esp32_ap_fails_without_attempting_association(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0,
                                           "SSID 1 : Amrita\n", "")
    monkeypatch.setattr(wifi_demo_session.subprocess, "run", fake_run)
    connected, reason = wifi_demo_session.connect("SafeSense-TX-Laptop")
    assert connected is False
    assert "not visible" in reason
    assert all("connect" not in command for command in calls)


def test_esp32_ap_scan_retries_before_association(monkeypatch):
    scans = 0
    calls = []
    def fake_run(command, **kwargs):
        nonlocal scans
        calls.append(command)
        if "networks" in command:
            scans += 1
            visible = "SSID 1 : Amrita\n" if scans == 1 else "SSID 1 : SafeSense-TX-Laptop\n"
            return subprocess.CompletedProcess(command, 0, visible, "")
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(wifi_demo_session.subprocess, "run", fake_run)
    monkeypatch.setattr(wifi_demo_session.time, "sleep", lambda *_: None)
    monkeypatch.setattr(wifi_demo_session, "current_ssid", lambda: wifi_demo_session.TARGET)
    connected, reason = wifi_demo_session.connect(wifi_demo_session.TARGET)
    assert connected and reason is None
    assert scans == 2
    assert any("connect" in command for command in calls)


def test_esp32_ap_retries_slow_windows_association(monkeypatch):
    connects = 0
    clock = 0.0
    def fake_run(command, **kwargs):
        nonlocal connects
        if "connect" in command:
            connects += 1
        if "networks" in command:
            return subprocess.CompletedProcess(command, 0, "SSID 1 : SafeSense-TX-Laptop\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")
    def fake_monotonic():
        nonlocal clock
        clock += 1
        return clock
    monkeypatch.setattr(wifi_demo_session.subprocess, "run", fake_run)
    monkeypatch.setattr(wifi_demo_session.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(wifi_demo_session.time, "sleep", lambda *_: None)
    monkeypatch.setattr(wifi_demo_session, "current_ssid",
                        lambda: wifi_demo_session.TARGET if connects >= 2 else "Amrita")
    connected, reason = wifi_demo_session.connect(wifi_demo_session.TARGET)
    assert connected and reason is None and connects == 2


def test_wifi_demo_control_is_local_and_bounded(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(wifi_demo_session, "STATUS", tmp_path / "status.json")
    monkeypatch.setattr(wifi_demo_session, "CANCEL", tmp_path / "cancel.txt")
    monkeypatch.setattr(transport_handoff, "REQUEST", tmp_path / "request.json")
    monkeypatch.setattr(wifi_demo_session, "current_ssid", lambda: "Amrita")
    monkeypatch.setattr(live_api, "_launch_wifi_session", lambda *args: launched.append(args))
    monkeypatch.setattr(live_api, "_ensure_bluetooth_receiver", lambda db: None)
    with TestClient(app) as client:
        assert client.post("/api/v1/live/direct/wifi-session").status_code == 403
        response = client.post("/api/v1/live/direct/wifi-session",
                               headers={"X-SafeSense-Control": "dashboard"})
        assert response.status_code == 200
        assert response.json()["duration_seconds"] == 120
        assert len(launched) == 1
        assert launched[0][:2] == ("--duration", "120")
        assert launched[0][2] == "--session-id"
        history = client.get("/api/v1/live/direct/wifi-session").json()["events"]
        assert history[0]["state"] == "STARTING"
        assert client.post("/api/v1/live/direct/wifi-session/restore",
                           headers={"X-SafeSense-Control": "dashboard"}).json()["accepted"]
        assert wifi_demo_session.CANCEL.read_text(encoding="ascii") == launched[0][3]


def test_wifi_demo_restores_amrita_even_if_esp32_ap_cannot_connect(monkeypatch):
    calls = []
    statuses = []
    def fake_connect(profile, **_):
        calls.append(profile)
        return (profile == "Amrita", None if profile == "Amrita" else "AP unavailable")
    monkeypatch.setattr(wifi_demo_session, "connect", fake_connect)
    monkeypatch.setattr(wifi_demo_session, "prepare_ap_scan", lambda: (True, None))
    monkeypatch.setattr(wifi_demo_session, "restore_auto", lambda: None)
    monkeypatch.setattr(transport_handoff, "request_reconnect", lambda: {})
    monkeypatch.setattr(wifi_demo_session, "current_ssid", lambda: "Amrita")
    monkeypatch.setattr(wifi_demo_session, "write_status",
                        lambda state, **details: statuses.append((state, details)))
    monkeypatch.setattr(sys, "argv", ["wifi_demo_session", "--duration", "20"])
    wifi_demo_session.main()
    assert calls == ["SafeSense-TX-Laptop", "Amrita"]
    assert statuses[-1][0] == "RESTORED"
    assert statuses[-1][1]["ap_connected"] is False


def test_manual_return_cancels_active_session_before_ap_association(monkeypatch, tmp_path):
    cancel = tmp_path / "cancel.txt"
    monkeypatch.setattr(wifi_demo_session, "CANCEL", cancel)
    monkeypatch.setattr(wifi_demo_session, "prepare_ap_scan", lambda: (True, None))
    monkeypatch.setattr(wifi_demo_session, "restore_auto", lambda: None)
    monkeypatch.setattr(transport_handoff, "request_reconnect", lambda: {})
    monkeypatch.setattr(wifi_demo_session, "current_ssid", lambda: "Amrita")
    calls = []
    statuses = []
    def fake_connect(profile, **_):
        calls.append(profile)
        return True, None
    def fake_status(state, **details):
        statuses.append(state)
        if state == "CONNECTING":
            cancel.write_text("session-1", encoding="ascii")
    monkeypatch.setattr(wifi_demo_session, "connect", fake_connect)
    monkeypatch.setattr(wifi_demo_session, "write_status", fake_status)
    monkeypatch.setattr(sys, "argv", ["wifi_demo_session", "--duration", "20",
                                    "--session-id", "session-1"])
    wifi_demo_session.main()
    assert calls == ["Amrita"]
    assert statuses[-1] == "RESTORED"


def test_manual_return_endpoint_cancels_connecting_session_even_on_amrita(monkeypatch, tmp_path):
    cancel = tmp_path / "cancel.txt"
    monkeypatch.setattr(wifi_demo_session, "CANCEL", cancel)
    monkeypatch.setattr(transport_handoff, "REQUEST", tmp_path / "request.json")
    monkeypatch.setattr(live_api, "_ensure_bluetooth_receiver", lambda db: None)
    monkeypatch.setattr(live_api, "wifi_session_status", lambda: {
        "current_ssid": "Amrita", "restore_profile": "Amrita", "on_safesense_ap": False,
        "session": {"state": "CONNECTING", "session_id": "session-2"},
    })
    launched = []
    monkeypatch.setattr(live_api, "_launch_wifi_session", lambda *args: launched.append(args))
    with TestClient(app) as client:
        result = client.post("/api/v1/live/direct/wifi-session/restore",
                             headers={"X-SafeSense-Control": "dashboard"}).json()
    assert result["accepted"] is True and not result.get("already_restored")
    assert cancel.read_text(encoding="ascii") == "session-2"
    assert launched == [("--restore-only",)]


def test_bluetooth_silent_link_reopens_only_after_idle_on_amrita():
    assert not bt_alert_receiver.idle_reconnect_due(0, 29, "Amrita")
    assert bt_alert_receiver.idle_reconnect_due(0, 31, "Amrita")
    assert not bt_alert_receiver.idle_reconnect_due(0, 31, "SafeSense-TX-Laptop")


def test_bluetooth_idle_check_survives_netsh_timeout(monkeypatch):
    def timeout():
        raise subprocess.TimeoutExpired("netsh", 10)
    monkeypatch.setattr(bt_alert_receiver, "current_ssid", timeout)
    assert bt_alert_receiver.network_for_idle_check() == "Amrita"


def test_wifi_probe_recovers_from_one_transient_socket_error(monkeypatch):
    class FakeSocket:
        attempts = 0
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def sendto(self, *_):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("route not ready")
    sender = FakeSocket()
    monkeypatch.setattr(wifi_demo_session.socket, "socket", lambda *_: sender)
    monkeypatch.setattr(wifi_demo_session, "current_ssid", lambda: wifi_demo_session.TARGET)
    monkeypatch.setattr(wifi_demo_session, "cancel_requested", lambda *_: False)
    sent, errors, reason = wifi_demo_session.run_probe_loop(0.5, "session-3")
    assert sender.attempts >= 2
    assert sent >= 1 and errors == 1 and reason is None


def test_restore_button_requests_bluetooth_even_when_amrita_is_connected(monkeypatch, tmp_path):
    monkeypatch.setattr(transport_handoff, "REQUEST", tmp_path / "request.json")
    monkeypatch.setattr(live_api, "_ensure_bluetooth_receiver", lambda db: None)
    monkeypatch.setattr(live_api, "wifi_session_status", lambda: {
        "current_ssid": "Amrita", "restore_profile": "Amrita", "session": {"state": "RESTORED"}})
    monkeypatch.setattr(live_api, "_launch_wifi_session", lambda *args: (_ for _ in ()).throw(AssertionError(args)))
    with TestClient(app) as client:
        result = client.post("/api/v1/live/direct/wifi-session/restore",
                             headers={"X-SafeSense-Control": "dashboard"}).json()
    assert result["accepted"] is True and result["already_restored"] is True
    assert transport_handoff.read_record(transport_handoff.REQUEST)["request_id"] == result["request_id"]


def test_transport_history_records_handoff_once_and_ignores_bad_lines(monkeypatch, tmp_path):
    monkeypatch.setattr(transport_handoff, "REQUEST", tmp_path / "request.json")
    monkeypatch.setattr(transport_handoff, "FRAME", tmp_path / "frame.json")
    transport_events.append_event("ON_SAFESENSE_AP", duration_seconds=120)
    requested = transport_handoff.request_reconnect()
    transport_handoff.record_frame("tx-first-packet")
    transport_handoff.record_frame("tx-next-packet")
    with transport_events.HISTORY.open("a", encoding="utf-8") as handle:
        handle.write("broken json\n")
    history = transport_events.recent_events()
    assert [item["state"] for item in history] == [
        "BLUETOOTH_PACKET_STORED", "BLUETOOTH_RECONNECT_REQUESTED", "ON_SAFESENSE_AP"]
    assert history[0]["event_id"] == "tx-first-packet"
    assert history[0]["request_id"] == requested["request_id"]
