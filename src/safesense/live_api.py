"""Backend view of physical RX telemetry and locally reported transport receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_session
from .models import BridgeHeartbeat, DeliveryReceipt, TelemetryEvent


router = APIRouter(prefix="/api/v1/live", tags=["live hardware"])
FRESH_SECONDS = 45


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


@router.get("/direct")
def direct_laptop_snapshot(session: Session = Depends(get_session)) -> dict:
    markers = session.scalars(select(DeliveryReceipt).where(
        DeliveryReceipt.kind.in_(("LAPTOP_WIFI_STORED", "LAPTOP_BT_SENSOR_STORED"))).order_by(
        desc(DeliveryReceipt.reported_at)).limit(100)).all()
    route_by_id = {}
    for marker in markers:
        route_by_id.setdefault(marker.event_id,
                               "DIRECT_BLUETOOTH" if marker.kind == "LAPTOP_BT_SENSOR_STORED"
                               else "DIRECT_WIFI")
    ids = [marker.event_id for marker in markers]
    rows = session.scalars(select(TelemetryEvent).where(
        TelemetryEvent.event_id.in_(ids)).order_by(
        desc(TelemetryEvent.received_at)).limit(20)).all() if ids else []
    direct = [row for row in rows if row.payload.get("firmware_version") in
              {"direct-wifi-bme680-mq135", "synthetic-forecast-demo"}]
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
    return {"as_of": datetime.now(timezone.utc).isoformat(), "events": [
        {"event_id": row.event_id, "device_id": row.device_id,
         "backend_stored_at": row.received_at.isoformat(),
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
