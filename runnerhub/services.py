import json
import logging
from collections import defaultdict
from statistics import mean
from uuid import uuid4

from django.conf import settings
from django.db.models import Count, Max, Q
from django.db import transaction
from django.utils import timezone
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


TIME_RANGE_OPTIONS = {
    "all": {"label": "All time", "delta": None},
    "1h": {"label": "Last hour", "delta": 60 * 60},
    "24h": {"label": "Last 24 hours", "delta": 24 * 60 * 60},
    "7d": {"label": "Last 7 days", "delta": 7 * 24 * 60 * 60},
    "30d": {"label": "Last 30 days", "delta": 30 * 24 * 60 * 60},
}

SENSOR_COLORS = {
    "heart_rate": "#d85858",
    "cadence": "#d79c3a",
    "pace": "#2e7d62",
    "gps": "#3f6fb3",
    "air_quality": "#7560aa",
}


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
        fog_node_id=None,
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
                anomaly_type=reading.get("anomaly_type", ""),
                anomaly_severity=reading.get("anomaly_severity", ""),
                anomaly_message=reading.get("anomaly_message", ""),
                processing_stage=reading.get("processing_stage", ""),
                recorded_at=recorded_at,
            )
        )

    SensorReading.objects.bulk_create(readings)
    logger.info("Persisted %s readings for run %s", len(readings), run_id)
    return len(readings)


def normalize_filters(filters=None):
    filters = filters or {}
    sensor_keys = {choice[0] for choice in SensorReading.SENSOR_TYPES}
    time_range = filters.get("time_range", "all")
    sensor_type = filters.get("sensor_type", "")

    if time_range not in TIME_RANGE_OPTIONS:
        time_range = "all"
    if sensor_type and sensor_type not in sensor_keys:
        sensor_type = ""

    return {
        "athlete_name": (filters.get("athlete_name") or "").strip(),
        "fog_node_id": (filters.get("fog_node_id") or "").strip(),
        "run_id": (filters.get("run_id") or "").strip(),
        "sensor_type": sensor_type,
        "time_range": time_range,
    }


def get_filtered_queryset(filters=None):
    filters = normalize_filters(filters)
    queryset = SensorReading.objects.all()

    if filters["athlete_name"]:
        queryset = queryset.filter(athlete_name=filters["athlete_name"])
    if filters["fog_node_id"]:
        queryset = queryset.filter(fog_node_id=filters["fog_node_id"])
    if filters["run_id"]:
        queryset = queryset.filter(run_id=filters["run_id"])
    if filters["sensor_type"]:
        queryset = queryset.filter(sensor_type=filters["sensor_type"])

    delta_seconds = TIME_RANGE_OPTIONS[filters["time_range"]]["delta"]
    if delta_seconds:
        queryset = queryset.filter(recorded_at__gte=timezone.now() - timezone.timedelta(seconds=delta_seconds))

    return queryset.order_by("-recorded_at")


def build_dashboard_summary(filters=None):
    filters = normalize_filters(filters)
    queryset = get_filtered_queryset(filters)
    readings = list(queryset[:1000])

    return {
        "selected_filters": filters,
        "filter_options": build_filter_options(),
        "total_readings": queryset.count(),
        "active_runs": queryset.values("run_id").distinct().count(),
        "risk_events": queryset.filter(risk_flag=True).count(),
        "anomaly_events": queryset.exclude(anomaly_type="").count(),
        "cards": build_metric_cards(readings),
        "fog_nodes": build_fog_node_breakdown(queryset),
        "recent_runs": build_recent_runs(readings),
        "trends": build_trend_series(readings),
        "risk_explanations": build_risk_explanations(readings),
        "fog_anomalies": build_fog_anomalies(readings),
        "has_filters": any(filters.values()),
    }


