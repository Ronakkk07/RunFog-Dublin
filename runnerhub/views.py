import json

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .services import build_dashboard_summary, persist_batch, publish_or_process, trigger_ingestion


def dashboard(request):
    context = build_dashboard_summary()
    context["queue_backend"] = settings.RUNNERHUB_QUEUE_BACKEND.upper()
    context["manual_trigger_mode"] = settings.RUNNERHUB_MANUAL_TRIGGER_MODE.upper()
    context["frontend_poll_seconds"] = settings.RUNNERHUB_FRONTEND_POLL_SECONDS
    return render(request, "runnerhub/dashboard.html", context)


@require_GET
def health(request):
    """
    Elastic Beanstalk health check endpoint.
    EB pings GET / by default but many setups use /health/.
    Returns 200 so the environment stays Green.
    """
    return HttpResponse("ok", content_type="text/plain")


@csrf_exempt
@require_POST
def ingest_fog_batch(request):
    """
    Public ingestion endpoint called by the fog node (Cloud9 simulator).
    Accepts a JSON batch payload and either persists inline or enqueues to SQS.

    Optional bearer-token check: set RUNNERHUB_BACKEND_INGEST_TOKEN to something
    other than the default and the fog node must pass the same token.
    """
    token = settings.RUNNERHUB_BACKEND_INGEST_TOKEN
    if token and token != "change-me":
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {token}":
            return JsonResponse({"detail": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    try:
        result = publish_or_process(payload)
    except (KeyError, ValueError, RuntimeError) as exc:
        return HttpResponseBadRequest(str(exc))

    return JsonResponse({"status": "accepted", **result})


@csrf_exempt
@require_POST
def process_queue_message(request):
    """
    Internal endpoint called by AWS Lambda after it dequeues a SQS message.
    Protected by the shared bearer token.
    """
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.RUNNERHUB_BACKEND_INGEST_TOKEN}"
    if auth_header != expected:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        persisted = persist_batch(payload)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        return HttpResponseBadRequest(str(exc))

    return JsonResponse({"status": "processed", "persisted": persisted})


@require_GET
def summary_api(request):
    return JsonResponse(build_dashboard_summary())


@require_POST
def manual_trigger(request):
    try:
        result = trigger_ingestion()
    except Exception as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse({"status": "triggered", **result})
