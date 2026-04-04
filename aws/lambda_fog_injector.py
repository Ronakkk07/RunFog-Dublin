"""
Lambda Fog Injector for RunFog Dublin
--------------------------------------
Acts as a cloud-side fog node. Generates sensor readings and pushes
them directly to SQS. The SQS consumer Lambda then picks them up
and persists them via the EB backend.

This approach works within AWS Academy LabRole permissions because
Lambda already has SQS access — the EB EC2 instance role does not.

Architecture:
  EventBridge (every 2 min)
    → this function
    → SQS (runfog-batches)
    → lambda_consumer
    → POST /api/internal/process/
    → Django persists to SQLite
    → Dashboard

Environment variables:
  RUNNERHUB_SQS_QUEUE_URL        - https://sqs.us-east-1.amazonaws.com/<account>/runfog-batches
  FOG_READINGS_PER_BATCH         - default 20
  FOG_NODE_ID                    - default fog-lambda-cloud
  FOG_ATHLETE_NAME               - default Ciarán Kelly
  FOG_CITY                       - default Dublin
  FREQ_HEART_RATE                - default 1.0
  FREQ_CADENCE                   - default 1.0
  FREQ_PACE                      - default 0.7
  FREQ_GPS                       - default 0.5
  FREQ_AIR_QUALITY               - default 0.4
"""

import json
import logging
import math
import os
import random
import boto3
from datetime import datetime, timezone, timedelta
from uuid import uuid4

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SQS_QUEUE_URL = os.environ["RUNNERHUB_SQS_QUEUE_URL"]

READINGS_PER_BATCH = int(os.environ.get("FOG_READINGS_PER_BATCH", "20"))
FOG_NODE_ID = os.environ.get("FOG_NODE_ID", "fog-lambda-cloud")
ATHLETE_NAME = os.environ.get("FOG_ATHLETE_NAME", "Ciarán Kelly")
CITY = os.environ.get("FOG_CITY", "Dublin")

SENSOR_FREQUENCIES = {
    "heart_rate":  float(os.environ.get("FREQ_HEART_RATE", "1.0")),
    "cadence":     float(os.environ.get("FREQ_CADENCE", "1.0")),
    "pace":        float(os.environ.get("FREQ_PACE", "0.7")),
    "gps":         float(os.environ.get("FREQ_GPS", "0.5")),
    "air_quality": float(os.environ.get("FREQ_AIR_QUALITY", "0.4")),
}

BASE_LAT = 53.3498
BASE_LNG = -6.2603

sqs = boto3.client("sqs", region_name="us-east-1")


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

    logger.info("Sending %d readings for run %s to SQS", len(readings), run_id)

    response = sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(payload),
    )

    logger.info("SQS MessageId: %s", response["MessageId"])

    return {
        "statusCode": 200,
        "run_id": run_id,
        "readings_sent": len(readings),
        "sqs_message_id": response["MessageId"],
        "mode": "queued",
    }


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