def build_run_detail(run_id):
    queryset = SensorReading.objects.filter(run_id=run_id).order_by("-recorded_at")
    readings = list(queryset[:1000])
    if not readings:
        return None

    latest = readings[0]
    oldest = readings[-1]
    return {
        "run_id": run_id,
        "athlete_name": latest.athlete_name,
        "city": latest.city,
        "fog_node_id": latest.fog_node_id,
        "reading_count": len(readings),
        "risk_events": sum(1 for reading in readings if reading.risk_flag),
        "anomaly_count": sum(1 for reading in readings if reading.anomaly_type),
        "started_at": oldest.recorded_at,
        "latest_at": latest.recorded_at,
        "cards": build_metric_cards(readings),
        "trends": build_trend_series(readings, max_points=20),
        "risk_explanations": build_risk_explanations(readings),
        "fog_anomalies": build_fog_anomalies(readings),
        "readings": [
            serialize_reading(reading)
            for reading in readings[:80]
        ],
        "gps_path": [
            {
                "latitude": reading.latitude,
                "longitude": reading.longitude,
                "recorded_at": serialize_timestamp(reading.recorded_at),
            }
            for reading in reversed(readings)
            if reading.sensor_type == "gps" and reading.latitude is not None and reading.longitude is not None
        ],
    }


def build_export_rows(filters=None):
    return [serialize_reading(reading) for reading in get_filtered_queryset(filters)]


def build_filter_options():
    sensor_types = [{"value": key, "label": label} for key, label in SensorReading.SENSOR_TYPES]
    athletes = list(
        SensorReading.objects.order_by("athlete_name")
        .values_list("athlete_name", flat=True)
        .distinct()
    )
    fog_nodes = list(
        SensorReading.objects.order_by("fog_node_id")
        .values_list("fog_node_id", flat=True)
        .distinct()
    )
    run_choices = []
    seen_runs = set()
    for reading in SensorReading.objects.order_by("-recorded_at")[:200]:
        if reading.run_id in seen_runs:
            continue
        seen_runs.add(reading.run_id)
        run_choices.append(
            {
                "run_id": reading.run_id,
                "athlete_name": reading.athlete_name,
                "label": f"{reading.run_id} - {reading.athlete_name}",
            }
        )
        if len(run_choices) == 30:
            break

    return {
        "athletes": athletes,
        "fog_nodes": fog_nodes,
        "runs": run_choices,
        "sensor_types": sensor_types,
        "time_ranges": [
            {"value": value, "label": config["label"]}
            for value, config in TIME_RANGE_OPTIONS.items()
        ],
    }


def build_metric_cards(readings):
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
                "latest_timestamp": serialize_timestamp(latest.recorded_at),
                "risk_events": sum(1 for item in typed if item.risk_flag),
                "color": SENSOR_COLORS.get(sensor_type, "#1d6b53"),
            }
        )

    return cards


def build_recent_runs(readings):
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
                "risk_events": sum(1 for item in run_readings if item.risk_flag),
                "started_at": serialize_timestamp(run_readings[-1].recorded_at),
                "latest_at": serialize_timestamp(run_readings[0].recorded_at),
            }
        )
        if len(recent_runs) == 8:
            break
    return recent_runs


def build_fog_node_breakdown(queryset):
    rows = (
        queryset.values("fog_node_id", "city")
        .annotate(
            reading_count=Count("id"),
            run_count=Count("run_id", distinct=True),
            risk_events=Count("id", filter=Q(risk_flag=True)),
            anomaly_events=Count("id", filter=~Q(anomaly_type="")),
            last_seen=Max("recorded_at"),
        )
        .order_by("-reading_count", "fog_node_id")
    )
    return [
        {
            "fog_node_id": row["fog_node_id"],
            "city": row["city"],
            "reading_count": row["reading_count"],
            "run_count": row["run_count"],
            "risk_events": row["risk_events"],
            "anomaly_events": row["anomaly_events"],
            "last_seen": serialize_timestamp(row["last_seen"]),
        }
        for row in rows
    ]


