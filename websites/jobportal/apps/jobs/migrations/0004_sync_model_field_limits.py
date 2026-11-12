from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0003_import_source_fields_and_job_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="icon",
            field=models.CharField(
                help_text="FontAwesome icon class (e.g., 'fas fa-code')",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="job",
            name="location",
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name="job",
            name="title",
            field=models.CharField(max_length=200),
        ),
    ]
