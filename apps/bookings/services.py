from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.systemlogs.services import log_event

from .models import Booking, GymSubscription, Session
from .qr_utils import build_qr_data_uri


def normalize_booking_datetime(value):
    """Parse datetime-local input and always return an aware Europe/Berlin datetime.

    HTML datetime-local fields submit values like ``2026-08-05T14:30`` without a timezone.
    Because the project runs with USE_TZ=True, storing that value directly can create subtle
    local-time bugs. This helper treats naive values as the current Django timezone.
    """
    if not value:
        return None

    dt = parse_datetime(value) if isinstance(value, str) else value
    if not dt:
        return None

    current_tz = timezone.get_current_timezone()
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, current_tz)
    return timezone.localtime(dt, current_tz)


def absolute_url(request, name, *args, **kwargs):
    path = reverse(name, args=args, kwargs=kwargs)
    if request is not None:
        try:
            return request.build_absolute_uri(path)
        except Exception as exc:  # defensive fallback for CLI/tests/proxy edge cases
            log_event(
                level='WARNING',
                category='SYSTEM',
                event='absolute_url_build_failed',
                message=f'Falling back to SITE_URL for {name}: {exc}',
                request=request,
            )

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    return f'{site_url}{path}' if site_url else path


def session_checkin_url(request, session):
    return absolute_url(request, 'session_check_in', session.qr_token)


def membership_checkin_url(request, subscription):
    return absolute_url(request, 'membership_check_in', subscription.current_qr_token)


def attach_session_qr(request, session):
    url = session_checkin_url(request, session)
    session.qr_url = url
    session.qr_data_uri = build_qr_data_uri(url)
    return session


def attach_membership_qr(request, subscription):
    url = membership_checkin_url(request, subscription)
    subscription.qr_url = url
    subscription.qr_data_uri = build_qr_data_uri(url)
    return subscription


def refresh_due_membership_qrs_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return 0

    refreshed = 0
    for subscription in GymSubscription.objects.filter(customer=user, status=GymSubscription.Status.ACTIVE):
        subscription.mark_expired_if_needed()
        if subscription.status == GymSubscription.Status.ACTIVE and subscription.needs_qr_refresh:
            subscription.refresh_qr_if_needed()
            refreshed += 1
    return refreshed


def create_operational_records_for_confirmed_booking(booking, *, actor=None, request=None):
    """Create operational records that must exist for every confirmed booking.

    Both owner confirmation and Control Deck/admin confirmation must use this same function.
    That prevents confirmed bookings from existing without a Session or Access Pass.
    """
    if booking.status != Booking.Status.CONFIRMED:
        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=['status'])

    session, session_created = Session.objects.get_or_create(
        booking=booking,
        defaults={
            'customer': booking.customer,
            'gym': booking.gym,
            'start_time': booking.booking_datetime,
            'end_time': booking.booking_datetime + timedelta(hours=1),
        },
    )
    if not session_created and session.status == Session.Status.CANCELLED:
        session.status = Session.Status.UPCOMING
        session.start_time = booking.booking_datetime
        session.end_time = booking.booking_datetime + timedelta(hours=1)
        session.cancelled_at = None
        session.cancel_reason = ''
        session.qr_used_at = None
        session.checked_in_at = None
        session.save(update_fields=[
            'status',
            'start_time',
            'end_time',
            'cancelled_at',
            'cancel_reason',
            'qr_used_at',
            'checked_in_at',
            'updated_at',
        ])

    subscription = None
    subscription_created = False
    if booking.plan and not booking.plan.is_trial:
        start_date = timezone.localdate(booking.booking_datetime)
        end_date = start_date + timedelta(days=max(booking.plan.duration_days, 1))
        subscription, subscription_created = GymSubscription.objects.get_or_create(
            source_booking=booking,
            defaults={
                'customer': booking.customer,
                'gym': booking.gym,
                'plan': booking.plan,
                'status': GymSubscription.Status.ACTIVE,
                'start_date': start_date,
                'end_date': end_date,
            },
        )
        if not subscription_created and subscription.status != GymSubscription.Status.ACTIVE:
            subscription.status = GymSubscription.Status.ACTIVE
            subscription.plan = booking.plan
            subscription.start_date = start_date
            subscription.end_date = end_date
            subscription.save(update_fields=['status', 'plan', 'start_date', 'end_date', 'updated_at'])
        subscription.refresh_qr_if_needed(force=True)

    if session_created:
        log_event(
            level='INFO',
            category='SESSION',
            event='session_created',
            message=f'Session created for booking {booking.id}',
            actor=actor,
            request=request,
            related_model='Session',
            related_id=session.id,
        )
    if subscription_created and subscription:
        log_event(
            level='INFO',
            category='SUBSCRIPTION',
            event='subscription_created',
            message=f'Access pass created for booking {booking.id}',
            actor=actor,
            request=request,
            related_model='GymSubscription',
            related_id=subscription.id,
        )

    return session, subscription


