# Hotfix migration for existing databases upgraded from v0.9.2.8.x to v0.9.2.9.
# Reason: v0.9.2.9 added Session, GymSubscription, and GymCheckIn to 0001_initial.
# Existing MySQL databases already marked bookings.0001_initial as applied, so Django will not
# re-run it. This migration creates the missing tables safely if they are not already present.

from django.db import migrations


def create_missing_qr_tables(apps, schema_editor):
    existing_tables = set(schema_editor.connection.introspection.table_names())

    # Create independent tables first; GymCheckIn depends on both Session and GymSubscription.
    models_to_create = [
        apps.get_model('bookings', 'GymSubscription'),
        apps.get_model('bookings', 'Session'),
        apps.get_model('bookings', 'GymCheckIn'),
    ]

    for model in models_to_create:
        table_name = model._meta.db_table
        if table_name not in existing_tables:
            schema_editor.create_model(model)
            existing_tables.add(table_name)


def noop_reverse(apps, schema_editor):
    # Keep user data safe. Do not drop tables automatically on reverse.
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('bookings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_missing_qr_tables, noop_reverse),
    ]
