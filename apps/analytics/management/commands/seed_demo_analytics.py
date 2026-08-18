from django.core.management.base import BaseCommand

from apps.analytics.demo_seed import TRAFFIC_PROFILES, seed_realistic_demo_data


class Command(BaseCommand):
    help = 'Seed realistic demo customers, memberships, bookings, arrivals, favorites, and workouts.'

    def add_arguments(self, parser):
        parser.add_argument('--owner', default='', help='Limit generated data to one owner username.')
        parser.add_argument('--customers', type=int, default=25)
        parser.add_argument('--days', type=int, default=120)
        parser.add_argument('--subscriptions-per-gym', type=int, default=24)
        parser.add_argument('--bookings-per-gym', type=int, default=45)
        parser.add_argument('--checkins-per-gym', type=int, default=220)
        parser.add_argument('--favorites-per-gym', type=int, default=12)
        parser.add_argument('--workouts-per-customer', type=int, default=18)
        parser.add_argument('--password', default='DemoPass123')
        parser.add_argument('--traffic-profile', choices=TRAFFIC_PROFILES, default='balanced')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--reset-demo', action='store_true')
        parser.add_argument('--seed', type=int, default=9309)

    def handle(self, *args, **options):
        result = seed_realistic_demo_data(
            owner_username=options['owner'],
            customers=options['customers'],
            days=options['days'],
            subscriptions_per_gym=options['subscriptions_per_gym'],
            bookings_per_gym=options['bookings_per_gym'],
            checkins_per_gym=options['checkins_per_gym'],
            favorites_per_gym=options['favorites_per_gym'],
            workouts_per_customer=options['workouts_per_customer'],
            password=options['password'],
            reset_demo=options['reset_demo'],
            dry_run=options['dry_run'],
            seed=options['seed'],
            traffic_profile=options['traffic_profile'],
        )
        self.stdout.write(self.style.SUCCESS('Realistic demo analytics seed complete.'))
        for key, value in result.to_dict().items():
            self.stdout.write(f'{key}: {value}')
