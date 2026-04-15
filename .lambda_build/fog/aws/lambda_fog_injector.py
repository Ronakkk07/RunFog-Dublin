"""
Lambda fog injector for RunFog Dublin.

Recommended trigger:
  EventBridge schedule -> this function -> SQS -> lambda_consumer -> Django

Environment variables:
  AWS_REGION                   - default us-east-1
  RUNNERHUB_SQS_QUEUE_URL      - target SQS queue URL
  FOG_READINGS_PER_BATCH       - default 20
  FOG_NODE_ID                  - default fog-lambda-cloud
  FOG_ATHLETE_NAME             - default Ciaran Kelly
  FOG_CITY                     - default Dublin
  FREQ_HEART_RATE              - default 1.0
  FREQ_CADENCE                 - default 1.0
  FREQ_PACE                    - default 0.7
  FREQ_GPS                     - default 0.5
  FREQ_AIR_QUALITY             - default 0.4
"""

import json
import logging
import os
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runnerhub.fog import build_fog_payload, env_frequencies

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.environ["RUNNERHUB_SQS_QUEUE_URL"]
READINGS_PER_BATCH = int(os.environ.get("FOG_READINGS_PER_BATCH", "20"))
FOG_NODE_ID = os.environ.get("FOG_NODE_ID", "fog-lambda-cloud")
ATHLETE_NAME = os.environ.get("FOG_ATHLETE_NAME", "Ciaran Kelly")
CITY = os.environ.get("FOG_CITY", "Dublin")

sqs = boto3.client("sqs", region_name=AWS_REGION)


def lambda_handler(event, context):
    payload = build_fog_payload(
        fog_node_id=FOG_NODE_ID,
        athlete_name=ATHLETE_NAME,
        city=CITY,
        readings_per_batch=READINGS_PER_BATCH,
        run_id=event.get("run_id"),
        frequencies=env_frequencies(),
    )

    logger.info("Sending %d readings for run %s to SQS", len(payload["readings"]), payload["run_id"])

    response = sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(payload),
    )

    logger.info("SQS MessageId: %s", response["MessageId"])

    return {
        "statusCode": 200,
        "run_id": payload["run_id"],
        "readings_sent": len(payload["readings"]),
        "sqs_message_id": response["MessageId"],
        "mode": "queued",
    }
