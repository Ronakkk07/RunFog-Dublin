"""
Lambda Fog Injector for RunFog Dublin
--------------------------------------
This Lambda function acts as a cloud-side fog node.
It generates sensor readings and posts them directly to the backend ingest endpoint.

Trigger: Amazon EventBridge (scheduled rule) — e.g. every 2 minutes
This means data flows into the dashboard even when Cloud9 is not running.

Environment variables:
  RUNNERHUB_INGEST_URL          - https://<eb-domain>/api/ingest/
  RUNNERHUB_BACKEND_INGEST_TOKEN - shared secret

To set up the EventBridge trigger:
  1. AWS Console → EventBridge → Rules → Create rule
  2. Name: runfog-fog-injector-schedule
  3. Rule type: Schedule
  4. Schedule: rate(2 minutes)   ← adjust as needed for your demo
  5. Target: Lambda → runfog-fog-injector
  6. Save
"""

import json
import logging
import math
import os
import random
from datetime import datetime, timezone, timedelta
from urllib import request, error
from uuid import uuid4

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INGEST_URL = os.environ["RUNNERHUB_INGEST_URL"]
TOKEN = os.environ["RUNNERHUB_BACKEND_INGEST_TOKEN"]

# Configurable via environment variables — demonstrates configurable dispatch rates
READINGS_PER_BATCH = int(os.environ.get("FOG_READINGS_PER_BATCH", "20"))
FOG_NODE_ID = os.environ.get("FOG_NODE_ID", "fog-lambda-cloud")
ATHLETE_NAME = os.environ.get("FOG_ATHLETE_NAME", "Ciarán Kelly")
CITY = os.environ.get("FOG_CITY", "Dublin")

# Sensor frequency weights — higher = more readings of that type per batch
SENSOR_FREQUENCIES = {
    "heart_rate":  float(os.environ.get("FREQ_HEART_RATE", "1.0")),
    "cadence":     float(os.environ.get("FREQ_CADENCE", "1.0")),
    "pace":        float(os.environ.get("FREQ_PACE", "0.7")),
    "gps":         float(os.environ.get("FREQ_GPS", "0.5")),
    "air_quality": float(os.environ.get("FREQ_AIR_QUALITY", "0.4")),
}

BASE_LAT = 53.3498
BASE_LNG = -6.2603


def lambda_handler(event, context):
    run_id = f"run-lambda-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    sensor_cycle = _build_sensor_cycle()
    readings = []

    for i in range(READINGS_PER_BATCH):
        sensor_type = sensor_cycle[i % len(sensor_cycle)]
        recorded_at = now + timedelta(seconds=i)
        readings.append(_generate_reading(sensor_type, recorded_at, i))

    payload = {
        "fog_node_id": FOG_NODE_ID,
        "run_id": run_id,
        "athlete_name": ATHLETE_NAME,
        "city": CITY,
        "batch_id": f"{run_id}-batch-1",
        "readings": readings,
    }

    logger.info("Dispatching %d readings for run %s to %s", len(readings), run_id, INGEST_URL)

    try:
        req = request.Request(
            INGEST_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            logger.info("Ingest response: %s", result)
            return {
                "statusCode": 200,
                "run_id": run_id,
                "readings_sent": len(readings),
                "mode": result.get("mode"),
            }

    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        logger.error("HTTP %s from backend: %s", exc.code, body)
        raise

    except error.URLError as exc:
        logger.error("Network error reaching backend: %s", exc)
        raise


def _build_sensor_cycle():
    weighted = []
    for sensor_type, freq in SENSOR_FREQUENCIES.items():
        weighted.extend([sensor_type] * max(1, round(freq * 10)))
    random.shuffle(weighted)
    return weighted


def _generate_reading(sensor_type, recorded_at, progress):
    oscillation = math.sin(progress / 4)

    if sensor_type == "heart_rate":
        value = round(140 + (oscillation * 12) + random.uniform(-4, 4), 2)
        return _reading(sensor_type, value, "bpm", recorded_at, risk_flag=value > 170)

    if sensor_type == "cadence":
        value = round(164 + (oscillation * 5) + random.uniform(-2, 2), 2)
        return _reading(sensor_type, value, "spm", recorded_at, risk_flag=value < 155)

    if sensor_type == "pace":
        value = round(5.5 - (oscillation * 0.3) + random.uniform(-0.15, 0.15), 2)
        return _reading(sensor_type, value, "min/km", recorded_at, risk_flag=value > 6.2)

    if sensor_type == "gps":
        lat = round(BASE_LAT + (progress * 0.0004), 6)
        lng = round(BASE_LNG + (progress * 0.00025), 6)
        return _reading(sensor_type, progress, "segment", recorded_at, latitude=lat, longitude=lng)

    # air_quality
    value = round(18 + (oscillation * 6) + random.uniform(-1, 1), 2)
    return _reading(sensor_type, value, "aqi", recorded_at, risk_flag=value > 22)


def _reading(sensor_type, value, unit, recorded_at, latitude=None, longitude=None, risk_flag=False):
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