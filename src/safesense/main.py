from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_session
from .fusion import evaluate
from .models import Device, Incident, TelemetryEvent
from .realtime import hub
from .schemas import Risk, TelemetryIn



@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SafeSense", version="0.1.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def dashboard() -> RedirectResponse:
    """Streamlit is the only dashboard surface; FastAPI remains the telemetry API."""
    return RedirectResponse(url="http://127.0.0.1:8501", status_code=307)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/telemetry", status_code=202)
async def ingest(telemetry: TelemetryIn, session: Session = Depends(get_session)) -> dict:
    existing = session.scalar(select(TelemetryEvent).where(TelemetryEvent.event_id == telemetry.event_id))
    if existing:
        incident_id = str(uuid5(NAMESPACE_URL, f"{telemetry.device_id}:{telemetry.event_id}")) if existing.fusion_state in {"INCIDENT", "CRITICAL"} else None
        return {"accepted": True, "duplicate": True, "fusion_state": existing.fusion_state, "incident_id": incident_id}
    now = datetime.now(timezone.utc)
    observed_at = telemetry.observed_at or now
    fusion = evaluate(telemetry)
    device = session.get(Device, telemetry.device_id)
    if device is None:
        device = Device(device_id=telemetry.device_id, last_seen_at=now, firmware_version=telemetry.firmware_version, state="ONLINE")
        session.add(device)
    else:
        device.last_seen_at, device.firmware_version, device.state = now, telemetry.firmware_version, "ONLINE"
    payload = telemetry.model_dump(mode="json")
    payload["observed_at"] = observed_at.isoformat()
    event = TelemetryEvent(event_id=telemetry.event_id, device_id=telemetry.device_id, observed_at=observed_at, received_at=now, payload=payload, fusion_state=fusion.state, fusion_reason=fusion.reason)
    session.add(event)
    incident_id = None
    if fusion.incident_required:
        incident_id = str(uuid5(NAMESPACE_URL, f"{telemetry.device_id}:{telemetry.event_id}"))
        if session.get(Incident, incident_id) is None:
            session.add(Incident(incident_id=incident_id, device_id=telemetry.device_id, created_at=now, state="NEW", severity="CRITICAL", reason=fusion.reason))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(TelemetryEvent).where(TelemetryEvent.event_id == telemetry.event_id))
        if existing is None:
            raise HTTPException(status_code=503, detail="Telemetry could not be committed")
        existing_incident = str(uuid5(NAMESPACE_URL, f"{existing.device_id}:{existing.event_id}")) if existing.fusion_state == "INCIDENT" else None
        return {"accepted": True, "duplicate": True, "fusion_state": existing.fusion_state, "incident_id": existing_incident}
    message = {"type": "telemetry", "device_id": telemetry.device_id, "observed_at": observed_at.isoformat(), "environment": telemetry.environment.model_dump(), "csi": telemetry.csi.model_dump(), "fusion": fusion.model_dump(), "incident_id": incident_id}
    await hub.broadcast(message)
    return {"accepted": True, "duplicate": False, "fusion_state": fusion.state, "incident_id": incident_id}


@app.get("/api/v1/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    latest = session.scalars(select(TelemetryEvent).order_by(desc(TelemetryEvent.received_at)).limit(20)).all()
    incidents = session.scalars(select(Incident).order_by(desc(Incident.created_at)).limit(20)).all()
    return {"telemetry": [{"device_id": item.device_id, "observed_at": item.observed_at, "payload": item.payload, "fusion_state": item.fusion_state, "fusion_reason": item.fusion_reason} for item in latest], "incidents": [{"incident_id": x.incident_id, "device_id": x.device_id, "created_at": x.created_at, "state": x.state, "severity": x.severity, "reason": x.reason} for x in incidents]}


@app.post("/api/v1/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id: str, operator: str = Query(min_length=1, max_length=120), session: Session = Depends(get_session)) -> dict:
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.state == "NEW":
        incident.state, incident.acknowledged_at, incident.acknowledged_by = "ACKNOWLEDGED", datetime.now(timezone.utc), operator
        session.commit()
    return {"incident_id": incident_id, "state": incident.state}


@app.websocket("/ws/dashboard")
async def dashboard_socket(socket: WebSocket) -> None:
    await hub.connect(socket)
    try:
        while True:
            await socket.receive_text()
    except Exception:
        hub.disconnect(socket)
