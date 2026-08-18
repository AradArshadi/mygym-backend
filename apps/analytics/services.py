from decimal import Decimal
from datetime import datetime, timedelta

from collections import defaultdict

from django.db.models import Count
from django.utils import timezone

from apps.bookings.models import Booking, GymCheckIn, GymSubscription
from apps.gyms.models import Gym
from apps.reviews.models import Favorite
from apps.analytics.models import GymView

ALLOWED_ANALYTICS_DAYS = {7, 30, 90, 120, 360}


def normalize_analytics_days(value, default=30):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return days if days in ALLOWED_ANALYTICS_DAYS else default


def _range(days):
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    start_dt = timezone.make_aware(datetime.combine(start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end + timedelta(days=1), datetime.min.time()))
    return start, end, start_dt, end_dt


def _pct_change(current, previous):
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)
    if previous == 0:
        return None if current == 0 else Decimal('100')
    return ((current - previous) / previous) * Decimal('100')


def _money(value):
    return Decimal(value or 0).quantize(Decimal('0.01'))


def get_gym_income_streams(gym, days=30):
    """Scalable income calculation.

    Today this is estimated from confirmed bookings/subscription access passes.
    Future income sources can append new stream dictionaries here, e.g. products,
    trainer sessions, class packs, marketplace fees, or Stripe payments.
    """
    start, end, start_dt, end_dt = _range(days)

    subscription_qs = GymSubscription.objects.filter(
        gym=gym,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    ).select_related('plan')
    subscription_income = sum((sub.plan.price if sub.plan else Decimal('0.00')) for sub in subscription_qs)

    confirmed_without_subscription_qs = Booking.objects.filter(
        gym=gym,
        status=Booking.Status.CONFIRMED,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
        subscription__isnull=True,
    ).select_related('plan')
    one_time_income = sum((booking.plan.price if booking.plan else Decimal('0.00')) for booking in confirmed_without_subscription_qs)

    streams = [
        {
            'key': 'subscriptions',
            'label': 'Subscriptions',
            'amount': _money(subscription_income),
            'count': subscription_qs.count(),
            'description': 'Estimated from membership/access-pass plans.',
        },
        {
            'key': 'bookings',
            'label': 'Other confirmed bookings',
            'amount': _money(one_time_income),
            'count': confirmed_without_subscription_qs.count(),
            'description': 'Extension point for trials, classes, trainer sessions, and future paid bookings.',
        },
    ]
    total = _money(sum(stream['amount'] for stream in streams))
    return {'streams': streams, 'total': total}


def _safe_localtime(value):
    """Return a localized datetime or None.

    PythonAnywhere/MySQL deployments can return NULL from database timezone
    conversion functions when MySQL timezone tables are not loaded. Analytics
    should not depend on DB-side Extract/Trunc helpers, so we aggregate in
    Python with this defensive converter instead.
    """
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value, timezone.get_current_timezone())


