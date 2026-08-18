# Generated for myGym v0.9.3 Fitness Home Rebase

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkoutGoal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekly_target', models.PositiveIntegerField(default=3)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='workout_goal', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['user__username'],
            },
        ),
        migrations.CreateModel(
            name='WorkoutLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Workout', max_length=120)),
                ('workout_type', models.CharField(blank=True, help_text='Strength, Cardio, Yoga, Boxing, etc.', max_length=80)),
                ('notes', models.TextField(blank=True)),
                ('duration_minutes', models.PositiveIntegerField(default=0)),
                ('logged_at', models.DateTimeField(db_index=True, default=timezone.now)),
                ('source', models.CharField(choices=[('MANUAL', 'Manual'), ('SESSION', 'Gym session'), ('IMPORTED', 'Imported')], default='MANUAL', max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='workout_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-logged_at', '-created_at'],
                'indexes': [models.Index(fields=['user', 'logged_at'], name='fitness_wor_user_id_b03dfb_idx'), models.Index(fields=['source'], name='fitness_wor_source_7fcdf3_idx')],
            },
        ),
    ]
