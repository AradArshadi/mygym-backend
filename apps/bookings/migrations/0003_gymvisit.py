from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('bookings', '0002_create_sessions_access_pass_tables'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GymVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('COMPLETED', 'Completed'), ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled')], db_index=True, default='ACTIVE', max_length=20)),
                ('entry_method', models.CharField(choices=[('SESSION_QR', 'Session QR'), ('MEMBERSHIP_QR', 'Membership QR'), ('MANUAL', 'Manual')], max_length=24)),
                ('checked_in_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('checked_out_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('checked_in_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gym_visits_started', to=settings.AUTH_USER_MODEL)),
                ('checked_out_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gym_visits_finished', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gym_visits', to=settings.AUTH_USER_MODEL)),
                ('gym', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visits', to='gyms.gym')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='visits', to='bookings.session')),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='visits', to='bookings.gymsubscription')),
            ],
            options={'ordering': ['-checked_in_at']},
        ),
        migrations.AddConstraint(
            model_name='gymvisit',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'ACTIVE')), fields=('customer',), name='one_active_gym_visit_per_customer'),
        ),
        migrations.AddIndex(
            model_name='gymvisit',
            index=models.Index(fields=['gym', 'status', '-checked_in_at'], name='bookings_gy_gym_id_8384b0_idx'),
        ),
    ]