def get_peak_hour_data(gym, days=30):
    start, end, start_dt, end_dt = _range(days)
    previous_start_dt = start_dt - timedelta(days=days)

    current_counts = defaultdict(int)
    previous_counts = defaultdict(int)

    current_times = GymCheckIn.objects.filter(
        gym=gym,
        checked_in_at__gte=start_dt,
        checked_in_at__lt=end_dt,
    ).values_list('checked_in_at', flat=True)
    previous_times = GymCheckIn.objects.filter(
        gym=gym,
        checked_in_at__gte=previous_start_dt,
        checked_in_at__lt=start_dt,
    ).values_list('checked_in_at', flat=True)

    for checked_in_at in current_times:
        local_dt = _safe_localtime(checked_in_at)
        if local_dt is not None:
            current_counts[local_dt.hour] += 1

    for checked_in_at in previous_times:
        local_dt = _safe_localtime(checked_in_at)
        if local_dt is not None:
            previous_counts[local_dt.hour] += 1

    max_current = max(current_counts.values(), default=0)
    max_previous = max(previous_counts.values(), default=0)
    max_count = max(max_current, max_previous, 1)
    total_current = sum(current_counts.values())
    total_previous = sum(previous_counts.values())

    if total_previous:
        change_percent = round(((total_current - total_previous) / total_previous) * 100, 1)
    elif total_current:
        change_percent = 100.0
    else:
        change_percent = 0.0

    hours = []
    for hour in range(24):
        current = current_counts.get(hour, 0)
        previous = previous_counts.get(hour, 0)
        current_pct = int((current / max_count) * 100) if current else 0
        previous_pct = int((previous / max_count) * 100) if previous else 0
        delta = current - previous
        if delta > 0:
            trend = 'up'
        elif delta < 0:
            trend = 'down'
        else:
            trend = 'flat'
        hours.append({
            'hour': hour,
            'label': f'{hour:02d}:00–{(hour + 1) % 24:02d}:00',
            'short_label': f'{hour:02d}',
            'count': current,
            'previous_count': previous,
            'delta': delta,
            'current_height': max(8, current_pct) if current else 4,
            'previous_height': max(8, previous_pct) if previous else 4,
            'is_peak': bool(max_current and current == max_current and current > 0),
            'show_label': hour in {0, 3, 6, 9, 12, 15, 18, 21},
            'trend': trend,
        })

    peak = [item for item in hours if item['is_peak']]
    fastest_rising = max(hours, key=lambda item: item['delta']) if hours else None
    largest_decline = min(hours, key=lambda item: item['delta']) if hours else None
    busiest_hour = max(hours, key=lambda item: item['count']) if hours else None

    return {
        'hours': hours,
        'peak': peak,
        'max_count': max_count,
        'summary': {
            'total_current': total_current,
            'total_previous': total_previous,
            'change_percent': change_percent,
            'change_label': f"{change_percent:+.1f}%",
            'change_direction': 'up' if change_percent > 0 else 'down' if change_percent < 0 else 'flat',
            'busiest_hour': busiest_hour,
            'fastest_rising': fastest_rising,
            'largest_decline': largest_decline,
        },
    }


def get_weekday_traffic_data(gym, days=30):
    start, end, start_dt, end_dt = _range(days)
    raw = defaultdict(int)
    checkin_times = GymCheckIn.objects.filter(
        gym=gym,
        checked_in_at__gte=start_dt,
        checked_in_at__lt=end_dt,
    ).values_list('checked_in_at', flat=True)

    for checked_in_at in checkin_times:
        local_dt = _safe_localtime(checked_in_at)
        if local_dt is not None:
            raw[local_dt.weekday()] += 1  # Monday=0 ... Sunday=6

    order = [(0, 'Mon'), (1, 'Tue'), (2, 'Wed'), (3, 'Thu'), (4, 'Fri'), (5, 'Sat'), (6, 'Sun')]
    max_count = max(raw.values(), default=0)
    days_out = []
    for key, label in order:
        count = raw.get(key, 0)
        pct = int((count / max_count) * 100) if max_count else 0
        days_out.append({'label': label, 'count': count, 'width': max(6, pct) if count else 4})
    return days_out


def get_growth_data(gym, days=30):
    start, end, start_dt, end_dt = _range(days)
    previous_start_dt = start_dt - timedelta(days=days)
    current_subs = GymSubscription.objects.filter(gym=gym, created_at__gte=start_dt, created_at__lt=end_dt).count()
    previous_subs = GymSubscription.objects.filter(gym=gym, created_at__gte=previous_start_dt, created_at__lt=start_dt).count()
    active_members = GymSubscription.objects.filter(
        gym=gym,
        status=GymSubscription.Status.ACTIVE,
        start_date__lte=end,
        end_date__gte=end,
    ).count()

    buckets = defaultdict(int)
    created_times = GymSubscription.objects.filter(
        gym=gym,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    ).values_list('created_at', flat=True)

    for created_at in created_times:
        local_dt = _safe_localtime(created_at)
        if local_dt is None:
            continue
        bucket = local_dt.date().replace(day=1) if days >= 120 else local_dt.date()
        buckets[bucket] += 1

    max_count = max(buckets.values(), default=0)
    trend = []
    for bucket, count in sorted(buckets.items()):
        label = bucket.strftime('%b') if days >= 120 else bucket.strftime('%d %b')
        trend.append({
            'label': label,
            'count': count,
            'height': int((count / max_count) * 100) if max_count else 0,
        })

    return {
        'new_members': current_subs,
        'previous_new_members': previous_subs,
        'change_pct': _pct_change(current_subs, previous_subs),
        'change_pct_known': _pct_change(current_subs, previous_subs) is not None,
        'active_members': active_members,
        'trend': trend,
    }


