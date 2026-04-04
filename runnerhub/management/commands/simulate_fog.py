import json
import math
import os
import random
import time
from datetime import timedelta
from urllib import error, request
from uuid import uuid4

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Generate runner telemetry and dispatch virtual fog batches to the backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backend-url",
            default=os.getenv("RUNNERHUB_BACKEND_URL", "http://127.0.0.1:8000/api/ingest/"),
            help="Full URL of the backend ingest endpoint.",
        )
        parser.add_argument("--fog-node-id", default="fog-dublin-cloud9")
        parser.add_argument("--athlete-name", default="Aoife Murphy")
        parser.add_argument("--city", default="Dublin")
        parser.add_argument("--batches", type=int, default=5)
        parser.add_argument("--readings-per-batch", type=int, default=15)
        parser.add_argument("--dispatch-delay", type=float, default=1.0)
        parser.add_argument("--heart-rate-frequency", type=float, default=1.0)
        parser.add_argument("--cadence-frequency", type=float, default=1.0)
        parser.add_argument("--pace-frequency", type=float, default=0.5)
        parser.add_argument("--gps-frequency", type=float, default=0.3)
        parser.add_argument("--air-quality-frequency", type=float, default=0.2)
        parser.add_argument(
            "--token",
            default=os.getenv("RUNNERHUB_BACKEND_INGEST_TOKEN", ""),
            help="Bearer token for the ingest endpoint (matches RUNNERHUB_BACKEND_INGEST_TOKEN).",
        )

    def handle(self, *args, **options):
        run_id = f"run-{uuid4().hex[:8]}"
        base_lat = 53.3498
        base_lng = -6.2603
        now = timezone.now()
        sensor_cycle = self._build_sensor_cycle(options)

        self.stdout.write(f"Starting fog simulation: {run_id}")
        self.stdout.write(f"Target backend: {options['backend_url']}")

        for batch_index in range(options["batches"]):
            readings = []
            batch_start = now + timedelta(seconds=batch_index * options["dispatch_delay"])
            for reading_index in range(options["readings_per_batch"]):
                sensor_type = sensor_cycle[(batch_index + reading_index) % len(sensor_cycle)]
                recorded_at = batch_start + timedelta(seconds=reading_index)
                progress = batch_index * options["readings_per_batch"] + reading_index
                readings.append(
                    self._generate_reading(sensor_type, recorded_at, base_lat, base_lng, progress)
                )

            payload = {
                "fog_node_id": options["fog_node_id"],
                "run_id": run_id,
                "athlete_name": options["athlete_name"],
                "city": options["city"],
                "batch_id": f"{run_id}-batch-{batch_index + 1}",
                "readings": readings,
            }
            self._dispatch(options["backend_url"], payload, options["token"])
            self.stdout.write(self.style.SUCCESS(f"Dispatched {payload['batch_id']} ({len(readings)} readings)"))
            time.sleep(options["dispatch_delay"])

        self.stdout.write(self.style.SUCCESS(f"Simulation complete: {options['batches']} batches sent."))

    def _build_sensor_cycle(self, options):
        weighted = []
        config = {
            "heart_rate": options["heart_rate_frequency"],
            "cadence": options["cadence_frequency"],
            "pace": options["pace_frequency"],
            "gps": options["gps_frequency"],
            "air_quality": options["air_quality_frequency"],
        }
        for sensor_type, frequency in config.items():
            weighted.extend([sensor_type] * max(1, round(frequency * 10)))
        random.shuffle(weighted)
        return weighted

    def _generate_reading(self, sensor_type, recorded_at, base_lat, base_lng, progress):
        oscillation = math.sin(progress / 4)
        if sensor_type == "heart_rate":
            value = round(140 + (oscillation * 12) + random.uniform(-4, 4), 2)
            return self._reading(sensor_type, value, "bpm", recorded_at, risk_flag=value > 170)
        if sensor_type == "cadence":
            value = round(164 + (oscillation * 5) + random.uniform(-2, 2), 2)
            return self._reading(sensor_type, value, "spm", recorded_at, risk_flag=value < 155)
        if sensor_type == "pace":
            value = round(5.5 - (oscillation * 0.3) + random.uniform(-0.15, 0.15), 2)
            return self._reading(sensor_type, value, "min/km", recorded_at, risk_flag=value > 6.2)
        if sensor_type == "gps":
            latitude = round(base_lat + (progress * 0.0004), 6)
            longitude = round(base_lng + (progress * 0.00025), 6)
            return self._reading(sensor_type, progress, "segment", recorded_at, latitude, longitude)
        value = round(18 + (oscillation * 6) + random.uniform(-1, 1), 2)
        return self._reading(sensor_type, value, "aqi", recorded_at, risk_flag=value > 22)

    def _reading(self, sensor_type, value, unit, recorded_at, latitude=None, longitude=None, risk_flag=False):
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

    def _dispatch(self, backend_url, payload, token=""):
        encoded = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(backend_url, data=encoded, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=15) as response:
                body = response.read().decode("utf-8")
                self.stdout.write(f"  Response: {body}")
        except error.URLError as exc:
            raise RuntimeError(f"Fog dispatch failed: {exc}") from exc