from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.emails.services import (
    send_booking_created_to_owner,
    send_booking_status_to_customer,
    send_membership_access_pass_to_customer,
    send_session_qr_to_customer,
)
from apps.gyms.models import Gym, MembershipPlan
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_safely
from apps.systemlogs.services import log_event

from .models import Booking, GymCheckIn, GymSubscription, GymVisit, Session
from .services import (
    absolute_url,
    attach_membership_qr,
    attach_session_qr,
    cancel_operational_records_for_booking,
    create_operational_records_for_confirmed_booking,
    membership_checkin_url,
    normalize_booking_datetime,
    refresh_due_membership_qrs_for_user,
    session_checkin_url,
    start_gym_visit,
    complete_gym_visit,
)


# Backwards-compatible aliases used by older imports in the project.
def _absolute_url(request, name, *args, **kwargs):
    return absolute_url(request, name, *args, **kwargs)


def _session_checkin_url(request, session):
    return session_checkin_url(request, session)


def _membership_checkin_url(request, subscription):
    return membership_checkin_url(request, subscription)


def _attach_session_qr(request, session):
    return attach_session_qr(request, session)


def _attach_membership_qr(request, subscription):
    return attach_membership_qr(request, subscription)


def _refresh_due_membership_qrs_for_user(user):
    return refresh_due_membership_qrs_for_user(user)


def _create_operational_records_for_confirmed_booking(booking, *, actor=None, request=None):
    return create_operational_records_for_confirmed_booking(booking, actor=actor, request=request)


def _is_owner_or_admin(user, gym):
    return gym.owner_id == user.id or user.is_staff or user.is_superuser or getattr(user, 'role', '') == 'ADMIN'


@login_required
def create_booking(request, gym_id):
    gym = get_object_or_404(Gym, id=gym_id, status=Gym.Status.APPROVED)
    if request.method == 'POST':
        booking_datetime = normalize_booking_datetime(request.POST.get('booking_datetime', ''))
        note = request.POST.get('customer_note', '')
        plan = None
        plan_id = request.POST.get('plan')
        if plan_id:
            plan = get_object_or_404(MembershipPlan, id=plan_id, gym=gym)

        if not booking_datetime:
            messages.error(request, 'Please choose a valid date and time.')
            return redirect('gym_detail', slug=gym.slug)

        booking, created = Booking.objects.get_or_create(
            customer=request.user,
            gym=gym,
            booking_datetime=booking_datetime,
            defaults={'customer_note': note, 'plan': plan},
        )
        if not created:
            messages.warning(request, 'You already have a booking request for this gym at this time.')
            return redirect('gym_detail', slug=gym.slug)

        send_booking_created_to_owner(booking, actor=request.user, request=request)
        log_event(level='INFO', category='BOOKING', event='booking_created', message=f'Booking request for {gym.name}', actor=request.user, request=request, related_model='Booking', related_id=booking.id)

        create_notification_safely(
            request=request,
            recipient=gym.owner,
            sender=request.user,
            kind=Notification.Kind.BOOKING,
            title=f'New booking request for {gym.name}',
            message=f'{request.user.username} requested a visit at {booking.booking_datetime}.',
            url='/dashboard/owner/',
        )
        create_notification_safely(
            request=request,
            recipient=request.user,
            sender=gym.owner,
            kind=Notification.Kind.BOOKING,
            title='Booking request sent',
            message=f'Your booking request for {gym.name} is now pending.',
            url='/dashboard/customer/',
        )

        messages.success(request, 'Booking request sent!')
    return redirect('gym_detail', slug=gym.slug)


