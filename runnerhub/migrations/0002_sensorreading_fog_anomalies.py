from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("runnerhub", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sensorreading",
            name="anomaly_message",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="sensorreading",
            name="anomaly_severity",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="sensorreading",
            name="anomaly_type",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="sensorreading",
            name="processing_stage",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
