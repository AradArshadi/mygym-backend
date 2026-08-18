# Generated for myGym v0.9.2 logging system
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(choices=[('INFO', 'Info'), ('WARNING', 'Warning'), ('ERROR', 'Error'), ('CRITICAL', 'Critical')], default='INFO', max_length=20)),
                ('category', models.CharField(choices=[('AUTH', 'Authentication'), ('EMAIL', 'Email'), ('BOOKING', 'Booking'), ('GYM', 'Gym'), ('REVIEW', 'Review'), ('ADMIN', 'Admin'), ('SYSTEM', 'System')], default='SYSTEM', max_length=30)),
                ('event', models.CharField(max_length=120)),
                ('message', models.TextField(blank=True)),
                ('related_model', models.CharField(blank=True, max_length=80)),
                ('related_id', models.CharField(blank=True, max_length=80)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('path', models.CharField(blank=True, max_length=255)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='system_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['level', 'category'], name='systemlogs_level_c_3152b5_idx'),
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['created_at'], name='systemlogs_created_c58330_idx'),
        ),
        migrations.AddIndex(
            model_name='systemlog',
            index=models.Index(fields=['event'], name='systemlogs_event_6b2b5f_idx'),
        ),
    ]
