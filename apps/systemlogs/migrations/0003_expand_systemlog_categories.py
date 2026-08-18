# Generated manually for v0.9.2.10 infrastructure hardening.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('systemlogs', '0002_rename_systemlogs_level_c_3152b5_idx_systemlogs__level_4aa8e2_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='systemlog',
            name='category',
            field=models.CharField(
                choices=[
                    ('AUTH', 'Authentication'),
                    ('EMAIL', 'Email'),
                    ('BOOKING', 'Booking'),
                    ('GYM', 'Gym'),
                    ('REVIEW', 'Review'),
                    ('ADMIN', 'Admin'),
                    ('NOTIFICATION', 'Notification'),
                    ('SESSION', 'Session'),
                    ('SUBSCRIPTION', 'Subscription'),
                    ('CHECKIN', 'Check-in'),
                    ('SYSTEM', 'System'),
                ],
                default='SYSTEM',
                max_length=30,
            ),
        ),
    ]
