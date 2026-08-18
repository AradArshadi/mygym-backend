from django.core.management.base import BaseCommand
from django.db.models import Count
from apps.gyms.models import Gym
try:
    from apps.systemlogs.services import log_event
except Exception:
    log_event = None


class Command(BaseCommand):
    help = 'Safely wipe imported, unclaimed gyms by city/source. Does not touch owner-created gyms.'

    def add_arguments(self, parser):
        parser.add_argument('--city', required=True)
        parser.add_argument('--source', default='openstreetmap')
        parser.add_argument('--force', action='store_true', help='Also delete imported gyms that have bookings/reviews/favorites. Still never deletes claimed gyms.')

    def handle(self, *args, **options):
        city = options['city']
        source = options['source']
        force = options['force']
        qs = Gym.objects.filter(city__iexact=city, source=source, is_imported=True, is_claimed=False)
        qs = qs.annotate(booking_count=Count('bookings', distinct=True), review_count=Count('reviews', distinct=True), favorite_count=Count('favorited_by', distinct=True))
        protected = qs.filter(booking_count__gt=0) | qs.filter(review_count__gt=0) | qs.filter(favorite_count__gt=0)
        if protected.exists() and not force:
            self.stdout.write(self.style.WARNING(f'{protected.count()} gyms have bookings/reviews/favorites and were protected. Use --force to delete them.'))
            qs = qs.filter(booking_count=0, review_count=0, favorite_count=0)
        count = qs.count()
        qs.delete()
        if log_event:
            log_event(category='GYM', event='imported_city_wiped', message=f'Wiped {count} imported gyms from {city}', metadata={'city': city, 'source': source, 'deleted': count, 'force': force})
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} imported unclaimed gyms from {city}.'))
