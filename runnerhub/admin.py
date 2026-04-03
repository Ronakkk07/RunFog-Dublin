from django.contrib import admin

from .models import SensorReading


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = (
        "run_id",
        "athlete_name",
        "sensor_type",
        "reading_value",
        "unit",
        "city",
        "recorded_at",
        "risk_flag",
    )
    list_filter = ("sensor_type", "city", "risk_flag")
    search_fields = ("run_id", "athlete_name", "fog_node_id")
