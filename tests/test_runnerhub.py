import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from runnerhub.fog import available_fog_nodes
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
                    "reading_value": 182.4,
                    "unit": "bpm",
                    "recorded_at": timestamp,
                    "quality_score": 0.98,
                    "risk_flag": True,
                    "anomaly_type": "high_heart_rate_spike",
                    "anomaly_severity": "critical",
                    "anomaly_message": "Fog node detected a sudden heart-rate spike.",
                    "processing_stage": "fog",
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
        self.assertEqual(
            SensorReading.objects.get(sensor_type="heart_rate", run_id="run-abc123").anomaly_type,
            "high_heart_rate_spike",
        )

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
        self.assertContains(response, "Filters")

    def test_manual_trigger_creates_data(self):
        response = self.client.post("/api/manual-trigger/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trigger_mode"], "local")
        self.assertGreater(response.json()["readings_sent"], 0)
        self.assertGreater(SensorReading.objects.count(), 0)
        self.assertTrue(SensorReading.objects.latest("id").athlete_name)
        self.assertIn(SensorReading.objects.latest("id").fog_node_id, available_fog_nodes())

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

    def test_summary_api_supports_filters(self):
        self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
            **self._auth_headers(),
        )
        second_payload = {
            **self.payload,
            "fog_node_id": "fog-campus-west",
            "run_id": "run-def456",
            "athlete_name": "Second Runner",
            "readings": [
                {
                    "sensor_type": "cadence",
                    "reading_value": 150.0,
                    "unit": "spm",
                    "recorded_at": timezone.now().isoformat(),
                    "quality_score": 0.93,
                    "risk_flag": True,
                }
            ],
        }
        self.client.post(
            "/api/ingest/",
            data=json.dumps(second_payload),
            content_type="application/json",
            **self._auth_headers(),
        )

        response = self.client.get("/api/summary/?athlete_name=Second+Runner&sensor_type=cadence&fog_node_id=fog-campus-west")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_readings"], 1)
        self.assertEqual(data["active_runs"], 1)
        self.assertEqual(data["cards"][0]["key"], "cadence")
        self.assertEqual(data["fog_nodes"][0]["fog_node_id"], "fog-campus-west")

    def test_summary_api_returns_anomaly_and_fog_node_breakdown(self):
        self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
            **self._auth_headers(),
        )

        response = self.client.get("/api/summary/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["anomaly_events"], 1)
        self.assertEqual(data["fog_nodes"][0]["fog_node_id"], "fog-dublin-01")
        self.assertEqual(data["fog_anomalies"][0]["anomaly_type"], "high_heart_rate_spike")

    def test_export_json_and_csv(self):
        self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
            **self._auth_headers(),
        )

        json_response = self.client.get("/api/export/?format=json&run_id=run-abc123")
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json()["count"], 2)

        csv_response = self.client.get("/api/export/?format=csv&run_id=run-abc123")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertIn("run-abc123", csv_response.content.decode("utf-8"))

    def test_run_detail_page_and_api(self):
        self.client.post(
            "/api/ingest/",
            data=json.dumps(self.payload),
            content_type="application/json",
            **self._auth_headers(),
        )

        page_response = self.client.get("/runs/run-abc123/")
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Latest Readings")

        api_response = self.client.get("/api/runs/run-abc123/")
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()["run_id"], "run-abc123")
        self.assertEqual(api_response.json()["anomaly_count"], 1)
