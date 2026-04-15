import math
import os
import random
from collections import defaultdict
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
VIRTUAL_FOG_NODES = [
    {
        "id": "fog-dublin-north",
        "label": "Dublin North",
        "city": "Dublin",
        "base_lat": 53.3898,
        "base_lng": -6.2608,
        "zone": "Northside canal route",
    },
    {
        "id": "fog-dublin-south",
        "label": "Dublin South",
        "city": "Dublin",
        "base_lat": 53.3255,
        "base_lng": -6.2661,
        "zone": "Southside riverside route",
    },
    {
        "id": "fog-campus-west",
        "label": "Campus West",
        "city": "Dublin",
        "base_lat": 53.3062,
        "base_lng": -6.2248,
        "zone": "Campus west loop",
    },
]
FOG_NODE_LOOKUP = {node["id"]: node for node in VIRTUAL_FOG_NODES}
ATHLETE_NAMES = [
    "Aoife Murphy",
    "Ciaran Kelly",
    "Niamh Doyle",
    "Conor Walsh",
    "Saoirse Byrne",
    "Eoin Brennan",
    "Clodagh Ryan",
    "Darragh O'Shea",
    "Aisling Nolan",
    "Finn O'Connor",
]


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
    fog_node = resolve_fog_node(fog_node_id, city=city, base_lat=base_lat, base_lng=base_lng)
    run_id = run_id or f"run-{uuid4().hex[:8]}"
    athlete_name = resolve_athlete_name(athlete_name)
    start_time = start_time or datetime.now(timezone.utc)
    sensor_cycle = build_sensor_cycle(frequencies or DEFAULT_SENSOR_FREQUENCIES)
    readings = []
    sensor_counts = defaultdict(int)
    anomaly_counts = defaultdict(int)

    for index in range(readings_per_batch):
        sensor_type = sensor_cycle[index % len(sensor_cycle)]
        recorded_at = start_time + timedelta(seconds=index)
        reading_payload = generate_reading(
            sensor_type=sensor_type,
            recorded_at=recorded_at,
            base_lat=fog_node["base_lat"],
            base_lng=fog_node["base_lng"],
            progress=index,
            sensor_index=sensor_counts[sensor_type],
            fog_node=fog_node,
        )
        readings.append(reading_payload)
        sensor_counts[sensor_type] += 1
        if reading_payload["anomaly_type"]:
            anomaly_counts[reading_payload["anomaly_type"]] += 1

    return {
        "fog_node_id": fog_node["id"],
        "run_id": run_id,
        "athlete_name": athlete_name,
        "city": fog_node["city"],
        "batch_id": batch_id or f"{run_id}-batch-1",
        "fog_summary": {
            "zone": fog_node["zone"],
            "sensor_counts": dict(sensor_counts),
            "anomaly_counts": dict(anomaly_counts),
            "processing_stage": "fog",
        },
        "readings": readings,
    }


def resolve_athlete_name(athlete_name=None):
    if athlete_name and athlete_name.strip():
        return athlete_name.strip()
    return random.choice(ATHLETE_NAMES)


def resolve_fog_node(fog_node_id=None, city=None, base_lat=None, base_lng=None):
    if fog_node_id and fog_node_id.strip():
        node = dict(FOG_NODE_LOOKUP.get(fog_node_id.strip(), {}))
        if not node:
            node = {
                "id": fog_node_id.strip(),
                "label": fog_node_id.strip().replace("-", " ").title(),
                "city": city or "Dublin",
                "base_lat": base_lat if base_lat is not None else DEFAULT_BASE_LAT,
                "base_lng": base_lng if base_lng is not None else DEFAULT_BASE_LNG,
                "zone": "Custom virtual fog node",
            }
    else:
        node = dict(random.choice(VIRTUAL_FOG_NODES))

    if city:
        node["city"] = city
    if base_lat is not None:
        node["base_lat"] = base_lat
    if base_lng is not None:
        node["base_lng"] = base_lng
    return node


def available_fog_nodes():
    return [node["id"] for node in VIRTUAL_FOG_NODES]


def generate_reading(sensor_type, recorded_at, base_lat, base_lng, progress, sensor_index, fog_node):
    oscillation = math.sin(progress / 4)
    if sensor_type == "heart_rate":
        value = round(140 + (oscillation * 12) + random.uniform(-4, 4), 2)
        anomaly = {}
        if sensor_index == 2:
            value = round(176 + random.uniform(2, 11), 2)
            anomaly = fog_anomaly(
                "high_heart_rate_spike",
                "critical",
                f"{fog_node['label']} detected a sudden heart-rate spike during edge processing.",
            )
        return reading(sensor_type, value, "bpm", recorded_at, risk_flag=value > 170 or bool(anomaly), **anomaly)
    if sensor_type == "cadence":
        value = round(164 + (oscillation * 5) + random.uniform(-2, 2), 2)
        return reading(sensor_type, value, "spm", recorded_at, risk_flag=value < 155)
    if sensor_type == "pace":
        value = round(5.5 - (oscillation * 0.3) + random.uniform(-0.15, 0.15), 2)
        anomaly = {}
        if sensor_index == 1:
            value = round(6.6 + random.uniform(0.1, 0.7), 2)
            anomaly = fog_anomaly(
                "pace_collapse",
                "high",
                f"{fog_node['label']} flagged a pace collapse after comparing the recent split to the expected effort.",
            )
        return reading(sensor_type, value, "min/km", recorded_at, risk_flag=value > 6.2 or bool(anomaly), **anomaly)
    if sensor_type == "gps":
        anomaly = {}
        latitude = round(base_lat + (progress * 0.0004), 6)
        longitude = round(base_lng + (progress * 0.00025), 6)
        quality_score = None
        if sensor_index == 1:
            latitude = None
            longitude = None
            quality_score = 0.58
            anomaly = fog_anomaly(
                "missing_gps_sample",
                "high",
                f"{fog_node['label']} detected a missing GPS sample and forwarded the gap for cloud-side review.",
            )
        return reading(
            sensor_type,
            progress,
            "segment",
            recorded_at,
            latitude=latitude,
            longitude=longitude,
            quality_score=quality_score,
            risk_flag=bool(anomaly),
            **anomaly,
        )
    value = round(18 + (oscillation * 6) + random.uniform(-1, 1), 2)
    anomaly = {}
    if sensor_index == 1:
        value = round(24 + random.uniform(1, 7), 2)
        anomaly = fog_anomaly(
            "poor_air_quality_segment",
            "high",
            f"{fog_node['label']} identified a poor-air-quality route segment before dispatching the batch.",
        )
    return reading(sensor_type, value, "aqi", recorded_at, risk_flag=value > 22 or bool(anomaly), **anomaly)


def fog_anomaly(anomaly_type, severity, message):
    return {
        "anomaly_type": anomaly_type,
        "anomaly_severity": severity,
        "anomaly_message": message,
        "processing_stage": "fog",
    }


def reading(
    sensor_type,
    value,
    unit,
    recorded_at,
    latitude=None,
    longitude=None,
    quality_score=None,
    risk_flag=False,
    anomaly_type="",
    anomaly_severity="",
    anomaly_message="",
    processing_stage="",
):
    return {
        "sensor_type": sensor_type,
        "reading_value": value,
        "unit": unit,
        "recorded_at": recorded_at.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "quality_score": round(quality_score if quality_score is not None else random.uniform(0.86, 0.99), 2),
        "risk_flag": risk_flag,
        "anomaly_type": anomaly_type,
        "anomaly_severity": anomaly_severity,
        "anomaly_message": anomaly_message,
        "processing_stage": processing_stage,
    }