def cancel_operational_records_for_booking(booking, *, actor=None, request=None, reason='Booking closed.'):
    """Cancel linked operational records when a confirmed booking is cancelled/rejected."""
    cancelled = {'session': False, 'subscription': False}

    try:
        session = booking.session
    except Session.DoesNotExist:
        session = None

    if session and session.status != Session.Status.CANCELLED:
        session.cancel(reason)
        cancelled['session'] = True
        log_event(
            level='INFO',
            category='SESSION',
            event='session_cancelled',
            message=f'Session {session.id} cancelled because booking {booking.id} was closed.',
            actor=actor,
            request=request,
            related_model='Session',
            related_id=session.id,
        )

    try:
        subscription = booking.subscription
    except GymSubscription.DoesNotExist:
        subscription = None

    if subscription and subscription.status == GymSubscription.Status.ACTIVE:
        subscription.status = GymSubscription.Status.CANCELLED
        subscription.save(update_fields=['status', 'updated_at'])
        cancelled['subscription'] = True
        log_event(
            level='INFO',
            category='SUBSCRIPTION',
            event='subscription_cancelled',
            message=f'Access pass {subscription.id} cancelled because booking {booking.id} was closed.',
            actor=actor,
            request=request,
            related_model='GymSubscription',
            related_id=subscription.id,
        )

    return cancelled


def start_gym_visit(*, customer, gym, actor, entry_method, session=None, subscription=None, request=None):
    """Create one live visit per customer and preserve an existing same-gym visit."""
    from django.db import IntegrityError, transaction
    from .models import GymVisit

    with transaction.atomic():
        existing = (
            GymVisit.objects.select_for_update()
            .filter(customer=customer, status=GymVisit.Status.ACTIVE)
            .select_related('gym', 'subscription__plan')
            .first()
        )
        if existing:
            if existing.gym_id == gym.id:
                return existing, False
            raise ValueError(f'Customer already has an active visit at {existing.gym.name}.')

        try:
            visit = GymVisit.objects.create(
                customer=customer,
                gym=gym,
                session=session,
                subscription=subscription,
                checked_in_by=actor,
                entry_method=entry_method,
            )
        except IntegrityError:
            visit = GymVisit.objects.get(customer=customer, status=GymVisit.Status.ACTIVE)
            if visit.gym_id != gym.id:
                raise ValueError(f'Customer already has an active visit at {visit.gym.name}.')
            return visit, False

    log_event(
        level='INFO', category='CHECKIN', event='gym_visit_started',
        message=f'Active visit {visit.id} started at {gym.name}', actor=actor,
        request=request, related_model='GymVisit', related_id=visit.id,
    )
    return visit, True


def complete_gym_visit(*, visit, actor, request=None):
    """Atomically finish an active visit and record who completed it."""
    from django.db import transaction
    from .models import GymVisit, Session

    with transaction.atomic():
        locked = GymVisit.objects.select_for_update().select_related('gym', 'customer', 'session').get(pk=visit.pk)
        if locked.status != GymVisit.Status.ACTIVE:
            return locked, False
        locked.status = GymVisit.Status.COMPLETED
        locked.checked_out_at = timezone.now()
        locked.checked_out_by = actor
        locked.save(update_fields=['status', 'checked_out_at', 'checked_out_by', 'updated_at'])
        if locked.session_id and locked.session.status == Session.Status.CHECKED_IN:
            locked.session.status = Session.Status.COMPLETED
            locked.session.end_time = locked.checked_out_at
            locked.session.save(update_fields=['status', 'end_time', 'updated_at'])

    log_event(
        level='INFO', category='CHECKIN', event='gym_visit_completed',
        message=f'Visit {locked.id} completed after {locked.duration_minutes} minutes',
        actor=actor, request=request, related_model='GymVisit', related_id=locked.id,
    )
    return locked, True
