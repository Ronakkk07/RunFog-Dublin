import json
import os
from urllib import request


BACKEND_URL = os.environ["RUNNERHUB_PROCESS_URL"]
INGEST_TOKEN = os.environ["RUNNERHUB_BACKEND_INGEST_TOKEN"]


def lambda_handler(event, context):
    processed = []
    for record in event.get("Records", []):
        payload = json.loads(record["body"])
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
            processed.append(json.loads(response.read().decode("utf-8")))

    return {"processed_messages": len(processed), "results": processed}
