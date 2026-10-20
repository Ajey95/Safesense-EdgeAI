"""Research CSI count demo: held-out replay and a local serial packet bridge."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

import joblib
import numpy as np
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .csi_count_features import FEATURE_NAMES, PAIR_POSITIONS, WINDOW_FRAMES, WINDOW_STRIDE, serial_amplitudes, window_features
from .room_capture import RoomCaptureStore
from .csi_packet_journal import append_packets

router = APIRouter(prefix="/api/v1/csi-count", tags=["csi-count"])
MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "models" / "profench_count_012_blocked"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_LOG = PROJECT_ROOT / "data" / "live" / "csi_sensor_bridge.log"
STALE_SECONDS = 3.0
SCENARIOS = {"empty_room": (0, "Empty room"), "one_person": (1, "One person"),
             "two_people": (2, "Two people")}


class PacketBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[str] = Field(min_length=1, max_length=100)
    source: Literal["ESP32_SERIAL", "ESP32_WIFI", "ESP32_BLUETOOTH"] = "ESP32_SERIAL"


class RoomCaptureStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    interval_seconds: int = Field(default=10, ge=5, le=60)
    label_count: int | None = Field(default=None, ge=0, le=2)


class RoomCaptureLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label_count: int | None = Field(default=None, ge=0, le=2)


class BridgeStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    port: str = Field(default="COM11", pattern=r"^COM[0-9]{1,3}$")


@lru_cache(maxsize=1)
def assets():
    try:
        bundle = joblib.load(MODEL_DIR / "model.joblib")
        with np.load(MODEL_DIR / "replay_windows.npz") as archive:
            windows, labels = archive["windows"], archive["labels"]
        evaluation = json.loads((MODEL_DIR / "evaluation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail=f"CSI count assets unavailable: {error}") from error
    if bundle["window_frames"] != WINDOW_FRAMES or bundle["pair_positions"] != PAIR_POSITIONS.tolist() or tuple(bundle["feature_names"]) != FEATURE_NAMES:
        raise HTTPException(status_code=503, detail="CSI model feature contract mismatch")
    if windows.ndim != 3 or windows.shape[1:] != (100, 50) or len(windows) != len(labels):
        raise HTTPException(status_code=503, detail="CSI replay shape mismatch")
    return bundle["model"], windows, labels, evaluation


def predict(window: np.ndarray) -> dict:
    model = assets()[0]
    features = window_features(window)[None, :]
    prediction = int(model.predict(features)[0])
    scores = model.predict_proba(features)[0]
    return {"predicted_count": prediction, "model_score": round(float(np.max(scores)), 3)}


@lru_cache(maxsize=1)
def recorded_variation_bounds() -> tuple[float, float]:
    """A conservative range from the recorded windows, not a live accuracy claim."""
    reference = assets()[1]
    variation = np.median(reference.std(axis=1), axis=1)
    return float(variation.min() * 0.75), float(variation.max() * 1.25)


def predict_live(window: np.ndarray) -> dict:
    variation = float(np.median(window.std(axis=0)))
    low, high = recorded_variation_bounds()
    quality = {"signal_variation": round(variation, 2),
               "recorded_variation_range": [round(low, 2), round(high, 2)]}
    if not low <= variation <= high:
        return {"predicted_count": None, "model_score": None,
                "quality_reason": "OUTSIDE_RECORDED_SIGNAL_RANGE", **quality}
    return {**predict(window), "quality_reason": None, **quality}


def trace(window: np.ndarray) -> list[float]:
    return np.round(window.mean(axis=1), 2).tolist()


@router.get("/replay")
def replay(scenario: str = Query(), index: int = Query(default=0, ge=0)) -> dict:
    if scenario not in SCENARIOS:
        raise HTTPException(status_code=404, detail="Unknown recorded CSI scenario")
    count, title = SCENARIOS[scenario]
    _, windows, labels, _ = assets()
    choices = np.flatnonzero(labels == count)
    if index >= len(choices):
        raise HTTPException(status_code=404, detail="Replay index outside held-out samples")
    window = windows[choices[index]]
    return {"source": "RECORDED_DATASET_REPLAY", "scenario": scenario, "scenario_title": title,
            "recorded_count": int(labels[choices[index]]), "sample_index": index,
            "sample_total": len(choices), "signal_trace": trace(window),
            "input_shape": [100, 50], "feature_count": len(FEATURE_NAMES),
            **predict(window)}


class LiveState:
    def __init__(self):
        self.lock = Lock()
        self.frames = deque(maxlen=WINDOW_FRAMES)
        self.packet_count = 0
        self.last_packet_monotonic = None
        self.last_packet_received_at = None
        self.last_sequence = None
        self.last_received_us = None
        self.last_rssi = None
        self.last_invalid_first_word = None
        self.last_iq_pairs = None
        self.queue_drops = 0
        self.prediction = None
        self.last_source = None


live = LiveState()
room_store = RoomCaptureStore()
bridge_lock = Lock()
bridge_process: subprocess.Popen | None = None
bridge_port: str | None = None


def _control(request: Request, control: str | None) -> None:
    if (request.client is None or request.client.host not in
            {"127.0.0.1", "::1", "testclient"} or control != "dashboard"):
        raise HTTPException(status_code=403, detail="Local dashboard control required")


@router.get("/bridge")
def bridge_status() -> dict:
    with bridge_lock:
        return {"running": bridge_process is not None and bridge_process.poll() is None,
                "port": bridge_port,
                "exit_code": bridge_process.poll() if bridge_process is not None else None}


@router.post("/bridge")
def bridge_start(change: BridgeStart, request: Request,
                 control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    _control(request, control)
    global bridge_process, bridge_port
    with bridge_lock:
        if bridge_process is not None and bridge_process.poll() is None:
            return {"running": True, "port": bridge_port, "already_running": True}
        BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            with BRIDGE_LOG.open("ab") as log:
                bridge_process = subprocess.Popen(
                    [sys.executable, "-m", "scripts.csi_count_receiver", "--port", change.port,
                     "--diagnostic-lines"],
                    cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            raise HTTPException(status_code=503, detail=f"Could not start serial bridge: {type(error).__name__}") from error
        bridge_port = change.port
        return {"running": True, "port": bridge_port, "started": True}


@router.post("/bridge/stop")
def bridge_stop(request: Request,
                control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    _control(request, control)
    global bridge_process, bridge_port
    with bridge_lock:
        if bridge_process is None or bridge_process.poll() is not None:
            return {"running": False, "already_stopped": True}
        bridge_process.terminate()
        try:
            bridge_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            bridge_process.kill()
            bridge_process.wait(timeout=3)
        bridge_process = None
        bridge_port = None
    return {"running": False, "stopped": True}


@router.get("/room-capture")
def room_capture_status() -> dict:
    return room_store.status()


@router.post("/room-capture")
def room_capture_start(change: RoomCaptureStart, request: Request,
                       control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    _control(request, control)
    with live.lock:
        try:
            result = room_store.start(change.room, change.interval_seconds, change.label_count)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        live.frames.clear()
        live.prediction = None
    return result


@router.post("/room-capture/label")
def room_capture_label(change: RoomCaptureLabel, request: Request,
                       control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    _control(request, control)
    with live.lock:
        try:
            result = room_store.set_label(change.label_count)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        live.frames.clear()
        live.prediction = None
    return result


@router.post("/room-capture/stop")
def room_capture_stop(request: Request,
                      control: str | None = Header(default=None, alias="X-SafeSense-Control")) -> dict:
    _control(request, control)
    try:
        return room_store.stop()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def parse_line(line: str) -> tuple[int, int, int, int, int, np.ndarray, bytes | None, np.ndarray]:
    fields = line.strip().split(",", 7)
    if len(fields) != 8 or fields[0] != "WISDOM_CSI" or fields[1] not in {"1", "2"}:
        raise ValueError("invalid CSI serial line/version")
    try:
        sequence, received_us, rssi, invalid, drops = map(int, fields[2:7])
        raw = base64.b64decode(fields[7], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("invalid CSI serial metadata/payload") from error
    if sequence < 0 or received_us < 0 or invalid not in (0, 1) or drops < 0 or not -128 <= rssi <= 127:
        raise ValueError("CSI serial metadata outside range")
    if len(raw) != (100 if fields[1] == "1" else 128):
        raise ValueError("CSI I/Q payload length does not match protocol version")
    selected = (np.frombuffer(raw, dtype=np.int8).reshape(64, 2)[PAIR_POSITIONS]
                .astype(np.int8, copy=True).tobytes() if fields[1] == "2" else raw)
    iq_pairs = np.frombuffer(selected, dtype=np.int8).reshape(50, 2).copy()
    return sequence, received_us, rssi, drops, invalid, iq_pairs, \
        raw if fields[1] == "2" else None, serial_amplitudes(selected)


@router.post("/packets")
def accept_packets(batch: PacketBatch, request: Request) -> dict:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail="CSI serial bridge accepts local requests only")
    assets()
    try:
        parsed = [parse_line(line) for line in batch.lines]
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    with live.lock:
        try:
            capture = room_store.status()
            append_packets(batch.source, parsed, capture=capture if capture["active"] else None)
        except sqlite3.Error as error:
            raise HTTPException(status_code=503, detail="CSI packet journal unavailable") from error
        for sequence, received_us, rssi, drops, invalid, iq_pairs, _raw_iq, amplitude in parsed:
            if (live.last_source is not None and live.last_source != batch.source) or (live.last_sequence is not None and (sequence <= live.last_sequence or sequence != live.last_sequence + 1)) or (live.last_received_us is not None and (received_us <= live.last_received_us or received_us - live.last_received_us > 500_000)):
                live.frames.clear()
                live.prediction = None
            live.packet_count += 1
            live.last_sequence = sequence
            live.last_received_us = received_us
            live.last_source = batch.source
            live.last_packet_monotonic = time.monotonic()
            live.last_packet_received_at = datetime.now(timezone.utc).isoformat()
            live.last_rssi = rssi
            live.last_invalid_first_word = bool(invalid)
            live.last_iq_pairs = iq_pairs
            live.queue_drops = drops
            # ESP32's first_word_invalid flags the first raw I/Q word; the
            # exported 50 pairs exclude it via PAIR_POSITIONS.
            live.frames.append(amplitude)
            if len(live.frames) == WINDOW_FRAMES and (live.packet_count % WINDOW_STRIDE == 0 or live.prediction is None):
                window = np.stack(live.frames)
                live.prediction = predict_live(window)
                room_store.maybe_capture(window, sequence, rssi, live.prediction,
                                         source=batch.source)
        return {"accepted": len(parsed), "total_packets": live.packet_count, "buffered_frames": len(live.frames)}


@router.get("/status")
def status() -> dict:
    _, _, _, evaluation = assets()
    with live.lock:
        age = None if live.last_packet_monotonic is None else round(time.monotonic() - live.last_packet_monotonic, 2)
        fresh = age is not None and age <= STALE_SECONDS
        signal = trace(np.stack(live.frames)) if fresh and live.frames else []
        latest_pairs = np.round(live.frames[-1], 2).tolist() if fresh and live.frames else []
        prediction = live.prediction if fresh else None
        return {"source": f"LIVE_{live.last_source}" if fresh and live.last_source else "NO_FRESH_LIVE_CSI",
                "status": "READY" if prediction and prediction["predicted_count"] is not None else "UNKNOWN",
                "predicted_count": prediction["predicted_count"] if prediction else None,
                "model_score": prediction["model_score"] if prediction else None,
                "quality_reason": prediction["quality_reason"] if prediction else "INSUFFICIENT_CSI_FRAMES" if fresh else "NO_FRESH_LIVE_CSI",
                "signal_variation": prediction["signal_variation"] if prediction else None,
                "recorded_variation_range": prediction["recorded_variation_range"] if prediction else None,
                "packet_count": live.packet_count, "buffered_frames": len(live.frames),
                "age_seconds": age, "last_rssi_dbm": live.last_rssi if fresh else None,
                "last_sequence": live.last_sequence if fresh else None,
                "last_packet_received_at": live.last_packet_received_at,
                "queue_drops": live.queue_drops, "signal_trace": signal,
                "last_packet": {"sequence": live.last_sequence,
                                "board_time_us": live.last_received_us,
                                "rssi_dbm": live.last_rssi,
                                "invalid_first_word": live.last_invalid_first_word,
                                "queue_drops": live.queue_drops,
                                "payload_bytes": 100,
                                "iq_pairs": live.last_iq_pairs.tolist()}
                               if fresh and live.last_iq_pairs is not None else None,
                "pair_positions": PAIR_POSITIONS.tolist(),
                "latest_pair_amplitudes": latest_pairs,
                "evaluation": {"accuracy": evaluation["model"]["accuracy"],
                               "test_windows": evaluation["test_windows"], "scope": evaluation["status"]}}
