from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from apps.gyms.models import Gym, ImportBatch
try:
    from apps.systemlogs.services import log_event
except Exception:
    log_event = None


class Command(BaseCommand):
    help = 'Safely wipe all unclaimed imported gyms from one import batch.'

    def add_arguments(self, parser):
        parser.add_argument('batch_id', type=int)
        parser.add_argument('--force', action='store_true', help='Also delete imported gyms that have bookings/reviews/favorites. Still never deletes claimed gyms.')
        parser.add_argument('--delete-batch', action='store_true', help='Delete the ImportBatch row after wiping gyms.')

    def handle(self, *args, **options):
        batch_id = options['batch_id']
        force = options['force']
        delete_batch = options['delete_batch']
        try:
            batch = ImportBatch.objects.get(id=batch_id)
        except ImportBatch.DoesNotExist:
            raise CommandError(f'ImportBatch #{batch_id} does not exist.')

        qs = Gym.objects.filter(import_batch=batch, is_imported=True, is_claimed=False)
        qs = qs.annotate(booking_count=Count('bookings', distinct=True), review_count=Count('reviews', distinct=True), favorite_count=Count('favorited_by', distinct=True))
        protected = qs.filter(booking_count__gt=0) | qs.filter(review_count__gt=0) | qs.filter(favorite_count__gt=0)
        if protected.exists() and not force:
            self.stdout.write(self.style.WARNING(f'{protected.count()} gyms have bookings/reviews/favorites and were protected. Use --force to delete them.'))
            qs = qs.filter(booking_count=0, review_count=0, favorite_count=0)

        count = qs.count()
        qs.delete()
        if delete_batch and not batch.gyms.exists():
            batch.delete()
        if log_event:
            log_event(category='GYM', event='import_batch_wiped', message=f'Wiped {count} gyms from batch {batch_id}', related_model='ImportBatch', related_id=batch_id, metadata={'deleted': count, 'force': force})
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} imported unclaimed gyms from batch #{batch_id}.'))
