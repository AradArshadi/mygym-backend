from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.bookings.models import Booking, GymCheckIn, GymSubscription, GymVisit, Session
from apps.bookings.services import refresh_due_membership_qrs_for_user
from apps.gyms.models import Gym
from apps.analytics.services import get_gym_analytics, get_owner_portfolio_analytics, normalize_analytics_days
from apps.reviews.models import Favorite, Review


def _can_access_owner_dashboard(user):
    return (
        user.is_authenticated
        and (
            getattr(user, 'role', '') in {'OWNER', 'ADMIN'}
            or user.is_staff
            or user.is_superuser
        )
    )


# Backwards-compatible alias for older imports.
def _refresh_due_membership_qrs_for_user(user):
    return refresh_due_membership_qrs_for_user(user)


@login_required
def owner_dashboard(request):
    if not _can_access_owner_dashboard(request.user):
        messages.warning(request, 'The owner dashboard is only available for gym owners and platform admins.')
        return redirect('customer_dashboard')

    days = normalize_analytics_days(request.GET.get('days'), default=30)
    portfolio = get_owner_portfolio_analytics(request.user, days=days)

    recent_booking_qs = Booking.objects.select_related('customer', 'trainer', 'plan').order_by('-created_at')
    gyms = Gym.objects.filter(owner=request.user).prefetch_related(
        Prefetch('bookings', queryset=recent_booking_qs, to_attr='recent_bookings')
    ).annotate(
        total_views=Count('views', distinct=True),
        total_bookings=Count('bookings', distinct=True),
        pending_bookings=Count('bookings', filter=Q(bookings__status=Booking.Status.PENDING), distinct=True),
        avg_rating=Avg('reviews__rating'),
        total_favorites=Count('favorited_by', distinct=True),
    )
    total_pending = Booking.objects.filter(gym__owner=request.user, status=Booking.Status.PENDING).count()
    total_confirmed = Booking.objects.filter(gym__owner=request.user, status=Booking.Status.CONFIRMED).count()
    today = timezone.localdate()

    pending_requests = Booking.objects.filter(
        gym__owner=request.user,
        status=Booking.Status.PENDING,
    ).select_related('customer', 'gym', 'plan', 'trainer').order_by('booking_datetime', 'created_at')[:20]

    confirmed_bookings = Booking.objects.filter(
        gym__owner=request.user,
        status=Booking.Status.CONFIRMED,
    ).select_related('customer', 'gym', 'plan', 'trainer').order_by('booking_datetime', '-created_at')[:20]

    todays_sessions = Session.objects.filter(gym__owner=request.user, start_time__date=today).select_related('customer', 'gym').order_by('start_time')[:20]
    todays_checkins = GymCheckIn.objects.filter(gym__owner=request.user, checked_in_at__date=today).select_related('customer', 'gym').order_by('-checked_in_at')[:20]
    active_visits = (
        GymVisit.objects
        .filter(gym__owner=request.user, status=GymVisit.Status.ACTIVE)
        .select_related('customer', 'gym', 'subscription__plan', 'session')
        .order_by('checked_in_at')[:50]
    )

    active_membership_qs = GymSubscription.objects.filter(
        gym__owner=request.user,
        status=GymSubscription.Status.ACTIVE,
        end_date__gte=today,
    ).select_related('customer', 'gym', 'plan').order_by('end_date', 'customer__username')
    active_memberships = active_membership_qs.count()
    active_membership_list = active_membership_qs[:20]

    return render(request, 'dashboard/owner_dashboard.html', {
        'gyms': gyms,
        'total_pending': total_pending,
        'total_confirmed': total_confirmed,
        'todays_sessions': todays_sessions,
        'todays_checkins': todays_checkins,
        'active_visits': active_visits,
        'active_memberships': active_memberships,
        'pending_requests': pending_requests,
        'confirmed_bookings': confirmed_bookings,
        'active_membership_list': active_membership_list,
        'portfolio': portfolio,
        'days': days,
        'range_options': [7, 30, 90, 120, 360],
    })

@login_required
def customer_dashboard(request):
    refresh_due_membership_qrs_for_user(request.user)
    bookings = Booking.objects.filter(customer=request.user).select_related('gym', 'trainer', 'plan')[:10]
    favorites = Favorite.objects.filter(user=request.user).select_related('gym')[:10]
    reviews = Review.objects.filter(user=request.user).select_related('gym')[:10]
    active_subscriptions = GymSubscription.objects.filter(customer=request.user, status=GymSubscription.Status.ACTIVE, end_date__gte=timezone.localdate()).select_related('gym', 'plan')[:3]
    upcoming_sessions = Session.objects.filter(customer=request.user, status=Session.Status.UPCOMING, start_time__gte=timezone.now()).select_related('gym')[:3]
    stats = {
        'bookings': Booking.objects.filter(customer=request.user).count(),
        'favorites': Favorite.objects.filter(user=request.user).count(),
        'reviews': Review.objects.filter(user=request.user).count(),
        'pending_bookings': Booking.objects.filter(customer=request.user, status=Booking.Status.PENDING).count(),
        'upcoming_sessions': Session.objects.filter(customer=request.user, status=Session.Status.UPCOMING, start_time__gte=timezone.now()).count(),
        'active_memberships': GymSubscription.objects.filter(customer=request.user, status=GymSubscription.Status.ACTIVE, end_date__gte=timezone.localdate()).count(),
    }
    return render(request, 'dashboard/customer_dashboard.html', {
        'bookings': bookings,
        'favorites': favorites,
        'reviews': reviews,
        'active_subscriptions': active_subscriptions,
        'upcoming_sessions': upcoming_sessions,
        'stats': stats,
    })


@login_required
def owner_analytics(request):
    if not _can_access_owner_dashboard(request.user):
        messages.warning(request, 'Analytics are only available for gym owners and platform admins.')
        return redirect('customer_dashboard')
    days = normalize_analytics_days(request.GET.get('days'), default=30)
    return redirect(f"{reverse('owner_dashboard')}?days={days}#owner-analytics")


@login_required
def owner_gym_analytics(request, gym_id):
    if not _can_access_owner_dashboard(request.user):
        messages.warning(request, 'Analytics are only available for gym owners and platform admins.')
        return redirect('customer_dashboard')
    gym = get_object_or_404(Gym, id=gym_id, owner=request.user)
    days = normalize_analytics_days(request.GET.get('days'), default=30)
    return redirect(f"{reverse('owner_dashboard')}?days={days}#owner-gym-analytics-{gym.id}")
