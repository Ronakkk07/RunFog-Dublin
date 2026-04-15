"""
AWS Lambda consumer for RunFog Dublin.

Trigger: SQS queue (runfog-batches)
Role needs: sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes

Environment variables required:
  RUNNERHUB_PROCESS_URL   - https://<eb-domain>/api/internal/process/
  RUNNERHUB_BACKEND_INGEST_TOKEN - shared secret (must match backend)
"""

import json
import logging
import os
from urllib import request, error

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BACKEND_URL = os.environ["RUNNERHUB_PROCESS_URL"]
INGEST_TOKEN = os.environ["RUNNERHUB_BACKEND_INGEST_TOKEN"]


def lambda_handler(event, context):
    processed = []
    failed = []

    for record in event.get("Records", []):
        try:
            payload = json.loads(record["body"])
            batch_id = payload.get("batch_id", "unknown")
            logger.info("Processing batch: %s", batch_id)

            req = request.Request(
                BACKEND_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {INGEST_TOKEN}",
                },
                method="POST",
            )
            with request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
                logger.info("Batch %s persisted: %s readings", batch_id, result.get("persisted"))
                processed.append({"batch_id": batch_id, **result})

        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            logger.error("HTTP %s for batch %s: %s", exc.code, record.get("messageId"), body)
            failed.append({"messageId": record.get("messageId"), "error": str(exc)})
            # Re-raise so Lambda marks this message for retry / DLQ
            raise

        except Exception as exc:
            logger.error("Unexpected error processing record %s: %s", record.get("messageId"), exc)
            failed.append({"messageId": record.get("messageId"), "error": str(exc)})
            raise

    return {
        "processed_messages": len(processed),
        "failed_messages": len(failed),
        "results": processed,
    }