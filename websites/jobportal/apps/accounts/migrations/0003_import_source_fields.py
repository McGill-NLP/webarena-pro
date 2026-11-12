from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_add_employer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="employer",
            name="source",
            field=models.CharField(blank=True, db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name="employer",
            name="external_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="jobseeker",
            name="source",
            field=models.CharField(blank=True, db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name="jobseeker",
            name="external_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="jobseeker",
            name="source_category",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddConstraint(
            model_name="employer",
            constraint=models.UniqueConstraint(
                fields=("source", "external_id"),
                name="unique_employer_source_external_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="jobseeker",
            constraint=models.UniqueConstraint(
                fields=("source", "external_id"),
                name="unique_jobseeker_source_external_id",
            ),
        ),
    ]
