"""Read-only synthetic forecast episodes for the dedicated dashboard."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .forecast_model import ForecastModel, HORIZONS
from .forecast_scenarios import CHANNELS, SCENARIOS, first_breach, generate_episode, get_scenario, safe_limits
from .forecast_hardware import replay_on_tx


router = APIRouter(prefix="/api/v1/forecast", tags=["forecast demo"])
ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ml" / "forecast_release" / "synthetic_v1" / "model.json"


class ReplayRequest(BaseModel):
    scenario: str
    minute: int = Field(ge=60, le=110)
    seed: int = Field(ge=1, le=999)
    wifi_fault: bool = False
    port: str = Field(pattern=r"^COM[0-9]{1,3}$")


@lru_cache(maxsize=1)
def model() -> ForecastModel:
    if not MODEL_PATH.is_file():
        raise HTTPException(status_code=503, detail="Synthetic forecast model is missing")
    return ForecastModel.load(MODEL_PATH)


@router.get("/scenarios")
def scenarios() -> dict:
    return {
        "synthetic": True,
        "scenarios": [
            {"key": s.key, "title": s.title, "room": s.room, "story": s.story,
             "response": s.response, "split": s.split}
            for s in SCENARIOS if s.split == "test"
        ],
    }


@router.get("/episode")
def episode(
    scenario: str = "freezer_rebound",
    minute: int = Query(82, ge=60, le=110),
    seed: int = Query(17, ge=1, le=999),
    reveal: bool = False,
) -> dict:
    try:
        selected = get_scenario(scenario)
    except StopIteration as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error
    if selected.split != "test":
        raise HTTPException(status_code=400, detail="Only held-out demo scenarios are selectable")

    values = generate_episode(selected, 90_000 + SCENARIOS.index(selected) * 1000 + seed)
    predicted = model().predict(values, minute, selected.room)
    limits = safe_limits(selected.room)
    breach = None
    for i, horizon in enumerate(HORIZONS):
        for channel, (low, high) in limits.items():
            value = float(predicted[i, CHANNELS.index(channel)])
            if value < low or value > high:
                breach = {"at_minute": horizon, "channel": channel, "value": value,
                          "limit": low if value < low else high, "direction": "below" if value < low else "above"}
                break
        if breach:
            break
    actual_offset, actual_channel = first_breach(values, selected.room, minute, 30)
    result = {
        "synthetic": True,
        "scenario": {"key": selected.key, "title": selected.title, "room": selected.room,
                     "story": selected.story, "response": selected.response, "split": selected.split},
        "seed": seed,
        "minute": minute,
        "event_id": f"sim-{selected.key}-{seed:03d}-{minute:03d}",
        "channels": list(CHANNELS),
        "current": values[minute].tolist(),
        "observed": values[max(0, minute - 45):minute + 1].tolist(),
        "forecast_horizons": list(HORIZONS),
        "forecast": predicted.tolist(),
        "limits": {k: list(v) for k, v in limits.items()},
        "breach": breach,
        "truth_revealed": reveal,
    }
    if reveal:
        result["actual_future"] = values[[minute + h for h in HORIZONS]].tolist()
        result["actual_breach"] = {"at_minute": actual_offset, "channel": actual_channel} if actual_offset is not None else None
    return result


@router.post("/replay")
def replay(request: ReplayRequest) -> dict:
    """Explicitly replay the same synthetic history through a connected TX board."""
    try:
        selected = get_scenario(request.scenario)
    except StopIteration as error:
        raise HTTPException(status_code=404, detail="Unknown scenario") from error
    if selected.split != "test":
        raise HTTPException(status_code=400, detail="Only held-out demo scenarios are selectable")
    values = generate_episode(selected, 90_000 + SCENARIOS.index(selected) * 1000 + request.seed)
    try:
        receipt = replay_on_tx(request.port, values, request.minute, selected.room, request.wifi_fault)
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        raise HTTPException(status_code=503, detail=f"TX replay unavailable: {error}") from error
    return {"synthetic_input": True, "physical_tx_replay": True, "receipt": receipt}
