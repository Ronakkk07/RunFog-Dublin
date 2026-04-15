import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from runnerhub.models import SensorReading


@override_settings(RUNNERHUB_QUEUE_BACKEND="inline", RUNNERHUB_MANUAL_TRIGGER_MODE="local", AWS_REGION="us-east-1")
class IngestionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.token = settings.RUNNERHUB_BACKEND_INGEST_TOKEN
        timestamp = timezone.now().isoformat()
        self.payload = {
            "fog_node_id": "fog-dublin-01",
            "run_id": "run-abc123",
            "athlete_name": "Test Runner",
            "city": "Dublin",
            "readings": [
                {
                    "sensor_type": "heart_rate",
                    "reading_value": 152.4,
                    "unit": "bpm",
                    "recorded_at": timestamp,
                    "quality_score": 0.98,
                    "risk_flag": False,
                },
                {
                    "sensor_type": "gps",
                    "reading_value": 1,
                    "unit": "segment",
                    "recorded_at": (timezone.now() + timedelta(seconds=3)).isoformat(),
                    "latitude": 53.3498,
                    "longitude": -6.2603,
                    "quality_score": 0.95,
                    "risk_flag": False,
                },
            ],
        }

    def _auth_headers(self):
        """Return HTTP_AUTHORIZATION header dict for the test client."""
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_ingest_endpoint_persists_readings(self):
        response = self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "inline")
        self.assertEqual(SensorReading.objects.count(), 2)

    def test_ingest_rejects_missing_token(self):
        """Endpoint must return 401 when no token is provided."""
        response = self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_dashboard_renders(self):
        self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
            **self._auth_headers(),
        )
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RunFog Dublin")
        self.assertContains(response, "Test Runner")

    def test_manual_trigger_creates_data(self):
        response = self.client.post("/api/manual-trigger/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trigger_mode"], "local")
        self.assertGreater(response.json()["readings_sent"], 0)
        self.assertGreater(SensorReading.objects.count(), 0)

    @override_settings(RUNNERHUB_MANUAL_TRIGGER_MODE="broken")
    def test_manual_trigger_returns_json_error_for_invalid_mode(self):
        response = self.client.post("/api/manual-trigger/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("RUNNERHUB_MANUAL_TRIGGER_MODE", response.json()["detail"])

    @override_settings(RUNNERHUB_MANUAL_TRIGGER_MODE="lambda", RUNNERHUB_INGESTOR_LAMBDA_NAME="runfog-fog-injector")
    @patch("runnerhub.services.boto3")
    def test_manual_trigger_handles_lambda_proxy_body(self, mock_boto3):
        payload_stream = Mock()
        payload_stream.read.return_value = json.dumps(
            {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "run_id": "run-manual-proxy",
                        "readings_sent": 20,
                        "mode": "queued",
                    }
                ),
            }
        ).encode("utf-8")

        lambda_client = Mock()
        lambda_client.invoke.return_value = {"Payload": payload_stream}
        mock_boto3.client.return_value = lambda_client

        response = self.client.post("/api/manual-trigger/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trigger_mode"], "lambda")
        self.assertEqual(response.json()["readings_sent"], 20)
