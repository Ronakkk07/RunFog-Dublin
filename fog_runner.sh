#!/bin/bash
# fog_runner.sh
# Simulates a continuously running fog node dispatching to the backend.
# Run this locally to keep data flowing into the dashboard.
#
# Usage:
#   chmod +x fog_runner.sh
#   ./fog_runner.sh
#
# Stop with Ctrl+C

set -e

BACKEND_URL="${RUNNERHUB_BACKEND_URL:-http://127.0.0.1:8000/api/ingest/}"
TOKEN="${RUNNERHUB_BACKEND_INGEST_TOKEN:-change-me-local}"
BATCHES="${FOG_BATCHES:-3}"
READINGS="${FOG_READINGS_PER_BATCH:-15}"
DELAY="${FOG_DISPATCH_DELAY:-2}"
PAUSE_BETWEEN_RUNS="${FOG_PAUSE:-30}"

echo "========================================"
echo " RunFog Dublin - Fog Node Simulator"
echo "========================================"
echo " Backend : $BACKEND_URL"
echo " Batches per run   : $BATCHES"
echo " Readings per batch: $READINGS"
echo " Pause between runs: ${PAUSE_BETWEEN_RUNS}s"
echo "========================================"
echo ""

RUN_COUNT=0

while true; do
    RUN_COUNT=$((RUN_COUNT + 1))
    echo "[$(date '+%H:%M:%S')] Starting fog run #$RUN_COUNT..."

    python manage.py simulate_fog \
        --backend-url "$BACKEND_URL" \
        --token "$TOKEN" \
        --batches "$BATCHES" \
        --readings-per-batch "$READINGS" \
        --dispatch-delay "$DELAY" \
        --heart-rate-frequency 1.0 \
        --cadence-frequency 1.0 \
        --pace-frequency 0.7 \
        --gps-frequency 0.5 \
        --air-quality-frequency 0.4

    echo "[$(date '+%H:%M:%S')] Run #$RUN_COUNT complete. Pausing ${PAUSE_BETWEEN_RUNS}s before next run..."
    echo ""
    sleep "$PAUSE_BETWEEN_RUNS"
done
