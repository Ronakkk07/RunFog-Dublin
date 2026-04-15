from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("runs/<str:run_id>/", views.run_detail_page, name="run-detail"),
    path("health/", views.health, name="health"),
    path("api/ingest/", views.ingest_fog_batch, name="ingest-fog-batch"),
    path("api/internal/process/", views.process_queue_message, name="process-queue-message"),
    path("api/summary/", views.summary_api, name="summary-api"),
    path("api/export/", views.export_readings, name="export-readings"),
    path("api/runs/<str:run_id>/", views.run_detail_api, name="run-detail-api"),
    path("api/manual-trigger/", views.manual_trigger, name="manual-trigger"),
]