@login_required
def update_booking_status(request, booking_id, status):
    """Allow a gym owner to accept or reject booking requests for their own gyms."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('owner_dashboard')

    booking = get_object_or_404(
        Booking.objects.select_related('gym', 'customer', 'plan'),
        id=booking_id,
        gym__owner=request.user,
    )

    allowed_statuses = {
        'confirm': Booking.Status.CONFIRMED,
        'reject': Booking.Status.REJECTED,
        'cancel': Booking.Status.CANCELLED,
    }

    new_status = allowed_statuses.get(status)
    if not new_status:
        messages.error(request, 'Invalid booking action.')
        return redirect('owner_dashboard')

    with transaction.atomic():
        old_status = booking.status
        booking.status = new_status
        booking.save(update_fields=['status'])

        session = None
        subscription = None
        if new_status == Booking.Status.CONFIRMED:
            session, subscription = create_operational_records_for_confirmed_booking(booking, actor=request.user, request=request)
        elif new_status in {Booking.Status.CANCELLED, Booking.Status.REJECTED}:
            cancel_operational_records_for_booking(booking, actor=request.user, request=request, reason='Closed by gym owner.')

    action_text = {
        Booking.Status.CONFIRMED: 'confirmed',
        Booking.Status.REJECTED: 'rejected',
        Booking.Status.CANCELLED: 'cancelled',
    }[new_status]

    create_notification_safely(
        request=request,
        recipient=booking.customer,
        sender=request.user,
        kind=Notification.Kind.BOOKING,
        title=f'Booking {action_text}',
        message=f'Your booking request for {booking.gym.name} was {action_text}.',
        url='/bookings/sessions/' if new_status == Booking.Status.CONFIRMED else '/dashboard/customer/',
    )

    send_booking_status_to_customer(booking, action_text, actor=request.user, request=request)
    if new_status == Booking.Status.CONFIRMED and session:
        attach_session_qr(request, session)
        send_session_qr_to_customer(session, session.qr_url, session.qr_data_uri, actor=request.user, request=request)
        if subscription:
            attach_membership_qr(request, subscription)
            send_membership_access_pass_to_customer(subscription, subscription.qr_url, subscription.qr_data_uri, actor=request.user, request=request)

    log_event(level='INFO', category='BOOKING', event='booking_status_updated', message=f'Booking {booking.id} moved from {old_status} to {new_status}', actor=request.user, request=request, related_model='Booking', related_id=booking.id, metadata={'old_status': old_status, 'new_status': new_status})

    messages.success(request, f'Booking moved from {old_status} to {new_status}.')
    return redirect('owner_dashboard')


@login_required
def cancel_own_booking(request, booking_id):
    """Allow customers to cancel their own pending/confirmed bookings."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('customer_dashboard')

    booking = get_object_or_404(
        Booking.objects.select_related('gym'),
        id=booking_id,
        customer=request.user,
    )

    if booking.status in [Booking.Status.CANCELLED, Booking.Status.REJECTED]:
        messages.warning(request, 'This booking is already closed.')
        return redirect('customer_dashboard')

    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=['status'])
    cancel_operational_records_for_booking(booking, actor=request.user, request=request, reason='Cancelled by customer.')

    create_notification_safely(
        request=request,
        recipient=booking.gym.owner,
        sender=request.user,
        kind=Notification.Kind.BOOKING,
        title='Booking cancelled by customer',
        message=f'{request.user.username} cancelled a booking for {booking.gym.name}.',
        url='/dashboard/owner/',
    )

    log_event(level='INFO', category='BOOKING', event='booking_cancelled_by_customer', message=f'Customer cancelled booking {booking.id}', actor=request.user, request=request, related_model='Booking', related_id=booking.id)
    messages.success(request, 'Booking cancelled.')
    return redirect('customer_dashboard')


@login_required
def my_sessions(request):
    refresh_due_membership_qrs_for_user(request.user)
    sessions = Session.objects.filter(customer=request.user).select_related('gym', 'booking', 'booking__plan')
    now = timezone.now()
    upcoming = sessions.filter(status=Session.Status.UPCOMING, start_time__gte=now).order_by('start_time')
    previous = sessions.exclude(status__in=[Session.Status.UPCOMING, Session.Status.CANCELLED]).order_by('-start_time')
    cancelled = sessions.filter(status=Session.Status.CANCELLED).order_by('-start_time')

    # For demo friendliness, future sessions include QR data directly in the list.
    for session in upcoming:
        attach_session_qr(request, session)

    return render(request, 'bookings/my_sessions.html', {
        'upcoming_sessions': upcoming,
        'previous_sessions': previous,
        'cancelled_sessions': cancelled,
    })


