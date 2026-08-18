import random
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, GymCheckIn, GymSubscription
from apps.gyms.models import Gym, MembershipPlan
from apps.reviews.models import Favorite

try:
    from apps.fitness.models import WorkoutLog
except Exception:  # pragma: no cover
    WorkoutLog = None


DEMO_USERNAME_PREFIX = 'demo_customer_analytics_'
DEMO_BOOKING_NOTE = 'Demo analytics booking'
DEMO_CHECKIN_NOTE = 'Demo QR check-in for traffic analytics'
DEMO_WORKOUT_NOTE = 'Demo workout log for activity map testing.'
DEMO_WORKOUT_SOURCE = 'IMPORTED'
TRAFFIC_PROFILES = ('balanced', 'evening-heavy', 'morning-heavy', 'student')


@dataclass
class DemoSeedResult:
    gyms: int = 0
    customers: int = 0
    subscriptions: int = 0
    bookings: int = 0
    checkins: int = 0
    favorites: int = 0
    workouts: int = 0
    reset_deleted: int = 0
    traffic_profile: str = 'balanced'
    days: int = 120
    dry_run: bool = False
    hour_distribution: dict | None = None
    weekday_distribution: dict | None = None

    def to_dict(self):
        return asdict(self)


class RealisticDemoSeeder:
    """Create repeatable, believable demo analytics without touching real data.

    The important implementation detail is that auto_now_add fields are updated
    after insert. Passing a historic value to ``objects.create`` does not override
    auto_now_add, which previously caused all memberships/check-ins to appear as if
    they happened at the same current timestamp.
    """

    def __init__(
        self,
        *,
        owner_username='',
        customers=25,
        days=120,
        subscriptions_per_gym=24,
        bookings_per_gym=45,
        checkins_per_gym=220,
        favorites_per_gym=12,
        workouts_per_customer=18,
        password='DemoPass123',
        reset_demo=False,
        dry_run=False,
        seed=9309,
        traffic_profile='balanced',
    ):
        if traffic_profile not in TRAFFIC_PROFILES:
            raise ValueError(f'Unknown traffic profile: {traffic_profile}')
        self.owner_username = owner_username
        self.customer_count = max(1, int(customers))
        self.days = max(1, int(days))
        self.subscriptions_per_gym = max(0, int(subscriptions_per_gym))
        self.bookings_per_gym = max(0, int(bookings_per_gym))
        self.checkins_per_gym = max(0, int(checkins_per_gym))
        self.favorites_per_gym = max(0, int(favorites_per_gym))
        self.workouts_per_customer = max(0, int(workouts_per_customer))
        self.password = password
        self.reset_demo = bool(reset_demo)
        self.dry_run = bool(dry_run)
        self.seed = int(seed)
        self.traffic_profile = traffic_profile
        self.rng = random.Random(self.seed)
        self.now = timezone.now()
        self.today = timezone.localdate()
        self.hour_counts = Counter()
        self.weekday_counts = Counter()

    def run(self):
        gyms = self._target_gyms()
        result = DemoSeedResult(
            gyms=len(gyms),
            customers=self.customer_count,
            traffic_profile=self.traffic_profile,
            days=self.days,
            dry_run=self.dry_run,
        )
        if self.dry_run:
            result.subscriptions = len(gyms) * self.subscriptions_per_gym
            result.bookings = len(gyms) * (self.bookings_per_gym + self.subscriptions_per_gym)
            result.checkins = len(gyms) * self.checkins_per_gym
            result.favorites = len(gyms) * min(self.favorites_per_gym, self.customer_count)
            result.workouts = min(15, self.customer_count) * self.workouts_per_customer
            return result

        with transaction.atomic():
            if self.reset_demo:
                result.reset_deleted = reset_realistic_demo_data()
            customers = self._ensure_customers()
            result.customers = len(customers)
            for gym in gyms:
                plan = self._plan(gym)
                subscriptions = self._create_subscriptions(gym, customers, plan)
                result.subscriptions += len(subscriptions)
                result.bookings += len(subscriptions)  # each subscription has a source booking
                result.bookings += self._create_extra_bookings(gym, customers, plan)
                result.checkins += self._create_checkins(gym, subscriptions)
                result.favorites += self._create_favorites(gym, customers)
            result.workouts = self._create_workouts(customers)

        result.hour_distribution = {f'{hour:02d}:00': self.hour_counts[hour] for hour in sorted(self.hour_counts)}
        labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        result.weekday_distribution = {labels[index]: self.weekday_counts[index] for index in range(7)}
        return result

    def _target_gyms(self):
        qs = Gym.objects.filter(owner__isnull=False).select_related('owner')
        if self.owner_username:
            qs = qs.filter(owner__username=self.owner_username)
        gyms = list(qs)
        if not gyms:
            raise CommandError('No owner gyms found. Create/seed gyms first or check the owner username.')
        return gyms

    def _ensure_customers(self):
        User = get_user_model()
        customers = []
        for index in range(1, self.customer_count + 1):
            joined_dt = self._random_datetime(kind='signup')
            user, created = User.objects.get_or_create(
                username=f'{DEMO_USERNAME_PREFIX}{index}',
                defaults={
                    'email': f'demo.customer.analytics.{index}@example.com',
                    'role': getattr(User.Role, 'CUSTOMER', 'CUSTOMER'),
                    'is_active': True,
                },
            )
            if created:
                user.set_password(self.password)
                user.save()
            if hasattr(user, 'date_joined'):
                User.objects.filter(pk=user.pk).update(date_joined=joined_dt)
                user.date_joined = joined_dt
            customers.append(user)
        return customers

    def _plan(self, gym):
        plans = list(MembershipPlan.objects.filter(gym=gym).order_by('price'))
        if plans:
            return self.rng.choice(plans)
        return MembershipPlan.objects.create(
            gym=gym,
            title='Demo Monthly Access',
            description='Demo monthly membership plan for analytics testing.',
            price=Decimal('49.00'),
            duration_days=30,
            is_trial=False,
        )

    def _weighted_hour(self, weekday):
        if weekday >= 5:
            hours = [8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20]
            weights = [2, 4, 8, 10, 8, 4, 4, 6, 7, 6, 4, 2]
        elif self.traffic_profile == 'evening-heavy':
            hours = [6, 7, 8, 12, 13, 16, 17, 18, 19, 20, 21]
            weights = [1, 2, 2, 1, 1, 4, 10, 18, 20, 15, 7]
        elif self.traffic_profile == 'morning-heavy':
            hours = [5, 6, 7, 8, 9, 12, 13, 17, 18, 19, 20]
            weights = [2, 9, 17, 16, 9, 2, 1, 5, 6, 4, 2]
        elif self.traffic_profile == 'student':
            hours = [8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]
            weights = [1, 1, 2, 2, 4, 6, 8, 9, 11, 13, 12, 9, 5, 2]
        else:
            hours = [6, 7, 8, 9, 12, 13, 16, 17, 18, 19, 20, 21]
            weights = [2, 4, 5, 3, 2, 2, 4, 8, 13, 14, 9, 4]
        return self.rng.choices(hours, weights=weights, k=1)[0]

    def _random_datetime(self, *, kind='traffic', earliest=None, latest=None):
        latest = latest or self.now
        earliest = earliest or (self.now - timedelta(days=self.days - 1))
        if latest < earliest:
            latest = earliest
        span_days = max(0, (timezone.localtime(latest).date() - timezone.localtime(earliest).date()).days)

        # Growth is gradual with a modest recent bias, not a single-day spike.
        if kind == 'signup':
            offset = int(self.rng.triangular(0, span_days or 1, min(span_days or 1, max(1, span_days * 0.35))))
        else:
            offset = self.rng.randint(0, span_days) if span_days else 0

        day = timezone.localtime(earliest).date() + timedelta(days=offset)
        hour = self._weighted_hour(day.weekday()) if kind == 'traffic' else self.rng.randint(8, 20)
        minute = self.rng.choice(range(0, 60, 5))
        candidate = timezone.make_aware(datetime.combine(day, time(hour, minute, self.rng.randint(0, 59))), timezone.get_current_timezone())
        if candidate > latest:
            candidate = latest - timedelta(minutes=self.rng.randint(1, 90))
        if candidate < earliest:
            candidate = earliest
        return candidate

    def _create_booking(self, gym, customer, plan, status, dt):
        for seconds in range(12):
            candidate = dt + timedelta(seconds=seconds)
            booking, created = Booking.objects.get_or_create(
                customer=customer,
                gym=gym,
                booking_datetime=candidate,
                defaults={
                    'plan': plan,
                    'status': status,
                    'payment_status': 'PAID' if status == Booking.Status.CONFIRMED else 'NOT_REQUIRED',
                    'customer_note': DEMO_BOOKING_NOTE,
                },
            )
            if created:
                Booking.objects.filter(pk=booking.pk).update(created_at=dt)
                booking.created_at = dt
                return booking, True
        return booking, False

    def _create_subscriptions(self, gym, customers, plan):
        subscriptions = []
        duration = max(7, int(getattr(plan, 'duration_days', 30) or 30))
        for _ in range(self.subscriptions_per_gym):
            customer = self.rng.choice(customers)
            started_at = self._random_datetime(kind='signup')
            booking, created = self._create_booking(gym, customer, plan, Booking.Status.CONFIRMED, started_at)
            if not created and hasattr(booking, 'subscription'):
                try:
                    subscriptions.append(booking.subscription)
                except GymSubscription.DoesNotExist:
                    pass
                continue

            cycles = self.rng.choices([1, 2, 3, 4, 6], weights=[36, 27, 18, 11, 8], k=1)[0]
            end_date = started_at.date() + timedelta(days=duration * cycles)
            if end_date >= self.today:
                status = GymSubscription.Status.ACTIVE
            else:
                status = self.rng.choices(
                    [GymSubscription.Status.EXPIRED, GymSubscription.Status.CANCELLED],
                    weights=[90, 10], k=1,
                )[0]
            subscription, created_sub = GymSubscription.objects.get_or_create(
                source_booking=booking,
                defaults={
                    'customer': customer,
                    'gym': gym,
                    'plan': plan,
                    'status': status,
                    'start_date': started_at.date(),
                    'end_date': end_date,
                    'qr_generated_at': min(self.now, started_at + timedelta(hours=2)),
                },
            )
            if created_sub:
                GymSubscription.objects.filter(pk=subscription.pk).update(
                    created_at=started_at,
                    updated_at=started_at,
                )
                subscription.created_at = started_at
            subscriptions.append(subscription)
        return subscriptions

    def _create_extra_bookings(self, gym, customers, plan):
        statuses = [
            Booking.Status.CONFIRMED,
            Booking.Status.CONFIRMED,
            Booking.Status.CONFIRMED,
            Booking.Status.PENDING,
            Booking.Status.REJECTED,
            Booking.Status.CANCELLED,
        ]
        created = 0
        for _ in range(self.bookings_per_gym):
            requested_at = self._random_datetime(kind='signup')
            # Booking visit can be same day or up to a week later.
            visit_at = min(self.now + timedelta(days=10), requested_at + timedelta(days=self.rng.randint(0, 7), hours=self.rng.randint(0, 8)))
            _, was_created = self._create_booking(gym, self.rng.choice(customers), plan, self.rng.choice(statuses), visit_at)
            created += int(was_created)
        return created

    def _create_checkins(self, gym, subscriptions):
        if not subscriptions:
            return 0
        created = 0
        eligible = [sub for sub in subscriptions if sub.start_date <= self.today]
        for _ in range(self.checkins_per_gym):
            sub = self.rng.choice(eligible)
            earliest = timezone.make_aware(datetime.combine(sub.start_date, time.min), timezone.get_current_timezone())
            latest_date = min(sub.end_date, self.today)
            latest = timezone.make_aware(datetime.combine(latest_date, time(22, 30)), timezone.get_current_timezone())
            dt = self._random_datetime(kind='traffic', earliest=earliest, latest=min(latest, self.now))
            checkin = GymCheckIn.objects.create(
                customer=sub.customer,
                gym=gym,
                subscription=sub,
                checkin_type=GymCheckIn.CheckInType.MEMBERSHIP,
                notes=DEMO_CHECKIN_NOTE,
            )
            # checked_in_at is auto_now_add, so update after insert.
            GymCheckIn.objects.filter(pk=checkin.pk).update(checked_in_at=dt)
            self.hour_counts[timezone.localtime(dt).hour] += 1
            self.weekday_counts[timezone.localtime(dt).weekday()] += 1
            created += 1
        return created

    def _create_favorites(self, gym, customers):
        created = 0
        for customer in self.rng.sample(customers, min(self.favorites_per_gym, len(customers))):
            _, was_created = Favorite.objects.get_or_create(user=customer, gym=gym)
            created += int(was_created)
        return created

    def _create_workouts(self, customers):
        if WorkoutLog is None:
            return 0
        created = 0
        titles = ['Gym Session', 'Strength Workout', 'Cardio Day', 'Push Day', 'Pull Day', 'Leg Day']
        workout_types = ['Strength', 'Upper Body', 'Lower Body', 'Cardio', 'Hypertrophy', 'Recovery']
        for customer in customers[:15]:
            for _ in range(self.workouts_per_customer):
                dt = self._random_datetime(kind='traffic')
                WorkoutLog.objects.create(
                    user=customer,
                    title=self.rng.choice(titles),
                    workout_type=self.rng.choice(workout_types),
                    duration_minutes=self.rng.choice([35, 45, 50, 60, 75, 90]),
                    notes=DEMO_WORKOUT_NOTE,
                    logged_at=dt,
                    source=DEMO_WORKOUT_SOURCE,
                )
                created += 1
        return created


def reset_realistic_demo_data():
    """Delete only records owned by the analytics demo namespace."""
    demo_users = get_user_model().objects.filter(username__startswith=DEMO_USERNAME_PREFIX)
    demo_user_ids = list(demo_users.values_list('id', flat=True))
    deleted = 0
    deleted += GymCheckIn.objects.filter(notes=DEMO_CHECKIN_NOTE).delete()[0]
    if WorkoutLog is not None:
        deleted += WorkoutLog.objects.filter(user_id__in=demo_user_ids, notes=DEMO_WORKOUT_NOTE).delete()[0]
    deleted += Favorite.objects.filter(user_id__in=demo_user_ids).delete()[0]
    deleted += GymSubscription.objects.filter(customer_id__in=demo_user_ids).delete()[0]
    deleted += Booking.objects.filter(customer_id__in=demo_user_ids, customer_note=DEMO_BOOKING_NOTE).delete()[0]
    return deleted


def seed_realistic_demo_data(**options):
    return RealisticDemoSeeder(**options).run()
