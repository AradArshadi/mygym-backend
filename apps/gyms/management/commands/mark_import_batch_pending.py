from django.core.management.base import BaseCommand, CommandError
from apps.gyms.models import Gym, ImportBatch
try:
    from apps.systemlogs.services import log_event
except Exception:
    log_event = None


class Command(BaseCommand):
    help = 'Emergency rollback: mark imported, unclaimed gyms from one batch as PENDING again.'

    def add_arguments(self, parser):
        parser.add_argument('batch_id', type=int)

    def handle(self, *args, **options):
        batch_id = options['batch_id']
        try:
            batch = ImportBatch.objects.get(id=batch_id)
        except ImportBatch.DoesNotExist:
            raise CommandError(f'ImportBatch #{batch_id} does not exist.')

        qs = Gym.objects.filter(import_batch=batch, is_imported=True, is_claimed=False)
        count = qs.update(status=Gym.Status.PENDING)
        if log_event:
            log_event(category='GYM', event='import_batch_marked_pending', message=f'Marked {count} gyms pending from batch {batch_id}', related_model='ImportBatch', related_id=batch_id, metadata={'count': count})
        self.stdout.write(self.style.SUCCESS(f'Marked {count} imported gyms from batch #{batch_id} as PENDING.'))
