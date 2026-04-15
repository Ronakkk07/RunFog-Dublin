import json
import logging
from statistics import mean
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime

from .fog import build_fog_payload, env_frequencies
from .models import SensorReading

logger = logging.getLogger(__name__)

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover
    BotoCoreError = ClientError = Exception


def publish_or_process(batch_payload):
    backend = settings.RUNNERHUB_QUEUE_BACKEND
    if backend == "sqs":
        _publish_to_sqs(batch_payload)
        return {"mode": "queued"}

    persist_batch(batch_payload)
    return {"mode": "inline"}


def trigger_ingestion():
    trigger_mode = settings.RUNNERHUB_MANUAL_TRIGGER_MODE.lower()
    if trigger_mode == "lambda":
        return _invoke_ingestor_lambda()
    if trigger_mode != "local":
        raise RuntimeError("RUNNERHUB_MANUAL_TRIGGER_MODE must be 'local' or 'lambda'")

    payload = build_fog_payload(
        fog_node_id="fog-manual-local",
        athlete_name=None,
        city="Dublin",
        readings_per_batch=20,
        run_id=f"run-manual-{uuid4().hex[:8]}",
        frequencies=env_frequencies(),
    )
    result = publish_or_process(payload)
    return {
        "trigger_mode": "local",
        "run_id": payload["run_id"],
        "readings_sent": len(payload["readings"]),
        **result,
    }


def _publish_to_sqs(batch_payload):
    if not boto3:
        raise RuntimeError("boto3 is required when RUNNERHUB_QUEUE_BACKEND=sqs")
    if not settings.RUNNERHUB_SQS_QUEUE_URL:
        raise RuntimeError("RUNNERHUB_SQS_QUEUE_URL is not configured")

    client = boto3.client("sqs", region_name=settings.AWS_REGION)
    client.send_message(
        QueueUrl=settings.RUNNERHUB_SQS_QUEUE_URL,
        MessageBody=json.dumps(batch_payload),
    )


def _invoke_ingestor_lambda():
    if not boto3:
        raise RuntimeError("boto3 is required when RUNNERHUB_MANUAL_TRIGGER_MODE=lambda")
    if not settings.RUNNERHUB_INGESTOR_LAMBDA_NAME:
        raise RuntimeError("RUNNERHUB_INGESTOR_LAMBDA_NAME is not configured")

    try:
        client = boto3.client("lambda", region_name=settings.AWS_REGION)
        run_id = f"run-manual-{uuid4().hex[:8]}"
        response = client.invoke(
            FunctionName=settings.RUNNERHUB_INGESTOR_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps({"run_id": run_id}).encode("utf-8"),
        )

        payload = response["Payload"].read().decode("utf-8")
        if response.get("FunctionError"):
            raise RuntimeError(payload or "Lambda invocation failed")

        result = json.loads(payload or "{}")
        if isinstance(result.get("body"), str):
            try:
                nested_body = json.loads(result["body"])
            except json.JSONDecodeError:
                nested_body = {}
            if isinstance(nested_body, dict):
                result = {**result, **nested_body}

        if result.get("statusCode") not in (None, 200):
            raise RuntimeError(f"Ingestion Lambda returned statusCode={result.get('statusCode')}: {payload}")

        if "readings_sent" not in result:
            raise RuntimeError(f"Unexpected ingestion Lambda response: {payload}")

        return {
            "trigger_mode": "lambda",
            "run_id": result.get("run_id", run_id),
            "readings_sent": result["readings_sent"],
            "mode": result.get("mode", "queued"),
        }
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Manual Lambda invocation failed")
        raise RuntimeError(f"Unable to invoke ingestion Lambda: {exc}") from exc


@transaction.atomic
def persist_batch(batch_payload):
    fog_node_id = batch_payload["fog_node_id"]
    run_id = batch_payload["run_id"]
    athlete_name = batch_payload.get("athlete_name", "Demo Runner")
    city = batch_payload.get("city", "Dublin")
    readings = []

    for reading in batch_payload.get("readings", []):
        recorded_at = parse_datetime(reading["recorded_at"])
        if recorded_at is None:
            raise ValueError(f"Invalid recorded_at value: {reading['recorded_at']}")

        readings.append(
            SensorReading(
                fog_node_id=fog_node_id,
                run_id=run_id,
                athlete_name=athlete_name,
                city=city,
                sensor_type=reading["sensor_type"],
                reading_value=reading["reading_value"],
                unit=reading["unit"],
                latitude=reading.get("latitude"),
                longitude=reading.get("longitude"),
                quality_score=reading.get("quality_score", 0),
                risk_flag=reading.get("risk_flag", False),
                recorded_at=recorded_at,
            )
        )

    SensorReading.objects.bulk_create(readings)
    logger.info("Persisted %s readings for run %s", len(readings), run_id)
    return len(readings)


def build_dashboard_summary():
    readings = SensorReading.objects.all()[:500]
    sensor_types = {choice[0]: choice[1] for choice in SensorReading.SENSOR_TYPES}
    cards = []

    for sensor_type, label in sensor_types.items():
        typed = [reading for reading in readings if reading.sensor_type == sensor_type]
        if not typed:
            continue
        latest = typed[0]
        cards.append(
            {
                "key": sensor_type,
                "label": label,
                "latest_value": round(latest.reading_value, 2),
                "unit": latest.unit,
                "average_value": round(mean(item.reading_value for item in typed), 2),
                "latest_timestamp": latest.recorded_at,
                "risk_events": sum(1 for item in typed if item.risk_flag),
            }
        )

    recent_runs = []
    seen_runs = set()
    for reading in readings:
        if reading.run_id in seen_runs:
            continue
        seen_runs.add(reading.run_id)
        run_readings = [item for item in readings if item.run_id == reading.run_id]
        recent_runs.append(
            {
                "run_id": reading.run_id,
                "athlete_name": reading.athlete_name,
                "city": reading.city,
                "fog_node_id": reading.fog_node_id,
                "reading_count": len(run_readings),
                "started_at": run_readings[-1].recorded_at,
                "latest_at": run_readings[0].recorded_at,
            }
        )
        if len(recent_runs) == 6:
            break

    return {
        "total_readings": SensorReading.objects.count(),
        "active_runs": len(seen_runs),
        "risk_events": SensorReading.objects.filter(risk_flag=True).count(),
        "cards": cards,
        "recent_runs": recent_runs,
    }
