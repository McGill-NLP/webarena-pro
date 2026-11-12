from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0002_job_experience_level"),
    ]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("full_time", "Full Time"),
                    ("part_time", "Part Time"),
                    ("contract", "Contract"),
                    ("internship", "Internship"),
                    ("temporary", "Temporary"),
                    ("volunteer", "Volunteer"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="source",
            field=models.CharField(blank=True, db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name="job",
            name="external_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddConstraint(
            model_name="job",
            constraint=models.UniqueConstraint(
                fields=("source", "external_id"),
                name="unique_job_source_external_id",
            ),
        ),
    ]
