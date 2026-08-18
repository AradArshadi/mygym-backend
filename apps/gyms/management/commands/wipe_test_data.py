from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.gyms.models import Gym, ImportBatch
try:
    from apps.systemlogs.services import log_event
except Exception:
    log_event = None


class Command(BaseCommand):
    help = 'Danger-zone test reset. Deletes imported unclaimed gyms and optional demo accounts/data. Never deletes claimed gyms or superusers.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Required confirmation flag.')
        parser.add_argument('--source', default='', help='Optional source filter, e.g. geoapify.')
        parser.add_argument('--city', default='', help='Optional city filter.')
        parser.add_argument('--include-demo-users', action='store_true', help='Also delete known demo/import users. Never deletes superusers.')
        parser.add_argument('--delete-empty-batches', action='store_true', help='Delete ImportBatch rows with no gyms left.')

    def handle(self, *args, **options):
        if not options['yes']:
            raise CommandError('Refusing to wipe data without --yes. Example: python manage.py wipe_test_data --source geoapify --city Tabriz --yes')

        qs = Gym.objects.filter(is_imported=True, is_claimed=False)
        if options['source']:
            qs = qs.filter(source=options['source'])
        if options['city']:
            qs = qs.filter(city__iexact=options['city'])

        with transaction.atomic():
            gym_count = qs.count()
            qs.delete()
            batch_count = 0
            if options['delete_empty_batches']:
                empty_batches = ImportBatch.objects.filter(gyms__isnull=True)
                batch_count = empty_batches.count()
                empty_batches.delete()

            user_count = 0
            if options['include_demo_users']:
                User = get_user_model()
                demo_qs = User.objects.filter(username__in=['owner_demo', 'customer_demo', 'trainer_demo', 'system_import_owner'], is_superuser=False)
                user_count = demo_qs.count()
                demo_qs.delete()

        if log_event:
            log_event(category='ADMIN', event='test_data_wiped', message=f'Wiped test data: gyms={gym_count}, batches={batch_count}, users={user_count}', metadata={'gyms': gym_count, 'batches': batch_count, 'users': user_count, 'source': options['source'], 'city': options['city']})
        self.stdout.write(self.style.SUCCESS(f'Wiped test data: {gym_count} imported gyms, {batch_count} empty batches, {user_count} demo users.'))
