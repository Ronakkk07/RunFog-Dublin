import math
import os
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4


DEFAULT_SENSOR_FREQUENCIES = {
    "heart_rate": 1.0,
    "cadence": 1.0,
    "pace": 0.7,
    "gps": 0.5,
    "air_quality": 0.4,
}

DEFAULT_BASE_LAT = 53.3498
DEFAULT_BASE_LNG = -6.2603


def env_frequencies():
    return {
        "heart_rate": float(os.getenv("FREQ_HEART_RATE", DEFAULT_SENSOR_FREQUENCIES["heart_rate"])),
        "cadence": float(os.getenv("FREQ_CADENCE", DEFAULT_SENSOR_FREQUENCIES["cadence"])),
        "pace": float(os.getenv("FREQ_PACE", DEFAULT_SENSOR_FREQUENCIES["pace"])),
        "gps": float(os.getenv("FREQ_GPS", DEFAULT_SENSOR_FREQUENCIES["gps"])),
        "air_quality": float(os.getenv("FREQ_AIR_QUALITY", DEFAULT_SENSOR_FREQUENCIES["air_quality"])),
    }


def build_sensor_cycle(frequencies):
    weighted = []
    for sensor_type, frequency in frequencies.items():
        weighted.extend([sensor_type] * max(1, round(frequency * 10)))
    random.shuffle(weighted)
    return weighted


def build_fog_payload(
    fog_node_id,
    athlete_name,
    city,
    readings_per_batch=20,
    run_id=None,
    batch_id=None,
    frequencies=None,
    base_lat=DEFAULT_BASE_LAT,
    base_lng=DEFAULT_BASE_LNG,
    start_time=None,
):
    run_id = run_id or f"run-{uuid4().hex[:8]}"
    start_time = start_time or datetime.now(timezone.utc)
    sensor_cycle = build_sensor_cycle(frequencies or DEFAULT_SENSOR_FREQUENCIES)
    readings = []

    for index in range(readings_per_batch):
        sensor_type = sensor_cycle[index % len(sensor_cycle)]
        recorded_at = start_time + timedelta(seconds=index)
        readings.append(generate_reading(sensor_type, recorded_at, base_lat, base_lng, index))

    return {
        "fog_node_id": fog_node_id,
        "run_id": run_id,
        "athlete_name": athlete_name,
        "city": city,
        "batch_id": batch_id or f"{run_id}-batch-1",
        "readings": readings,
    }


def generate_reading(sensor_type, recorded_at, base_lat, base_lng, progress):
    oscillation = math.sin(progress / 4)
    if sensor_type == "heart_rate":
        value = round(140 + (oscillation * 12) + random.uniform(-4, 4), 2)
        return reading(sensor_type, value, "bpm", recorded_at, risk_flag=value > 170)
    if sensor_type == "cadence":
        value = round(164 + (oscillation * 5) + random.uniform(-2, 2), 2)
        return reading(sensor_type, value, "spm", recorded_at, risk_flag=value < 155)
    if sensor_type == "pace":
        value = round(5.5 - (oscillation * 0.3) + random.uniform(-0.15, 0.15), 2)
        return reading(sensor_type, value, "min/km", recorded_at, risk_flag=value > 6.2)
    if sensor_type == "gps":
        latitude = round(base_lat + (progress * 0.0004), 6)
        longitude = round(base_lng + (progress * 0.00025), 6)
        return reading(sensor_type, progress, "segment", recorded_at, latitude=latitude, longitude=longitude)
    value = round(18 + (oscillation * 6) + random.uniform(-1, 1), 2)
    return reading(sensor_type, value, "aqi", recorded_at, risk_flag=value > 22)


def reading(sensor_type, value, unit, recorded_at, latitude=None, longitude=None, risk_flag=False):
    return {
        "sensor_type": sensor_type,
        "reading_value": value,
        "unit": unit,
        "recorded_at": recorded_at.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "quality_score": round(random.uniform(0.86, 0.99), 2),
        "risk_flag": risk_flag,
    }
