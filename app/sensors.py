"""IoT Sensor Simulator — virtual sensors with diurnal time-series generation."""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from math import pi, sin

import numpy as np
from fastapi import APIRouter

from app.anomaly import check_anomaly
from app.config import CITIES

SENSOR_SEED = os.environ.get("SENSOR_SEED", "42")
_seed = int(SENSOR_SEED) if SENSOR_SEED else None
rng = np.random.default_rng(_seed)

TYPE_ABBREV = {"air_quality": "aq", "noise_db": "noise", "vibration_g": "vib", "water_flow_lps": "wf"}

SENSOR_TYPE_PARAMS = {
    "air_quality": {"baseline": 12, "amplitude": 8, "phase": 8, "sigma": 2.0, "spike_prob": 0.02, "spike_range": (30, 50), "valid_range": (5, 80)},
    "noise_db": {"baseline": 45, "amplitude": 15, "phase": 12, "sigma": 3.0, "spike_prob": 0.03, "spike_range": (20, 35), "valid_range": (30, 95)},
    "vibration_g": {"baseline": 0.02, "amplitude": 0.01, "phase": 9, "sigma": 0.005, "spike_prob": 0.01, "spike_range": (0.1, 0.3), "valid_range": (0.001, 0.5)},
    "water_flow_lps": {"baseline": 2.5, "amplitude": 1.5, "phase": 7, "sigma": 0.3, "spike_prob": 0.015, "spike_range": (5, 10), "valid_range": (0.1, 15)},
}

SENSOR_TYPES = list(SENSOR_TYPE_PARAMS.keys())


@dataclass
class SensorState:
    sensor_id: str
    sensor_type: str
    neighborhood: str
    lat: float
    lng: float
    last_reading: float = 0.0
    last_timestamp: str = ""
    status: str = "online"


def init_sensors() -> list[SensorState]:
    """Create 20 sensors across Stuttgart neighborhoods, 5 per type round-robin."""
    neighborhoods = CITIES["stuttgart"]["neighborhoods"]
    # 3 high-density neighborhoods get 2 sensors
    slots = list(neighborhoods) + [neighborhoods[0], neighborhoods[1], neighborhoods[2]]  # 20 total
    sensors = []
    for i, (lat_min, lat_max, lng_min, lng_max, name) in enumerate(slots):
        sensor_type = SENSOR_TYPES[i % 4]
        abbrev = TYPE_ABBREV[sensor_type]
        slug = name.lower().replace("-", "_").replace(" ", "_").replace("ö", "oe").replace("ü", "ue")
        # Count how many of this type already exist for this neighborhood
        idx = sum(1 for s in sensors if s.neighborhood == name and s.sensor_type == sensor_type) + 1
        sensor_id = f"iot-{slug}-{abbrev}-{idx:02d}"
        lat = (lat_min + lat_max) / 2 + (i * 0.0001 - 0.001)
        lng = (lng_min + lng_max) / 2 + (i * 0.0001 - 0.001)
        sensors.append(SensorState(sensor_id=sensor_id, sensor_type=sensor_type, neighborhood=name, lat=round(lat, 6), lng=round(lng, 6)))
    return sensors


def generate_reading(sensor: SensorState, hour: float, gen: np.random.Generator = rng) -> float:
    """Generate a single reading: diurnal sine + noise + spike, clamped to valid range."""
    p = SENSOR_TYPE_PARAMS[sensor.sensor_type]
    diurnal = p["amplitude"] * sin(2 * pi * (hour - p["phase"]) / 24)
    noise = gen.normal(0, p["sigma"])
    spike = gen.uniform(*p["spike_range"]) if gen.random() < p["spike_prob"] else 0.0
    value = p["baseline"] + diurnal + noise + spike
    lo, hi = p["valid_range"]
    return float(np.clip(value, lo, hi))


_sensors: list[SensorState] = []
_last_cycle: str = ""


def get_sensors() -> list[SensorState]:
    global _sensors
    if not _sensors:
        _sensors = init_sensors()
    return _sensors


async def sensor_loop() -> None:
    """Background task: generate readings every 60s, feed anomaly detector on spikes."""
    global _last_cycle
    sensors = get_sensors()
    while True:
        try:
            now = datetime.now(timezone.utc)
            hour = now.hour + now.minute / 60.0
            _last_cycle = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            for sensor in sensors:
                reading = generate_reading(sensor, hour)
                sensor.last_reading = reading
                sensor.last_timestamp = _last_cycle
                p = SENSOR_TYPE_PARAMS[sensor.sensor_type]
                if reading > p["baseline"] + p["amplitude"] + 2 * p["sigma"]:
                    try:
                        check_anomaly("stuttgart", sensor.neighborhood)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(60)


router = APIRouter(prefix="/api/sensors")


@router.get("/status")
async def sensor_status():
    sensors = get_sensors()
    return {
        "sensors": [
            {"sensor_id": s.sensor_id, "type": s.sensor_type, "neighborhood": s.neighborhood,
             "lat": s.lat, "lng": s.lng, "last_reading": s.last_reading,
             "last_timestamp": s.last_timestamp, "status": s.status}
            for s in sensors
        ],
        "fleet_health": {"online": len(sensors), "total": len(sensors)},
        "last_cycle": _last_cycle,
    }
