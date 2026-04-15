from django.db import models


class SensorReading(models.Model):
    SENSOR_TYPES = [
        ("heart_rate", "Heart Rate"),
        ("cadence", "Cadence"),
        ("pace", "Pace"),
        ("gps", "GPS"),
        ("air_quality", "Air Quality"),
    ]

    fog_node_id = models.CharField(max_length=64)
    run_id = models.CharField(max_length=64)
    athlete_name = models.CharField(max_length=120)
    city = models.CharField(max_length=120, default="Dublin")
    sensor_type = models.CharField(max_length=32, choices=SENSOR_TYPES)
    reading_value = models.FloatField()
    unit = models.CharField(max_length=32)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    quality_score = models.FloatField(default=0)
    risk_flag = models.BooleanField(default=False)
    anomaly_type = models.CharField(max_length=64, blank=True, default="")
    anomaly_severity = models.CharField(max_length=32, blank=True, default="")
    anomaly_message = models.CharField(max_length=255, blank=True, default="")
    processing_stage = models.CharField(max_length=32, blank=True, default="")
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.run_id}:{self.sensor_type}:{self.reading_value}"