def get_conversion_metrics(gym, days=30):
    start, end, start_dt, end_dt = _range(days)
    qs = Booking.objects.filter(gym=gym, created_at__gte=start_dt, created_at__lt=end_dt)
    total = qs.count()
    confirmed = qs.filter(status=Booking.Status.CONFIRMED).count()
    pending = qs.filter(status=Booking.Status.PENDING).count()
    rejected = qs.filter(status=Booking.Status.REJECTED).count()
    cancelled = qs.filter(status=Booking.Status.CANCELLED).count()
    rate = round((confirmed / total) * 100, 1) if total else 0
    handled_total = confirmed + rejected + cancelled
    handled_rate = round((confirmed / handled_total) * 100, 1) if handled_total else 0
    return {
        'total': total,
        'confirmed': confirmed,
        'pending': pending,
        'rejected': rejected,
        'cancelled': cancelled,
        'rate': rate,
        'handled_rate': handled_rate,
    }


def get_gym_analytics(gym, days=30):
    days = normalize_analytics_days(days)
    start, end, start_dt, end_dt = _range(days)
    income = get_gym_income_streams(gym, days)
    peak = get_peak_hour_data(gym, days)
    growth = get_growth_data(gym, days)
    conversion = get_conversion_metrics(gym, days)
    traffic_days = get_weekday_traffic_data(gym, days)
    total_checkins = GymCheckIn.objects.filter(gym=gym, checked_in_at__gte=start_dt, checked_in_at__lt=end_dt).count()
    views = GymView.objects.filter(gym=gym, created_at__gte=start_dt, created_at__lt=end_dt).count()
    favorites = Favorite.objects.filter(gym=gym).count()
    avg_hour = peak['peak'][0]['label'] if peak['peak'] else '—'
    recent_checkins = GymCheckIn.objects.filter(gym=gym).select_related('customer').order_by('-checked_in_at')[:8]
    return {
        'gym': gym,
        'days': days,
        'start': start,
        'end': end,
        'income': income,
        'peak': peak,
        'growth': growth,
        'conversion': conversion,
        'traffic_days': traffic_days,
        'total_checkins': total_checkins,
        'views': views,
        'favorites': favorites,
        'peak_label': avg_hour,
        'recent_checkins': recent_checkins,
    }


def get_owner_portfolio_analytics(owner, days=30):
    days = normalize_analytics_days(days)
    gyms = list(Gym.objects.filter(owner=owner).order_by('name'))
    gym_cards = []
    total_income = Decimal('0.00')
    total_checkins = 0
    total_active_members = 0
    total_bookings = 0
    total_favorites = 0
    for gym in gyms:
        metrics = get_gym_analytics(gym, days)
        total_income += metrics['income']['total']
        total_checkins += metrics['total_checkins']
        total_active_members += metrics['growth']['active_members']
        total_bookings += metrics['conversion']['total']
        total_favorites += metrics['favorites']
        gym_cards.append(metrics)
    for item in gym_cards:
        item['checkin_share'] = int((item['total_checkins'] / total_checkins) * 100) if total_checkins else 0
        item['income_share'] = int((item['income']['total'] / total_income) * 100) if total_income else 0
    top_by_checkins = sorted(gym_cards, key=lambda item: item['total_checkins'], reverse=True)[:5]
    top_by_income = sorted(gym_cards, key=lambda item: item['income']['total'], reverse=True)[:5]
    return {
        'days': days,
        'gyms': gyms,
        'gym_cards': gym_cards,
        'top_by_checkins': top_by_checkins,
        'top_by_income': top_by_income,
        'totals': {
            'gyms': len(gyms),
            'income': _money(total_income),
            'checkins': total_checkins,
            'active_members': total_active_members,
            'bookings': total_bookings,
            'favorites': total_favorites,
        },
    }
