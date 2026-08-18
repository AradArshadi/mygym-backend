from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.fitness.models import WorkoutLog
from apps.fitness.services import fitness_summary, normalize_activity_days


class Command(BaseCommand):
    help = 'Debug workout activity counts and calendar ranges for a user.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        username = options['username']
        days = normalize_activity_days(options['days'])
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f'User not found: {username}') from exc

        summary = fitness_summary(user, activity_days=days)
        calendar = summary['activity_calendar']
        self.stdout.write(f'User: {user.username} ({user.email})')
        self.stdout.write(f'Timezone: {timezone.get_current_timezone_name()}')
        self.stdout.write(f'Today: {timezone.localdate()}')
        self.stdout.write(f'Selected range: {calendar["requested_start"]} → {calendar["today"]} ({days} days)')
        self.stdout.write(f'Grid range: {calendar["grid_start"]} → {calendar["grid_end"]} ({calendar["total_weeks"]} weeks)')
        self.stdout.write(f'Workouts in selected range: {calendar["range_workouts"]}')
        self.stdout.write(f'Active days in selected range: {calendar["range_active_days"]}')
        self.stdout.write(f'This week: {summary["week_count"]}/{summary["goal"].weekly_target} workouts, {summary["active_days"]} active days')
        self.stdout.write('')
        self.stdout.write('Recent workout logs:')
        workouts = WorkoutLog.objects.filter(user=user).order_by('-logged_at')[:20]
        if not workouts:
            self.stdout.write('  No workouts found.')
            return
        for workout in workouts:
            local_dt = timezone.localtime(workout.logged_at)
            in_range = calendar['requested_start'] <= local_dt.date() <= calendar['today']
            marker = 'IN_RANGE' if in_range else 'OUT_OF_RANGE'
            self.stdout.write(
                f'  #{workout.id} {workout.title} | {local_dt:%Y-%m-%d %H:%M} | {workout.duration_minutes} min | {marker}'
            )
