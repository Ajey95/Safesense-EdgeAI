"""Backend view of physical RX telemetry and locally reported transport receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
import json
import subprocess
import sys
import time
from threading import Lock
from uuid import uuid4
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_session
from .models import BoardQueueStatus, BridgeHeartbeat, DeliveryReceipt, TelemetryEvent
from .queue_status import BoardQueueIn


router = APIRouter(prefix="/api/v1/live", tags=["live hardware"])
FRESH_SECONDS = 45
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BT_RECEIVER_LOG = PROJECT_ROOT / "data/live/bt_receiver_autostart.log"
WIFI_SESSION_LOG = PROJECT_ROOT / "data/live/wifi_demo_session.log"
WIFI_VISIT_SECONDS = 120
_bt_start_lock = Lock()
_bt_last_start = 0.0


class ReceiptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    kind: Literal["BLUETOOTH_STORED", "RX_FORWARD_ACKED"]
    room: str | None = Field(default=None, max_length=80)
    channel: str | None = Field(default=None, max_length=80)
    horizon_minutes: int | None = Field(default=None, ge=5, le=30)
    stored_at_utc: datetime | None = None
    simulated: bool | None = None


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["rx_http_bridge", "bt_alert_receiver"]
    status: Literal["empty", "forwarded", "deferred", "listening", "receipt"]


class FaultIn(BaseModel):
    enabled: bool


class BoardQueueReport(BoardQueueIn):
    laptop_stored_at_utc: datetime


@router.post("/board-queue", status_code=202)
def record_board_queue(report: BoardQueueReport,
                       ingress: str | None = Header(default=None, alias="X-SafeSense-Ingress"),
                       session: Session = Depends(get_session)) -> dict:
    route = {"direct-laptop-receiver": "WIFI",
             "bt-sensor-receiver": "BLUETOOTH"}.get(ingress)
    if route is None:
        raise HTTPException(status_code=403, detail="Wireless receiver required")
    existing = session.get(BoardQueueStatus, report.status_id)
    if existing:
        # A lost Wi-Fi response can make the same board frame arrive by Bluetooth.
        if existing.payload != report.model_dump(mode="json", exclude={"laptop_stored_at_utc"}):
            raise HTTPException(status_code=409, detail="Status ID reused with different data")
        return {"accepted": True, "status_id": report.status_id, "duplicate": True}
    session.add(BoardQueueStatus(
        status_id=report.status_id, device_id=report.device_id, route=route,
        laptop_stored_at=report.laptop_stored_at_utc,
        received_at=datetime.now(timezone.utc),
        payload=report.model_dump(mode="json", exclude={"laptop_stored_at_utc"}),
    ))
    session.commit()
    return {"accepted": True, "status_id": report.status_id, "duplicate": False}


def _local_receiver(path: str, data: dict | None = None) -> dict:
    payload = None if data is None else json.dumps(data).encode("utf-8")
    request = UrlRequest(f"http://127.0.0.1:8765{path}", data=payload,
                         headers={"Content-Type": "application/json",
                                  "X-SafeSense-Control": "dashboard"} if payload else {})
    try:
        with urlopen(request, timeout=2) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error).get("error", str(error))
        except (ValueError, AttributeError):
            detail = str(error)
        raise HTTPException(status_code=error.code, detail=detail) from error
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail=f"Direct laptop receiver unavailable: {error}") from error


@router.get("/direct/status")
def direct_receiver_status() -> dict:
    return _local_receiver("/status")


@router.post("/direct/fault")
def set_direct_fault(change: FaultIn, request: Request,
                     control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Local dashboard control only")
    if control != "dashboard":
        raise HTTPException(status_code=403, detail="Dashboard control header required")
    return _local_receiver("/fault", change.model_dump())


@router.post("/direct/test-alert")
def request_direct_test_alert(request: Request,
                              control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Local dashboard control only")
    if control != "dashboard":
        raise HTTPException(status_code=403, detail="Dashboard control header required")
    return _local_receiver("/test-alert", {})


def _local_control(request: Request, control: str | None) -> None:
    if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"} or control != "dashboard":
        raise HTTPException(status_code=403, detail="Local dashboard control required")


def _launch_wifi_session(*arguments: str) -> None:
    command = [sys.executable, "-m", "scripts.wifi_demo_session", *arguments]
    try:
        WIFI_SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with WIFI_SESSION_LOG.open("ab") as log:
            subprocess.Popen(command, cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as error:
        raise HTTPException(status_code=503, detail=f"Wi-Fi control unavailable: {type(error).__name__}") from error


def _ensure_bluetooth_receiver(session: Session) -> None:
    """Restart a dead listener; its process lock prevents duplicate COM owners."""
    global _bt_last_start
    heartbeat = session.get(BridgeHeartbeat, "bt_alert_receiver")
    if heartbeat and _age_seconds(heartbeat.reported_at, datetime.now(timezone.utc)) < 12:
        return
    with _bt_start_lock:
        now = time.monotonic()
        if now - _bt_last_start < 12:
            return
        BT_RECEIVER_LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            with BT_RECEIVER_LOG.open("ab") as log:
                subprocess.Popen([sys.executable, "-m", "scripts.bt_alert_receiver",
                                  "--port", "COM15", "--sos-voice"],
                                 cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            raise HTTPException(status_code=503, detail=f"Bluetooth receiver unavailable: {type(error).__name__}") from error
        _bt_last_start = now


@router.get("/direct/wifi-session")
def wifi_session_status() -> dict:
    from scripts.wifi_demo_session import STATUS, TARGET, RESTORE, current_ssid
    from scripts.transport_events import recent_events
    saved = {}
    if STATUS.exists():
        try:
            saved = json.loads(STATUS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
    ssid = current_ssid()
    return {"current_ssid": ssid, "on_safesense_ap": ssid == TARGET,
            "restore_profile": RESTORE, "duration_seconds": WIFI_VISIT_SECONDS,
            "session": saved, "events": recent_events()}


@router.post("/direct/wifi-session")
def start_wifi_session(request: Request,
                       control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    _local_control(request, control)
    from scripts.wifi_demo_session import CANCEL, TARGET, RESTORE, write_status
    current = wifi_session_status()
    previous = current["session"]
    if previous.get("state") in {"STARTING", "CONNECTING", "ON_SAFESENSE_AP"}:
        return {"accepted": True, **current}
    if current["current_ssid"] not in {TARGET, RESTORE}:
        raise HTTPException(status_code=409, detail="Connect to Amrita before starting the bounded Wi-Fi demonstration")
    session_id = uuid4().hex
    CANCEL.unlink(missing_ok=True)
    write_status("STARTING", target=TARGET, restore=RESTORE,
                 session_id=session_id, duration_seconds=WIFI_VISIT_SECONDS)
    _launch_wifi_session("--duration", str(WIFI_VISIT_SECONDS), "--session-id", session_id)
    return {"accepted": True, "target": TARGET, "restore": RESTORE,
            "duration_seconds": WIFI_VISIT_SECONDS}


@router.post("/direct/wifi-session/restore")
def restore_wifi_session(request: Request,
                         control: str | None = Header(default=None, alias="X-SafeSense-Control"),
                         db: Session = Depends(get_session)) -> dict:
    _local_control(request, control)
    from scripts.wifi_demo_session import request_cancel
    from scripts.transport_handoff import request_reconnect
    current = wifi_session_status()
    session = current["session"]
    active = session.get("state") in {"STARTING", "CONNECTING", "ON_SAFESENSE_AP"}
    if active and session.get("session_id"):
        request_cancel(session["session_id"])
    _ensure_bluetooth_receiver(db)
    handoff = request_reconnect()
    if current["current_ssid"] == current["restore_profile"] and not active:
        return {"accepted": True, "already_restored": True, **handoff}
    _launch_wifi_session("--restore-only")
    return {"accepted": True, "restoring": current["restore_profile"], **handoff}


@router.get("/direct/transport-handoff")
def transport_handoff_status(db: Session = Depends(get_session)) -> dict:
    from scripts.transport_handoff import REQUEST, FRAME, read_record
    from scripts.wifi_demo_session import RESTORE, current_ssid
    request = read_record(REQUEST)
    frame = read_record(FRAME)
    ssid = current_ssid()
    requested_at = request.get("requested_at_utc")
    received_at = frame.get("received_at_utc")
    event_id = frame.get("event_id")
    try:
        start = datetime.fromisoformat(requested_at) if requested_at else None
        received = datetime.fromisoformat(received_at) if received_at else None
    except (TypeError, ValueError):
        start = received = None
    now = datetime.now(timezone.utc)
    recent_frame = bool(received and _age_seconds(received, now) <= 25)
    after_request = bool(start and received and received > start)
    stored = bool(event_id and db.scalar(select(DeliveryReceipt.id).where(
        DeliveryReceipt.event_id == event_id,
        DeliveryReceipt.kind == "LAPTOP_BT_SENSOR_STORED")))
    ready = ssid == RESTORE and recent_frame and stored and (not start or after_request)
    if ready:
        state = "READY"
    elif start and _age_seconds(start, now) >= 70:
        state = "TIMED_OUT"
    elif start:
        state = "WAITING_WIFI" if ssid != RESTORE else "WAITING_BLUETOOTH"
    else:
        state = "IDLE"
    if state == "WAITING_BLUETOOTH":
        _ensure_bluetooth_receiver(db)
    return {"state": state, "current_ssid": ssid, "request_id": request.get("request_id"),
            "requested_at_utc": requested_at, "latest_bt_event_id": event_id if stored else None,
            "latest_bt_frame_at_utc": received_at if stored else None}


@router.get("/direct")
def direct_laptop_snapshot(session: Session = Depends(get_session)) -> dict:
    def recent_sensor_receipts(kind: str) -> tuple[list[dict], list[dict]]:
        markers = session.scalars(select(DeliveryReceipt).where(
            DeliveryReceipt.kind == kind).order_by(
                desc(DeliveryReceipt.reported_at)).limit(100)).all()
        if not markers:
            return [], []
        telemetry = session.scalars(select(TelemetryEvent).where(
            TelemetryEvent.event_id.in_([marker.event_id for marker in markers]))).all()
        by_id = {row.event_id: row for row in telemetry
                 if row.payload.get("firmware_version") in
                 {"direct-wifi-bme680-mq135", "synthetic-forecast-demo"}}
        rows = [{"event_id": marker.event_id,
                 "receipt_reported_at": marker.reported_at.isoformat(),
                 "environment": by_id[marker.event_id].payload.get("environment") or {},
                 "test_alert": by_id[marker.event_id].payload.get("firmware_version") ==
                     "synthetic-forecast-demo"}
                for marker in markers if marker.event_id in by_id]
        return rows[:8], [row for row in rows if not row["test_alert"]][:8]

    now = datetime.now(timezone.utc)
    queue_rows = []
    for route in ("WIFI", "BLUETOOTH"):
        queue_rows.extend(session.scalars(select(BoardQueueStatus).where(
            BoardQueueStatus.route == route).order_by(
                desc(BoardQueueStatus.laptop_stored_at)).limit(3)).all())
    queue_rows.sort(key=lambda row: row.laptop_stored_at, reverse=True)
    queue_history = [{**row.payload, "route": row.route,
                      "laptop_stored_at_utc": row.laptop_stored_at.isoformat(),
                      "backend_stored_at_utc": row.received_at.isoformat(),
                      "age_seconds": _age_seconds(row.laptop_stored_at, now)}
                     for row in queue_rows]
    board_queue = queue_history[0] if queue_history else None
    queue_proof = None
    if board_queue and board_queue["last_acked_id"]:
        event_id = board_queue["last_acked_id"]
        telemetry_row = session.scalar(select(TelemetryEvent).where(TelemetryEvent.event_id == event_id))
        receipt_kind = ("LAPTOP_WIFI_STORED" if board_queue["last_ack_route"] == "WIFI"
                        else "LAPTOP_BT_SENSOR_STORED")
        receipt_row = session.scalar(select(DeliveryReceipt).where(
            DeliveryReceipt.event_id == event_id, DeliveryReceipt.kind == receipt_kind))
        queue_proof = {"event_id": event_id,
                       "receiver_receipt_at": receipt_row.reported_at.isoformat() if receipt_row else None,
                       "backend_stored_at": telemetry_row.received_at.isoformat() if telemetry_row else None,
                       "route": board_queue["last_ack_route"]}

    wifi_receipts, wifi_sensor_deliveries = recent_sensor_receipts("LAPTOP_WIFI_STORED")
    bluetooth_receipts, bluetooth_sensor_deliveries = recent_sensor_receipts(
        "LAPTOP_BT_SENSOR_STORED")

    markers = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.kind.in_(("LAPTOP_WIFI_STORED", "LAPTOP_BT_SENSOR_STORED",
                                 "LAPTOP_USB_SENSOR_STORED"))).order_by(
        desc(DeliveryReceipt.reported_at)).limit(300)).all()
    route_by_id = {}
    marker_by_id = {}
    for marker in markers:
        route = {"LAPTOP_BT_SENSOR_STORED": "DIRECT_BLUETOOTH",
                 "LAPTOP_USB_SENSOR_STORED": "USB_SERIAL",
                 "LAPTOP_WIFI_STORED": "DIRECT_WIFI"}[marker.kind]
        if marker.event_id not in route_by_id or route_by_id[marker.event_id] == "USB_SERIAL" and route != "USB_SERIAL":
            route_by_id[marker.event_id] = route
            marker_by_id[marker.event_id] = marker
    ids = list(route_by_id)
    rows = session.scalars(select(TelemetryEvent).where(
        TelemetryEvent.event_id.in_(ids)).order_by(
        desc(TelemetryEvent.received_at)).limit(300)).all() if ids else []
    direct = [row for row in rows if row.payload.get("firmware_version") in
              {"direct-wifi-bme680-mq135", "synthetic-forecast-demo"}]
    direct.sort(key=lambda row: marker_by_id[row.event_id].reported_at, reverse=True)
    direct = direct[:30]
    usb_receipts = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.event_id.in_([row.event_id for row in direct]),
        DeliveryReceipt.kind == "LAPTOP_USB_SENSOR_STORED")).all() if direct else []
    usb_seen_at = {receipt.event_id: receipt.reported_at.isoformat()
                   for receipt in usb_receipts}
    receipts = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.event_id.in_([row.event_id for row in direct]),
        DeliveryReceipt.kind == "BLUETOOTH_STORED")).all() if direct else []
    bt_ids = {receipt.event_id for receipt in receipts
              if receipt.details.get("reporter") == "bt-alert-receiver"}
    recent_bt = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.kind == "BLUETOOTH_STORED").order_by(
        desc(DeliveryReceipt.reported_at)).limit(30)).all()
    wifi_ids = {row.event_id for row in direct
                if route_by_id.get(row.event_id) == "DIRECT_WIFI"}
    return {"as_of": datetime.now(timezone.utc).isoformat(),
        "board_queue": board_queue, "board_queue_history": queue_history,
        "board_queue_proof": queue_proof,
        "wifi_receipts": wifi_receipts,
        "bluetooth_receipts": bluetooth_receipts,
        "wifi_sensor_deliveries": wifi_sensor_deliveries,
        "bluetooth_sensor_deliveries": bluetooth_sensor_deliveries,
        "events": [
        {"event_id": row.event_id, "device_id": row.device_id,
         "backend_stored_at": row.received_at.isoformat(),
         "wireless_received_at": marker_by_id[row.event_id].reported_at.isoformat()
             if route_by_id[row.event_id] != "USB_SERIAL" else None,
         "sample_observed_at": marker_by_id[row.event_id].details.get("captured_at_utc")
             if route_by_id[row.event_id] != "USB_SERIAL" else None,
         "capture_age_ms": marker_by_id[row.event_id].details.get("capture_age_ms")
             if route_by_id[row.event_id] != "USB_SERIAL" else None,
         "usb_sample_seen_at": usb_seen_at.get(row.event_id),
         "environment": row.payload.get("environment") or {},
         "bluetooth_stored": row.event_id in bt_ids,
         "test_alert": row.payload.get("firmware_version") == "synthetic-forecast-demo",
         "route": route_by_id.get(row.event_id, "UNKNOWN")}
        for row in direct],
        "bluetooth_only": [
            {"event_id": receipt.event_id,
             "reported_at": receipt.reported_at.isoformat(),
             "details": receipt.details}
            for receipt in recent_bt if receipt.event_id not in wifi_ids
            and receipt.details.get("reporter") == "bt-alert-receiver"][:10]}


@router.post("/receipts", status_code=202)
def record_receipt(receipt: ReceiptIn, session: Session = Depends(get_session),
                   ingress: str | None = Header(default=None, alias="X-SafeSense-Ingress")) -> dict:
    required = "bt-alert-receiver" if receipt.kind == "BLUETOOTH_STORED" else "rx-http-bridge"
    if ingress != required:
        raise HTTPException(status_code=403, detail="Receipt reporter mismatch")
    existing = session.scalar(select(DeliveryReceipt).where(
        DeliveryReceipt.event_id == receipt.event_id,
        DeliveryReceipt.kind == receipt.kind,
    ))
    if existing:
        return {"event_id": receipt.event_id, "kind": receipt.kind, "accepted": True, "duplicate": True}
    details = receipt.model_dump(mode="json", exclude={"event_id", "kind"}, exclude_none=True)
    details["reporter"] = ingress
    session.add(DeliveryReceipt(event_id=receipt.event_id, kind=receipt.kind,
                                reported_at=datetime.now(timezone.utc), details=details))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return {"event_id": receipt.event_id, "kind": receipt.kind, "accepted": True, "duplicate": True}
    return {"event_id": receipt.event_id, "kind": receipt.kind, "accepted": True, "duplicate": False}


@router.post("/heartbeat", status_code=202)
def record_heartbeat(heartbeat: HeartbeatIn, session: Session = Depends(get_session),
                     ingress: str | None = Header(default=None, alias="X-SafeSense-Ingress")) -> dict:
    required = "bt-alert-receiver" if heartbeat.name == "bt_alert_receiver" else "rx-http-bridge"
    if ingress != required:
        raise HTTPException(status_code=403, detail="Heartbeat reporter mismatch")
    row = session.get(BridgeHeartbeat, heartbeat.name)
    if row is None:
        row = BridgeHeartbeat(name=heartbeat.name, reported_at=datetime.now(timezone.utc),
                              status=heartbeat.status)
        session.add(row)
    else:
        row.reported_at = datetime.now(timezone.utc)
        row.status = heartbeat.status
    session.commit()
    return {"accepted": True, "name": heartbeat.name}


def _age_seconds(moment: datetime, now: datetime) -> float:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (now - moment).total_seconds())


def _physical_event(row: TelemetryEvent) -> bool:
    payload = row.payload or {}
    communication = payload.get("communication") or {}
    return (communication.get("tx_rx_transport") == "HTTP POST"
            and communication.get("rx_queue_persisted") is True
            and payload.get("firmware_version") != "synthetic-forecast-demo"
            and not payload.get("simulated"))


@router.get("")
def live_snapshot(session: Session = Depends(get_session)) -> dict:
    now = datetime.now(timezone.utc)
    # The backend only calls these RX-reported, never board-attested. Exclude
    # serial synthetic replay records from the physical monitor.
    markers = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.kind == "RX_BRIDGE_INGEST").order_by(
        desc(DeliveryReceipt.reported_at)).limit(500)).all()
    bridge_ingested = {receipt.event_id for receipt in markers}
    candidate_rows = session.scalars(select(TelemetryEvent).where(
        TelemetryEvent.event_id.in_(bridge_ingested)).order_by(
        desc(TelemetryEvent.received_at)).limit(500)).all() if bridge_ingested else []
    telemetry = [row for row in candidate_rows
                 if row.event_id in bridge_ingested and _physical_event(row)][:20]
    visible_ids = {row.event_id for row in telemetry}
    route_receipts = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.event_id.in_(visible_ids))).all() if visible_ids else []
    bluetooth_receipts = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.kind == "BLUETOOTH_STORED").order_by(
        desc(DeliveryReceipt.reported_at)).limit(100)).all()
    receipts = route_receipts + bluetooth_receipts
    by_event: dict[str, dict[str, DeliveryReceipt]] = {}
    for receipt in receipts:
        by_event.setdefault(receipt.event_id, {})[receipt.kind] = receipt
    events = []
    for row in telemetry:
        comm = row.payload.get("communication") or {}
        tx = by_event.get(row.event_id, {})
        events.append({
            "event_id": row.event_id,
            "device_id": row.device_id,
            "sequence": comm.get("tx_sequence"),
            "rx_device_id": comm.get("rx_device_id"),
            "rx_queue_persisted": True,
            "rx_received_uptime_ms": comm.get("rx_received_uptime_ms"),
            "backend_stored_at": row.received_at.isoformat(),
            "rx_forward_acked_at": tx["RX_FORWARD_ACKED"].reported_at.isoformat()
                if "RX_FORWARD_ACKED" in tx and tx["RX_FORWARD_ACKED"].details.get("reporter") == "rx-http-bridge" else None,
            "bluetooth_stored_at": tx["BLUETOOTH_STORED"].reported_at.isoformat()
                if "BLUETOOTH_STORED" in tx and tx["BLUETOOTH_STORED"].details.get("simulated") is False
                and tx["BLUETOOTH_STORED"].details.get("reporter") == "bt-alert-receiver" else None,
            "environment": row.payload.get("environment") or {},
            "csi": row.payload.get("csi") or {},
        })
    # Bluetooth can carry an alert while Wi-Fi is down, so a receipt may have
    # no matching backend telemetry yet.
    bt_only = [receipt for receipt in bluetooth_receipts
               if receipt.details.get("simulated") is False
               and receipt.details.get("reporter") == "bt-alert-receiver"
               and receipt.event_id not in bridge_ingested][:10]
    heartbeats = {}
    for row in session.scalars(select(BridgeHeartbeat)).all():
        age = _age_seconds(row.reported_at, now)
        heartbeats[row.name] = {"status": row.status, "reported_at": row.reported_at.isoformat(),
                                "age_seconds": round(age, 1), "fresh": age <= 15}
    latest = events[0] if events else None
    age = _age_seconds(telemetry[0].received_at, now) if telemetry else None
    return {
        "as_of": now.isoformat(),
        "source": "RX-reported HTTP receipt forwarded by laptop bridge",
        "fresh_after_seconds": FRESH_SECONDS,
        "latest_age_seconds": round(age, 1) if age is not None else None,
        "latest_fresh": age is not None and age <= FRESH_SECONDS,
        "latest": latest,
        "events": events,
        "bluetooth_only": [{"event_id": receipt.event_id,
                            "reported_at": receipt.reported_at.isoformat(),
                            "details": receipt.details} for receipt in bt_only],
        "bridges": heartbeats,
    }
