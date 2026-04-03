import json

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .services import build_dashboard_summary, persist_batch, publish_or_process


def dashboard(request):
    context = build_dashboard_summary()
    context["queue_backend"] = settings.RUNNERHUB_QUEUE_BACKEND.upper()
    return render(request, "runnerhub/dashboard.html", context)


@csrf_exempt
@require_POST
def ingest_fog_batch(request):
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
