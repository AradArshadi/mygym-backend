from collections import Counter
from datetime import datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import WorkoutGoal, WorkoutLog

ACTIVITY_RANGE_OPTIONS = (30, 90, 120, 360)
WEEKDAY_LABELS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def week_start_for(date_value=None):
    """Return Monday for the week containing date_value in the current timezone."""
    date_value = date_value or timezone.localdate()
    return date_value - timedelta(days=date_value.weekday())


def normalize_activity_days(value, default=30):
    """Return a safe activity calendar range."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value in ACTIVITY_RANGE_OPTIONS else default


def _aware_day_start(date_value):
    return timezone.make_aware(datetime.combine(date_value, time.min), timezone.get_current_timezone())


def get_or_create_goal(user):
    goal, _ = WorkoutGoal.objects.get_or_create(user=user, defaults={'weekly_target': 3})
    return goal


def workouts_for_week(user, start_date=None):
    start_date = start_date or week_start_for()
    end_date = start_date + timedelta(days=7)
    return WorkoutLog.objects.filter(
        user=user,
        logged_at__gte=_aware_day_start(start_date),
        logged_at__lt=_aware_day_start(end_date),
    )


def weekly_workout_count(user, start_date=None):
    return workouts_for_week(user, start_date=start_date).count()


def weekly_active_days(user, start_date=None):
    days = set()
    for workout in workouts_for_week(user, start_date=start_date).only('logged_at'):
        days.add(timezone.localtime(workout.logged_at).date())
    return len(days)


def current_weekly_streak(user, target=None, reference_date=None, max_weeks=52):
    """Count consecutive weeks where the user met their weekly target.

    The current week counts only if the target is already met. If the current
    week is not finished and not yet complete, we still check previous completed
    weeks so a good streak is not visually broken on Monday morning.
    """
    target = target or get_or_create_goal(user).weekly_target
    current_start = week_start_for(reference_date)
    streak = 0

    for offset in range(max_weeks):
        week_start = current_start - timedelta(days=7 * offset)
        count = weekly_workout_count(user, week_start)
        if count >= target:
            streak += 1
        else:
            if offset == 0:
                continue
            break
    return streak


def _activity_intensity(count):
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count == 2:
        return 2
    if count == 3:
        return 3
    return 4


def _build_month_labels(grid_start, total_weeks):
    """Return non-overlapping month labels for a GitHub-style calendar.

    A 30-day range often starts in the final few days of a month, e.g.
    May 29 -> Jun 27. If we render both ``May`` and ``Jun`` on adjacent
    week columns, the labels collide on mobile. This helper intentionally
    skips tiny leading partial-month labels and keeps at least four week
    columns between labels, which matches the visual behavior users expect
    from contribution maps.
    """
    candidates = []
    last_label = None
    for column in range(total_weeks):
        week_date = grid_start + timedelta(days=column * 7)
        label = week_date.strftime('%b')
        if label != last_label:
            candidates.append({
                'label': label,
                'column': column + 1,
            })
            last_label = label

    # If the visible range begins with a tiny partial month and immediately
    # enters the next month, omit the first label to avoid ``MayJun`` overlap.
    if len(candidates) > 1 and candidates[0]['column'] == 1 and candidates[1]['column'] <= 2:
        candidates = candidates[1:]

    labels = []
    last_column = -99
    minimum_gap = 4
    for item in candidates:
        if item['column'] - last_column >= minimum_gap:
            labels.append(item)
            last_column = item['column']
    return labels


def training_activity_calendar(user, days=30):
    """Build a GitHub-style contribution calendar.

    Layout rules:
    - selected range is 30/90/120/360 days ending today
    - data is counted from the selected range only
    - visual grid is aligned to Monday/Sunday weeks like GitHub
    - cells flow top-to-bottom inside each week, then left-to-right
    - empty leading/future cells are rendered muted, not counted
    """
    days = normalize_activity_days(days)
    today = timezone.localdate()
    requested_start = today - timedelta(days=days - 1)
    grid_start = week_start_for(requested_start)
    grid_end = today + timedelta(days=6 - today.weekday())
    total_days = (grid_end - grid_start).days + 1
    total_weeks = max(1, total_days // 7)

    start_dt = _aware_day_start(requested_start)
    end_dt = _aware_day_start(today + timedelta(days=1))
    counts = Counter()
    qs = WorkoutLog.objects.filter(user=user, logged_at__gte=start_dt, logged_at__lt=end_dt).only('logged_at')
    for workout in qs:
        local_day = timezone.localtime(workout.logged_at).date()
        if requested_start <= local_day <= today:
            counts[local_day] += 1

    cells = []
    for index in range(total_days):
        day = grid_start + timedelta(days=index)
        is_in_range = requested_start <= day <= today
        is_future = day > today
        count = counts.get(day, 0) if is_in_range else 0
        cells.append({
            'date': day,
            'count': count,
            'intensity': _activity_intensity(count),
            'is_today': day == today,
            'is_in_range': is_in_range,
            'is_future': is_future,
            'is_muted': not is_in_range or is_future,
            'weekday': WEEKDAY_LABELS[day.weekday()],
        })

    return {
        'days': days,
        'today': today,
        'requested_start': requested_start,
        'grid_start': grid_start,
        'grid_end': grid_end,
        'total_weeks': total_weeks,
        'cells': cells,
        'month_labels': _build_month_labels(grid_start, total_weeks),
        'range_workouts': sum(counts.values()),
        'range_active_days': sum(1 for count in counts.values() if count > 0),
        'weekday_labels': WEEKDAY_LABELS,
    }


def training_activity_grid(user, days=30):
    """Backward-compatible alias used by older templates/tests."""
    return training_activity_calendar(user, days)['cells']


def fitness_summary(user, activity_days=30):
    activity_days = normalize_activity_days(activity_days)
    goal = get_or_create_goal(user)
    week_start = week_start_for()
    week_count = weekly_workout_count(user, week_start)
    active_days = weekly_active_days(user, week_start)
    total_workouts = WorkoutLog.objects.filter(user=user).count()
    total_minutes = WorkoutLog.objects.filter(user=user).aggregate(total=Sum('duration_minutes'))['total'] or 0
    streak = current_weekly_streak(user, goal.weekly_target)
    progress_percent = min(100, round((week_count / goal.weekly_target) * 100)) if goal.weekly_target else 0
    activity_calendar = training_activity_calendar(user, activity_days)

    return {
        'goal': goal,
        'week_start': week_start,
        'week_count': week_count,
        'active_days': active_days,
        'total_workouts': total_workouts,
        'total_minutes': total_minutes,
        'streak': streak,
        'progress_percent': progress_percent,
        'activity_days': activity_days,
        'activity_range_options': ACTIVITY_RANGE_OPTIONS,
        'activity_calendar': activity_calendar,
        # Backward-compatible names used by some older templates/tests.
        'activity_grid': activity_calendar['cells'],
        'activity_columns': activity_calendar['total_weeks'],
        'activity_range_workouts': activity_calendar['range_workouts'],
        'activity_range_active_days': activity_calendar['range_active_days'],
    }
