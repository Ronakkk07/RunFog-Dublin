from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SensorReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fog_node_id", models.CharField(max_length=64)),
                ("run_id", models.CharField(max_length=64)),
                ("athlete_name", models.CharField(max_length=120)),
                ("city", models.CharField(default="Dublin", max_length=120)),
                ("sensor_type", models.CharField(choices=[("heart_rate", "Heart Rate"), ("cadence", "Cadence"), ("pace", "Pace"), ("gps", "GPS"), ("air_quality", "Air Quality")], max_length=32)),
                ("reading_value", models.FloatField()),
                ("unit", models.CharField(max_length=32)),
                ("latitude", models.FloatField(blank=True, null=True)),
                ("longitude", models.FloatField(blank=True, null=True)),
                ("quality_score", models.FloatField(default=0)),
                ("risk_flag", models.BooleanField(default=False)),
                ("recorded_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-recorded_at"]},
        ),
    ]