@login_required
def session_detail(request, session_id):
    session = get_object_or_404(Session.objects.select_related('gym', 'booking', 'booking__plan'), id=session_id, customer=request.user)
    attach_session_qr(request, session)
    return render(request, 'bookings/session_detail.html', {'session': session})


@login_required
def cancel_session(request, session_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('my_sessions')
    session = get_object_or_404(Session.objects.select_related('booking', 'gym'), id=session_id, customer=request.user)
    if session.status != Session.Status.UPCOMING:
        messages.warning(request, 'Only upcoming sessions can be cancelled.')
        return redirect('my_sessions')

    session.cancel('Cancelled by customer from My Sessions.')
    session.booking.status = Booking.Status.CANCELLED
    session.booking.save(update_fields=['status'])

    create_notification_safely(
        request=request,
        recipient=session.gym.owner,
        sender=request.user,
        kind=Notification.Kind.BOOKING,
        title='Session cancelled by customer',
        message=f'{request.user.username} cancelled a session for {session.gym.name}.',
        url='/dashboard/owner/',
    )

    log_event(level='INFO', category='SESSION', event='session_cancelled_by_customer', message=f'Session {session.id} cancelled by customer', actor=request.user, request=request, related_model='Session', related_id=session.id)
    messages.success(request, 'Session cancelled.')
    return redirect('my_sessions')


@login_required
def my_memberships(request):
    refresh_due_membership_qrs_for_user(request.user)
    subscriptions = GymSubscription.objects.filter(customer=request.user).select_related('gym', 'plan')
    active = []
    expired_or_closed = []
    for subscription in subscriptions:
        subscription.mark_expired_if_needed()
        if subscription.status == GymSubscription.Status.ACTIVE:
            attach_membership_qr(request, subscription)
            active.append(subscription)
        else:
            expired_or_closed.append(subscription)
    active_visit = (
        GymVisit.objects
        .filter(customer=request.user, status=GymVisit.Status.ACTIVE)
        .select_related('gym', 'subscription__plan', 'session')
        .first()
    )
    return render(request, 'bookings/my_memberships.html', {
        'active_subscriptions': active,
        'closed_subscriptions': expired_or_closed,
        'active_visit': active_visit,
    })


@login_required
def refresh_membership_qr(request, subscription_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('my_memberships')
    subscription = get_object_or_404(GymSubscription, id=subscription_id, customer=request.user)
    if not subscription.is_active:
        messages.warning(request, 'This access pass is not active.')
        return redirect('my_memberships')
    subscription.refresh_qr_if_needed(force=True)
    messages.success(request, 'Access Pass QR refreshed.')
    return redirect('my_memberships')


@login_required
def session_check_in(request, token):
    session = get_object_or_404(Session.objects.select_related('customer', 'gym', 'booking', 'booking__plan'), qr_token=token)
    authorized = _is_owner_or_admin(request.user, session.gym)
    valid = authorized and session.is_one_time_qr_available
    if not authorized:
        reason = 'Only this gym owner or platform admin can validate this QR code.'
    elif not session.is_one_time_qr_available:
        reason = 'This one-time session QR is cancelled, already used, or no longer available.'
    else:
        reason = ''

    if request.method == 'POST':
        if not valid:
            messages.error(request, reason or 'Invalid session QR code.')
            return redirect('owner_dashboard')
        try:
            with transaction.atomic():
                locked = Session.objects.select_for_update().select_related('customer', 'gym', 'booking', 'booking__plan').get(pk=session.pk)
                if not locked.is_one_time_qr_available:
                    messages.error(request, 'This one-time session QR has already been used.')
                    return redirect('owner_dashboard')
                visit, created = start_gym_visit(
                    customer=locked.customer, gym=locked.gym, actor=request.user,
                    entry_method=GymVisit.EntryMethod.SESSION_QR, session=locked, request=request,
                )
                checkin = locked.mark_checked_in()
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('owner_dashboard')
        log_event(level='INFO', category='CHECKIN', event='session_checkin_confirmed', message=f'Session {session.id} checked in', actor=request.user, request=request, related_model='GymCheckIn', related_id=checkin.id)
        messages.success(request, f'{locked.customer.get_full_name() or locked.customer.username} is now checked in at {locked.gym.name}.')
        return redirect('owner_dashboard')

    active_visit = GymVisit.objects.filter(customer=session.customer, status=GymVisit.Status.ACTIVE).select_related('gym').first()
    return render(request, 'bookings/check_in_validate.html', {
        'mode': 'SESSION', 'valid': valid, 'reason': reason,
        'session': session if authorized else None, 'subscription': None,
        'authorized': authorized, 'active_visit': active_visit,
    })


@login_required
def membership_check_in(request, token):
    subscription = get_object_or_404(GymSubscription.objects.select_related('customer', 'gym', 'plan'), current_qr_token=token)
    subscription.mark_expired_if_needed()
    authorized = _is_owner_or_admin(request.user, subscription.gym)
    valid = authorized and subscription.is_active and subscription.qr_is_fresh
    if not authorized:
        reason = 'Only this gym owner or platform admin can validate this Access Pass.'
    elif not subscription.is_active:
        reason = 'This membership is not active or has expired.'
    elif not subscription.qr_is_fresh:
        reason = 'This Access Pass QR is older than 24 hours. The customer must open their account to refresh it.'
    else:
        reason = ''

    if request.method == 'POST':
        if not valid:
            messages.error(request, reason or 'Invalid Access Pass QR.')
            return redirect('owner_dashboard')
        try:
            with transaction.atomic():
                locked = GymSubscription.objects.select_for_update().select_related('customer', 'gym', 'plan').get(pk=subscription.pk)
                locked.mark_expired_if_needed()
                if not locked.is_active or not locked.qr_is_fresh:
                    messages.error(request, 'This membership pass is no longer valid.')
                    return redirect('owner_dashboard')
                visit, created = start_gym_visit(
                    customer=locked.customer, gym=locked.gym, actor=request.user,
                    entry_method=GymVisit.EntryMethod.MEMBERSHIP_QR,
                    subscription=locked, request=request,
                )
                if created:
                    checkin = GymCheckIn.objects.create(
                        customer=locked.customer, gym=locked.gym, subscription=locked,
                        checkin_type=GymCheckIn.CheckInType.MEMBERSHIP,
                    )
                else:
                    checkin = None
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('owner_dashboard')
        if checkin:
            log_event(level='INFO', category='CHECKIN', event='membership_checkin_confirmed', message=f'Subscription {subscription.id} checked in', actor=request.user, request=request, related_model='GymCheckIn', related_id=checkin.id)
        message = 'Active visit already exists.' if not created else 'Access granted and active visit started.'
        messages.success(request, f'{locked.customer.get_full_name() or locked.customer.username}: {message}')
        return redirect('owner_dashboard')

    active_visit = GymVisit.objects.filter(customer=subscription.customer, status=GymVisit.Status.ACTIVE).select_related('gym').first()
    return render(request, 'bookings/check_in_validate.html', {
        'mode': 'MEMBERSHIP', 'valid': valid, 'reason': reason,
        'session': None, 'subscription': subscription if authorized else None,
        'authorized': authorized, 'active_visit': active_visit,
    })


@login_required
def checkout_visit(request, visit_id):
    if request.method != 'POST':
        messages.error(request, 'Checkout requires confirmation.')
        return redirect('my_memberships')

    visit = get_object_or_404(GymVisit.objects.select_related('customer', 'gym'), pk=visit_id)
    is_customer = visit.customer_id == request.user.id
    is_staff = _is_owner_or_admin(request.user, visit.gym)
    if not (is_customer or is_staff):
        messages.error(request, 'You are not allowed to finish this visit.')
        return redirect('fitness_home')

    visit, completed = complete_gym_visit(visit=visit, actor=request.user, request=request)
    if completed:
        messages.success(request, f'Visit completed. Total duration: {visit.duration_minutes} minutes.')
    else:
        messages.info(request, 'This visit is already closed.')
    return redirect('fitness_home' if is_customer else 'owner_dashboard')