def build_trend_series(readings, max_points=12):
    sensor_types = {choice[0]: choice[1] for choice in SensorReading.SENSOR_TYPES}
    grouped = defaultdict(list)
    for reading in readings:
        grouped[reading.sensor_type].append(reading)

    trends = []
    for sensor_type, label in sensor_types.items():
        typed = grouped.get(sensor_type, [])
        if not typed:
            continue
        points = list(reversed(typed[:max_points]))
        trends.append(
            {
                "key": sensor_type,
                "label": label,
                "unit": typed[0].unit,
                "color": SENSOR_COLORS.get(sensor_type, "#1d6b53"),
                "points": [
                    {
                        "timestamp": serialize_timestamp(point.recorded_at),
                        "value": round(point.reading_value, 2),
                    }
                    for point in points
                ],
            }
        )
    return trends


def build_risk_explanations(readings):
    risk_readings = [reading for reading in readings if reading.risk_flag][:12]
    sensor_labels = {choice[0]: choice[1] for choice in SensorReading.SENSOR_TYPES}
    return [
        {
            "run_id": reading.run_id,
            "athlete_name": reading.athlete_name,
            "fog_node_id": reading.fog_node_id,
            "sensor_type": reading.sensor_type,
            "sensor_label": sensor_labels.get(reading.sensor_type, reading.sensor_type),
            "reading_value": round(reading.reading_value, 2),
            "unit": reading.unit,
            "recorded_at": serialize_timestamp(reading.recorded_at),
            "anomaly_type": reading.anomaly_type,
            "anomaly_severity": reading.anomaly_severity,
            "explanation": risk_explanation(reading),
        }
        for reading in risk_readings
    ]


def build_fog_anomalies(readings):
    sensor_labels = {choice[0]: choice[1] for choice in SensorReading.SENSOR_TYPES}
    anomaly_readings = [reading for reading in readings if reading.anomaly_type][:12]
    return [
        {
            "run_id": reading.run_id,
            "athlete_name": reading.athlete_name,
            "fog_node_id": reading.fog_node_id,
            "sensor_type": reading.sensor_type,
            "sensor_label": sensor_labels.get(reading.sensor_type, reading.sensor_type),
            "anomaly_type": reading.anomaly_type,
            "anomaly_severity": reading.anomaly_severity or "medium",
            "message": reading.anomaly_message,
            "recorded_at": serialize_timestamp(reading.recorded_at),
            "reading_value": round(reading.reading_value, 2),
            "unit": reading.unit,
        }
        for reading in anomaly_readings
    ]


def risk_explanation(reading):
    if reading.anomaly_message:
        return reading.anomaly_message
    if reading.sensor_type == "heart_rate":
        return f"Heart rate rose above the 170 bpm alert threshold at {round(reading.reading_value, 1)} bpm."
    if reading.sensor_type == "cadence":
        return f"Cadence dropped below the 155 spm efficiency threshold at {round(reading.reading_value, 1)} spm."
    if reading.sensor_type == "pace":
        return f"Pace slowed beyond the 6.2 min/km threshold at {round(reading.reading_value, 1)} min/km."
    if reading.sensor_type == "air_quality":
        return f"Air quality crossed the AQI 22 comfort threshold at {round(reading.reading_value, 1)} AQI."
    return "This reading was marked as risky by the fog node rules."


def serialize_reading(reading):
    return {
        "run_id": reading.run_id,
        "athlete_name": reading.athlete_name,
        "city": reading.city,
        "fog_node_id": reading.fog_node_id,
        "sensor_type": reading.sensor_type,
        "sensor_label": reading.get_sensor_type_display(),
        "reading_value": round(reading.reading_value, 2),
        "unit": reading.unit,
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "quality_score": round(reading.quality_score, 2),
        "risk_flag": reading.risk_flag,
        "anomaly_type": reading.anomaly_type,
        "anomaly_severity": reading.anomaly_severity,
        "anomaly_message": reading.anomaly_message,
        "processing_stage": reading.processing_stage,
        "risk_explanation": risk_explanation(reading) if reading.risk_flag else "",
        "recorded_at": serialize_timestamp(reading.recorded_at),
    }


def serialize_timestamp(value):
    return value.isoformat() if value else None
