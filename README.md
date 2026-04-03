# RunFog Dublin

RunFog Dublin is a fog and edge computing coursework project for runner telemetry in Dublin. It simulates wearable and environmental sensors, processes them through virtual fog nodes, and pushes the data into a cloud-ready Django backend with queue-ready ingestion.

## Architecture

1. Sensors: five virtual sensor types generate live readings for runners.
2. Fog node: batches, enriches, and forwards readings through a single payload.
3. Backend: Django exposes ingestion APIs and a responsive dashboard.
4. Scalability: the backend can process inline for local demos or publish batches to Amazon SQS.
5. Cloud processing: an AWS Lambda consumer reads from SQS and posts processed messages back into the backend.
6. Hosting: the web service is Dockerised so it can be deployed on Elastic Beanstalk and pulled into Cloud9 consistently.

## Sensor Types

- Heart rate
- Cadence
- Pace
- GPS
- Air quality

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

In another terminal, simulate fog traffic:

```bash
python manage.py simulate_fog --batches 6 --readings-per-batch 20
```

Open `http://127.0.0.1:8000/` to view the dashboard.

## AWS Deployment Path

### Elastic Beanstalk backend

1. Create an Elastic Beanstalk Docker environment.
2. Set environment variables:
   - `DJANGO_DEBUG=False`
   - `DJANGO_ALLOWED_HOSTS=<your-eb-domain>`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-eb-domain>`
   - `RUNNERHUB_QUEUE_BACKEND=sqs`
   - `RUNNERHUB_SQS_QUEUE_URL=<your-sqs-url>`
   - `RUNNERHUB_BACKEND_INGEST_TOKEN=<shared-secret>`
3. Deploy this repository as-is because the Dockerfile is included.

### SQS and Lambda

1. Create an SQS queue for fog payload batches.
2. Create a Lambda function using `aws/lambda_consumer.py`.
3. Set Lambda environment variables:
   - `RUNNERHUB_PROCESS_URL=https://<your-eb-domain>/api/internal/process/`
   - `RUNNERHUB_BACKEND_INGEST_TOKEN=<shared-secret>`
4. Add the SQS queue as the Lambda trigger.

### Cloud9 fog simulation

Pull this repository into Cloud9 and run:

```bash
pip install -r requirements.txt
python manage.py simulate_fog --backend-url https://<your-eb-domain>/api/ingest/
```

## Coursework Fit

- Sensor and fog layer: configurable simulated sensors and virtual fog dispatch.
- Backend layer: scalable ingestion API, queue integration, and dashboarding.
- Cloud deployment: Docker + Elastic Beanstalk + SQS + Lambda.
- Runner focus: a Strava-inspired Dublin running telemetry scenario that is practical to demo and explain.
