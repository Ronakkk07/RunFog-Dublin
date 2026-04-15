import json
import os
import time
from datetime import timedelta
from urllib import error, request
from uuid import uuid4

from django.core.management.base import BaseCommand
from django.utils import timezone

from runnerhub.fog import build_fog_payload

class Command(BaseCommand):
    help = "Generate runner telemetry and dispatch virtual fog batches to the backend."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backend-url",
            default=os.getenv("RUNNERHUB_BACKEND_URL", "http://127.0.0.1:8000/api/ingest/"),
            help="Full URL of the backend ingest endpoint.",
        )
        parser.add_argument("--fog-node-id", default="")
        parser.add_argument("--athlete-name", default="")
        parser.add_argument("--city", default="")
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
        now = timezone.now()
        athlete_name = options["athlete_name"]

        self.stdout.write(f"Starting fog simulation: {run_id}")
        self.stdout.write(f"Target backend: {options['backend_url']}")

        for batch_index in range(options["batches"]):
            batch_start = now + timedelta(seconds=batch_index * options["dispatch_delay"])
            payload = build_fog_payload(
                fog_node_id=options["fog_node_id"],
                run_id=run_id,
                athlete_name=athlete_name,
                city=options["city"],
                batch_id=f"{run_id}-batch-{batch_index + 1}",
                readings_per_batch=options["readings_per_batch"],
                frequencies={
                    "heart_rate": options["heart_rate_frequency"],
                    "cadence": options["cadence_frequency"],
                    "pace": options["pace_frequency"],
                    "gps": options["gps_frequency"],
                    "air_quality": options["air_quality_frequency"],
                },
                start_time=batch_start,
            )
            self._dispatch(options["backend_url"], payload, options["token"])
            self.stdout.write(
                self.style.SUCCESS(f"Dispatched {payload['batch_id']} ({len(payload['readings'])} readings)")
            )
            time.sleep(options["dispatch_delay"])

        self.stdout.write(self.style.SUCCESS(f"Simulation complete: {options['batches']} batches sent."))

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
