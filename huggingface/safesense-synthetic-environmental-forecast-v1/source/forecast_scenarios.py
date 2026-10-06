"""Seeded, synthetic room trajectories for the forecast demonstration.

The generator keeps its latent disturbance private.  Only five sensor-like
channels and room context are exposed to the forecaster.  Values are examples,
not calibrated gas concentrations or evidence of a real hazardous event.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


CHANNELS = ("temperature_c", "humidity_pct", "pressure_pa", "gas_resistance_ohm", "mq135_adc_raw")
ROOMS = ("Cold storage", "Laboratory", "Classroom", "Bakery", "Server room")


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    room: str
    family: str
    split: str
    story: str
    response: str
    # Independent synthetic simulator parameters; the model never receives these.
    heat: float
    moisture: float
    vapor: float
    onset: int
    ramp: int
    rebound: float = 0.0


SCENARIOS = (
    Scenario("freezer_defrost", "Defrost cycle that fails to settle", "Cold storage", "defrost", "train", "A normal defrost pulse slowly becomes a persistent warming trend.", "Inspect refrigeration and protect stored goods.", 5.8, 7.5, 0.15, 55, 55, 0.45),
    Scenario("door_ajar", "A loading door left ajar", "Cold storage", "air_exchange", "train", "Warm, moist air enters in small bursts while the temperature still looks acceptable.", "Check door seals and close the loading route.", 4.8, 11.0, 0.1, 54, 65),
    Scenario("lab_cleanup", "Lab cleanup vapor build-up", "Laboratory", "vapor", "train", "A cleaning task raises a broad gas response even while temperature stays ordinary.", "Pause the activity and follow the site procedure.", 0.8, 2.0, 1.0, 56, 50),
    Scenario("lab_hvac", "Lab extraction weakens", "Laboratory", "ventilation", "train", "Residual vapors accumulate after an otherwise routine process.", "Check extraction and move people from the affected zone.", 1.3, 4.0, 0.85, 57, 60),
    Scenario("class_busy", "Crowded classroom with reduced air exchange", "Classroom", "occupancy", "train", "Heat and humidity rise together during a long session.", "Increase fresh-air exchange and check occupancy.", 3.5, 8.0, 0.35, 53, 70),
    Scenario("class_clean", "Cleaning after class", "Classroom", "cleaning", "train", "A short cleaning pulse leaves a slowly fading gas-sensor response.", "Check the product and room ventilation.", 0.4, 1.0, 0.78, 58, 35),
    Scenario("oven_shift", "Bakery oven shift runs long", "Bakery", "process_heat", "train", "A sustained heat load competes with the room cooling cycle.", "Check oven schedule and worker heat conditions.", 5.0, -5.0, 0.25, 54, 58),
    Scenario("steam_clean", "Bakery steam cleaning overlap", "Bakery", "steam", "train", "A humid cleaning operation overlaps with residual process heat.", "Separate cleaning from hot production and inspect conditions.", 3.1, 13.0, 0.45, 56, 54),
    Scenario("server_cooling", "Server cooling loses capacity", "Server room", "cooling", "train", "The rack aisle warms slowly despite a temporary cooling recovery.", "Check cooling plant and thermal load.", 6.2, -4.0, 0.08, 52, 65, 0.5),
    Scenario("server_battery", "Battery service disturbance", "Server room", "equipment", "train", "Service work adds a small heat load and a non-specific sensor response.", "Inspect the service area; do not infer a chemical identity from these sensors.", 2.6, -2.0, 0.65, 58, 46),
    # Entire families below are held out from model fitting and model selection.
    Scenario("freezer_rebound", "Compressor recovers, then warming rebounds", "Cold storage", "rebound", "test", "Readings briefly improve after a cooling cycle, then drift upward again.", "Inspect compressor cycling and door traffic.", 5.4, 8.8, 0.12, 52, 70, 0.9),
    Scenario("lab_two_stage", "Two-stage lab process", "Laboratory", "two_stage", "test", "Mild warming precedes a delayed broad gas-sensor rise.", "Pause the process and verify local ventilation.", 1.9, 3.2, 0.95, 54, 68),
    Scenario("class_afterhours", "After-hours classroom cleaning", "Classroom", "afterhours", "test", "The room cools as an unrelated cleaning response slowly grows.", "Verify the cleaning task and keep occupancy decisions separate.", -1.0, 0.4, 0.88, 57, 56),
    Scenario("bakery_restart", "Bakery restart after cleaning", "Bakery", "restart", "test", "Heat, moisture and a gas-sensor response overlap on different time scales.", "Check restart procedures and local conditions.", 4.6, 10.0, 0.58, 53, 72, 0.4),
    Scenario("server_airflow", "Server aisle airflow recirculation", "Server room", "recirculation", "test", "A slow thermal rise is masked by a short-lived cooling dip.", "Inspect aisle containment and airflow.", 5.3, -2.0, 0.1, 49, 76, 0.7),
    Scenario("cold_load", "Warm pallet and repeated door openings", "Cold storage", "load_interaction", "test", "A warm load and wet outside air combine after several small door events.", "Check loading practice and product temperature.", 5.1, 12.0, 0.2, 58, 59),
    Scenario("lab_flush", "Lab ventilation flush followed by accumulation", "Laboratory", "flush_rebound", "test", "A temporary clean-air flush hides a continuing source.", "Check the process source and extraction.", 0.8, 2.5, 0.9, 51, 73, 0.8),
    Scenario("bakery_cooling", "Bakery cooling bottleneck", "Bakery", "cooldown", "test", "Heat falls initially but humidity and sensor response keep rising.", "Inspect cooling and cleaning overlap.", 3.2, 12.5, 0.55, 51, 75, 0.55),
)


BASE = {
    "Cold storage": (-16.5, 47.0, 101325.0, 90000.0, 470.0),
    "Laboratory": (22.0, 43.0, 101325.0, 82000.0, 560.0),
    "Classroom": (24.0, 48.0, 101325.0, 78000.0, 590.0),
    "Bakery": (27.0, 44.0, 101325.0, 75000.0, 610.0),
    "Server room": (21.5, 39.0, 101325.0, 88000.0, 510.0),
}


def get_scenario(key: str) -> Scenario:
    return next(s for s in SCENARIOS if s.key == key)


def generate_episode(scenario: Scenario, seed: int, minutes: int = 151) -> np.ndarray:
    """Return one-minute synthetic sensor values; no labels or future in input."""
    rng = np.random.default_rng(seed)
    base = np.array(BASE[scenario.room], dtype=np.float64)
    base += rng.normal(0, [0.35, 1.3, 90, 4500, 32])
    amplitude = rng.uniform(0.78, 1.25)
    onset = scenario.onset + int(rng.integers(-8, 9))
    ramp = scenario.ramp * rng.uniform(0.8, 1.2)
    t = np.arange(minutes, dtype=np.float64)
    progress = np.clip((t - onset) / ramp, 0, 1.45)
    # Rebound gives a short apparent recovery before the disturbance resumes.
    dip = scenario.rebound * np.exp(-0.5 * ((t - onset - ramp * 0.55) / 9.0) ** 2)
    exposure = np.maximum(0, progress - dip)
    delayed = np.clip((t - onset - 10) / (ramp * 0.9), 0, 1.5)
    daily = np.sin(2 * np.pi * t / 100 + rng.uniform(-1, 1))
    temp = base[0] + amplitude * scenario.heat * exposure + 0.22 * daily + rng.normal(0, 0.06, minutes)
    humidity = base[1] + amplitude * scenario.moisture * delayed - 0.55 * (temp - base[0]) + 0.7 * daily + rng.normal(0, 0.35, minutes)
    pressure = base[2] + 0.35 * t + 9 * daily + rng.normal(0, 2.5, minutes)
    # BME680 gas resistance and MQ raw ADC are broad, humidity-sensitive proxies.
    gas = base[3] * (1 - 0.52 * amplitude * scenario.vapor * exposure) - 180 * (humidity - base[1])
    gas += rng.normal(0, 550, minutes)
    mq = base[4] + 440 * amplitude * scenario.vapor * delayed + 1.5 * (humidity - base[1])
    mq += rng.normal(0, 8, minutes)
    result = np.column_stack((temp, humidity, pressure, gas, mq))
    result[:, 1] = np.clip(result[:, 1], 5, 95)
    result[:, 3] = np.clip(result[:, 3], 1000, 300000)
    result[:, 4] = np.clip(result[:, 4], 0, 4095)
    return result.astype(np.float32)


def safe_limits(room: str) -> dict[str, tuple[float, float]]:
    """Demo policy ranges, independent of the synthetic hidden trajectory."""
    return {
        "Cold storage": {"temperature_c": (-19, -12), "humidity_pct": (25, 65), "gas_resistance_ohm": (45000, 200000)},
        "Laboratory": {"temperature_c": (18, 27), "humidity_pct": (25, 65), "gas_resistance_ohm": (45000, 200000)},
        "Classroom": {"temperature_c": (19, 29), "humidity_pct": (25, 70), "gas_resistance_ohm": (42000, 200000)},
        "Bakery": {"temperature_c": (19, 34), "humidity_pct": (20, 70), "gas_resistance_ohm": (40000, 200000)},
        "Server room": {"temperature_c": (17, 27), "humidity_pct": (20, 65), "gas_resistance_ohm": (45000, 200000)},
    }[room]


def first_breach(values: np.ndarray, room: str, start: int, horizon: int = 30) -> tuple[int | None, str | None]:
    limits = safe_limits(room)
    for offset in range(1, min(horizon + 1, len(values) - start)):
        for channel, (low, high) in limits.items():
            value = float(values[start + offset, CHANNELS.index(channel)])
            if value < low or value > high:
                return offset, channel
    return None, None
