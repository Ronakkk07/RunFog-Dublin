# Technical Report Notes

## Project concept

RunFog Dublin monitors runner activity across popular Dublin running routes using virtual sensors inspired by wearable devices and environmental probes. The system is designed to feel realistic for runners who already use activity platforms such as Strava, while staying simple enough to build and demonstrate for coursework.

## Why this project fits fog and edge computing

The edge layer simulates raw sensors attached to a runner. The fog layer acts as an intermediate processing node that:

- collects high-frequency sensor data
- batches events to reduce backend load
- enriches payloads with quality and risk markers
- forwards a compact payload into the cloud backend

This mirrors real fog computing where processing is pushed closer to the data source before sending it to a central platform.

## Sensor model

The project uses five sensor types:

1. Heart rate in bpm
2. Cadence in steps per minute
3. Pace in min/km
4. GPS progress with latitude and longitude
5. Air quality index

Each stream can be tuned with configurable frequency weights and dispatch settings in the fog simulator command.

## Scalable cloud design

The backend supports two modes:

1. Inline mode for local development and demos
2. SQS mode for cloud deployment

In SQS mode, the ingestion API accepts fog payloads quickly and pushes them to Amazon SQS. AWS Lambda consumes queued messages and calls the protected backend processing endpoint. This separates ingress from persistence and demonstrates horizontal scalability.

## Deployment choice

Elastic Beanstalk was chosen for the web service because it simplifies deployment, environment variables, autoscaling, and Docker support. Docker ensures the same runtime works locally, in Cloud9, and in the public cloud.

## Dashboard

The dashboard presents:

- total readings
- active runs
- risk events
- latest values per sensor type
- recent run summaries

The layout is responsive so it works well during a live demonstration on both laptop and mobile-sized screens.

## Limitations and future work

- It currently uses mock sensors rather than direct hardware integration.
- Strava is used only as inspiration; no live Strava API integration is required.
- A future version could add route heatmaps, anomaly alerts, or a real PostgreSQL backend.
