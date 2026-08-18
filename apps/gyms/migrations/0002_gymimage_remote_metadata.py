from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('gyms', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gymimage',
            name='remote_id',
            field=models.CharField(blank=True, help_text='Remote image identifier returned by the hosting provider.', max_length=80),
        ),
        migrations.AddField(
            model_name='gymimage',
            name='remote_delete_url',
            field=models.URLField(blank=True, help_text='Provider cleanup URL. Keep private; do not expose via public API.'),
        ),
        migrations.AddField(
            model_name='gymimage',
            name='remote_width',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='gymimage',
            name='remote_height',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='gymimage',
            name='remote_size',
            field=models.PositiveIntegerField(blank=True, help_text='Remote image size in bytes.', null=True),
        ),
    ]
