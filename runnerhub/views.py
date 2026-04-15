import csv
import json

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .services import (
    build_dashboard_summary,
    build_export_rows,
    build_run_detail,
    persist_batch,
    publish_or_process,
    trigger_ingestion,
)


def dashboard(request):
    context = build_dashboard_summary(read_request_filters(request))
    context["queue_backend"] = settings.RUNNERHUB_QUEUE_BACKEND.upper()
    context["manual_trigger_mode"] = settings.RUNNERHUB_MANUAL_TRIGGER_MODE.upper()
    context["frontend_poll_seconds"] = settings.RUNNERHUB_FRONTEND_POLL_SECONDS
    return render(request, "runnerhub/dashboard.html", context)


@require_GET
def run_detail_page(request, run_id):
    detail = build_run_detail(run_id)
    if not detail:
        return HttpResponseBadRequest("Unknown run_id")

    return render(
        request,
        "runnerhub/run_detail.html",
        {
            "detail": detail,
            "queue_backend": settings.RUNNERHUB_QUEUE_BACKEND.upper(),
        },
    )


@require_GET
def health(request):
    return HttpResponse("ok", content_type="text/plain")


@csrf_exempt
@require_POST
def ingest_fog_batch(request):
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
    return JsonResponse(build_dashboard_summary(read_request_filters(request)))


@require_GET
def run_detail_api(request, run_id):
    detail = build_run_detail(run_id)
    if not detail:
        return JsonResponse({"detail": "Unknown run_id"}, status=404)
    return JsonResponse(detail)


@require_GET
def export_readings(request):
    filters = read_request_filters(request)
    rows = build_export_rows(filters)
    export_format = (request.GET.get("format") or "json").lower()

    if export_format == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="runfog-readings.csv"'
        writer = csv.DictWriter(
            response,
            fieldnames=[
                "run_id",
                "athlete_name",
                "city",
                "fog_node_id",
                "sensor_type",
                "sensor_label",
                "reading_value",
                "unit",
                "latitude",
                "longitude",
                "quality_score",
                "risk_flag",
                "risk_explanation",
                "recorded_at",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
        return response

    return JsonResponse({"count": len(rows), "readings": rows})


@require_POST
def manual_trigger(request):
    try:
        result = trigger_ingestion()
    except Exception as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse({"status": "triggered", **result})


def read_request_filters(request):
    return {
        "athlete_name": request.GET.get("athlete_name", ""),
        "run_id": request.GET.get("run_id", ""),
        "sensor_type": request.GET.get("sensor_type", ""),
        "time_range": request.GET.get("time_range", "all"),
    }
