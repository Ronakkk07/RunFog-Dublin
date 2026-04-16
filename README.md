# RunFog Dublin

RunFog Dublin is a fog and edge computing coursework project for runner telemetry in Dublin. It simulates wearable and environmental sensors, processes them through virtual fog nodes, and presents the results in a Django dashboard that can run locally or on AWS.

## Architecture

1. Sensors generate heart rate, cadence, pace, GPS, and air quality readings.
2. A virtual fog node receives those readings, batches them, and enriches them with quality, risk, and anomaly metadata.
3. Django accepts the payload, either storing it inline or publishing it to Amazon SQS.
4. An AWS Lambda consumer reads SQS messages and posts them back to the backend for persistence.
5. The dashboard polls the summary API so scheduled ingestion appears automatically in the frontend.
6. A manual trigger button can either generate data locally or invoke the AWS ingestion Lambda.

## Current feature set

### Sensor and fog layer

- Five configurable sensor types:
  - heart rate
  - cadence
  - pace
  - GPS
  - air quality
- Multiple virtual fog nodes:
  - `fog-dublin-north`
  - `fog-dublin-south`
  - `fog-campus-west`
- Fog-side anomaly detection for:
  - high heart rate spike
  - poor air quality segment
  - pace collapse
  - missing GPS sample
- Configurable frequency controls through environment variables or the local simulator command
- Batch-based dispatch from fog to backend

### Dashboard and backend

- Live summary cards for sensor values and run activity
- Fog Node Activity panel showing readings, runs, risk events, and anomaly counts per fog node
- Fog-side Anomalies panel showing recent anomaly detections from the fog layer
- Sensor trend charts
- Recent runs table with drill-down pages
- Run detail page with readings, trends, and anomaly explanations
- Filters by athlete, fog node, run, sensor type, and time range
- Export to JSON and CSV
- Manual trigger button for demos
- Auto-refresh polling in the frontend

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

### Local data flow options

Use the dashboard button:

- `RUNNERHUB_MANUAL_TRIGGER_MODE=local` generates a batch inside Django.
- `RUNNERHUB_MANUAL_TRIGGER_MODE=lambda` invokes the AWS ingestion Lambda from the backend.

Or run the simulator manually:

```bash
python manage.py simulate_fog --backend-url http://127.0.0.1:8000/api/ingest/
```

To keep batches flowing from your machine:

```bash
bash ./fog_runner.sh
```

The simulator supports optional fog-node selection. Leave `--fog-node-id` blank to let the project choose a virtual fog node automatically.

## AWS deployment

### 1. Create the backend on Elastic Beanstalk

Deploy this repository as a Docker application. Set these Elastic Beanstalk environment variables:

- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=<your-eb-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-eb-domain>`
- `RUNNERHUB_QUEUE_BACKEND=sqs`
- `RUNNERHUB_SQS_QUEUE_URL=<your-sqs-url>`
- `RUNNERHUB_BACKEND_INGEST_TOKEN=<shared-secret>`
- `RUNNERHUB_MANUAL_TRIGGER_MODE=lambda`
- `RUNNERHUB_INGESTOR_LAMBDA_NAME=<lambda-fog-injector-name>`
- `AWS_REGION=<your-region>`
- `RUNNERHUB_FRONTEND_POLL_SECONDS=15`

The Beanstalk instance profile must be allowed to invoke the ingestion Lambda if you want the frontend button to trigger AWS ingestion.

### 2. Create SQS

Create an SQS queue for batch payloads, for example `runfog-batches`.

### 3. Deploy the Lambda consumer

Use `aws/lambda_consumer.py` for the SQS-triggered Lambda.

Required Lambda environment variables:

- `RUNNERHUB_PROCESS_URL=https://<your-eb-domain>/api/internal/process/`
- `RUNNERHUB_BACKEND_INGEST_TOKEN=<shared-secret>`

Attach the SQS queue as the trigger.

### 4. Deploy the ingestion Lambda

Use `aws/lambda_fog_injector.py` for scheduled or manual telemetry generation.

Required environment variables:

- `RUNNERHUB_SQS_QUEUE_URL=<your-sqs-url>`
- `AWS_REGION=<your-region>`
- `FOG_READINGS_PER_BATCH=20`
- `FOG_NODE_ID=` for random virtual fog nodes, or set a fixed node such as `fog-dublin-north`
- `FOG_ATHLETE_NAME=` for random athlete names, or set a fixed athlete
- `FOG_CITY=Dublin`

Optional frequency controls:

- `FREQ_HEART_RATE`
- `FREQ_CADENCE`
- `FREQ_PACE`
- `FREQ_GPS`
- `FREQ_AIR_QUALITY`

### 5. Schedule automatic ingestion

Create an EventBridge rule or EventBridge Scheduler entry that invokes the ingestion Lambda on a fixed interval, such as every 2 minutes.

Example schedule expression:

```text
rate(2 minutes)
```

That gives you:

`EventBridge -> lambda_fog_injector -> SQS -> lambda_consumer -> Elastic Beanstalk -> dashboard polling`

## Data model highlights

Each reading currently stores:

- `fog_node_id`
- `run_id`
- `athlete_name`
- `city`
- `sensor_type`
- `reading_value`
- `unit`
- `latitude` / `longitude` where relevant
- `quality_score`
- `risk_flag`
- `anomaly_type`
- `anomaly_severity`
- `anomaly_message`
- `processing_stage`
- `recorded_at`

## Local AWS credentials

When developing locally, configure AWS credentials on your machine so Django can invoke Lambda and publish to SQS when needed:

```bash
aws configure
```

Or set standard AWS environment variables such as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_DEFAULT_REGION`.

## Tests

```bash
python manage.py test
```

## Coursework fit

- Sensor and fog layer:
  - configurable simulated sensors
  - virtual fog nodes
  - fog-side batching and anomaly detection
- Backend layer:
  - scalable ingestion API
  - queue integration with SQS
  - Lambda-based consumption
  - responsive dashboards, run drill-downs, and exports
- Cloud deployment:
  - Docker
  - Elastic Beanstalk
  - SQS
  - Lambda
  - EventBridge scheduling
- Runner focus:
  - a Strava-inspired Dublin running telemetry scenario that is practical to demo
