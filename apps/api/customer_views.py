from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.db.models import Avg, Count, Q
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.services import get_peak_hour_data
from apps.bookings.models import Booking, GymSubscription, GymVisit, Session
from apps.bookings.services import (
    attach_membership_qr,
    attach_session_qr,
    cancel_operational_records_for_booking,
    complete_gym_visit,
    normalize_booking_datetime,
    refresh_due_membership_qrs_for_user,
)
from apps.emails.services import send_booking_created_to_owner, send_review_notice_to_owner
from apps.fitness.services import fitness_summary
from apps.fitness.forms import ProfileUpdateForm
from apps.gyms.models import Gym, MembershipPlan
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_safely
from apps.reviews.models import Favorite, Review
from apps.systemlogs.services import log_event


def _decimal(value):
    return f'{value or 0:.2f}'


def _datetime(value):
    return timezone.localtime(value).isoformat() if value else None


def _date(value):
    return value.isoformat() if value else None


def _user(user):
    if not user or not user.is_authenticated:
        return None
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'name': user.get_full_name() or user.username,
        'phone': getattr(user, 'phone', ''),
        'role': getattr(user, 'role', ''),
        'member_since': _date(user.date_joined.date()) if user.date_joined else None,
    }


def _safe_image_url(image):
    if not image:
        return ''
    external = getattr(image, 'external_url', '') or ''
    if external:
        return external
    if getattr(image, 'image', None):
        try:
            if image.image.storage.exists(image.image.name):
                return image.image.url
        except Exception:
            pass
    return ''


def _gym(gym):
    image = gym.cover_image
    return {
        'id': gym.id,
        'name': gym.name,
        'slug': gym.slug,
        'city': gym.city,
        'address': gym.address,
        'starting_price': _decimal(gym.starting_price),
        'cover_image': _safe_image_url(image),
    }


def _booking(booking):
    return {
        'id': booking.id,
        'gym': _gym(booking.gym),
        'plan': ({
            'id': booking.plan_id,
            'title': booking.plan.title,
            'price': _decimal(booking.plan.price),
        } if booking.plan else None),
        'status': booking.status,
        'booking_datetime': _datetime(booking.booking_datetime),
        'created_at': _datetime(booking.created_at),
    }


def _session(request, session, with_qr=False):
    if with_qr and session.is_one_time_qr_available:
        attach_session_qr(request, session)
    return {
        'id': session.id,
        'gym': _gym(session.gym),
        'status': session.status,
        'start_time': _datetime(session.start_time),
        'end_time': _datetime(session.end_time),
        'plan': session.booking.plan.title if session.booking and session.booking.plan else None,
        'qr_data_uri': getattr(session, 'qr_data_uri', ''),
        'qr_url': getattr(session, 'qr_url', ''),
    }


def _subscription(request, subscription, with_qr=False):
    subscription.mark_expired_if_needed()
    if with_qr and subscription.is_active:
        attach_membership_qr(request, subscription)
    return {
        'id': subscription.id,
        'gym': _gym(subscription.gym),
        'plan': ({
            'id': subscription.plan_id,
            'title': subscription.plan.title,
            'price': _decimal(subscription.plan.price),
            'duration_days': subscription.plan.duration_days,
        } if subscription.plan else None),
        'status': subscription.status,
        'start_date': _date(subscription.start_date),
        'end_date': _date(subscription.end_date),
        'days_remaining': subscription.days_remaining,
        'qr_data_uri': getattr(subscription, 'qr_data_uri', ''),
        'qr_url': getattr(subscription, 'qr_url', ''),
    }


def _visit(visit):
    return {
        'id': visit.id,
        'gym': _gym(visit.gym),
        'status': visit.status,
        'entry_method': visit.entry_method,
        'checked_in_at': _datetime(visit.checked_in_at),
        'checked_out_at': _datetime(visit.checked_out_at),
        'duration_minutes': visit.duration_minutes,
        'subscription_id': visit.subscription_id,
        'session_id': visit.session_id,
        'access_label': (
            visit.subscription.plan.title
            if visit.subscription and visit.subscription.plan
            else 'Session'
        ),
    }


class CsrfAPIView(APIView):
    permission_classes = []

    def get(self, request):
        return Response({'csrfToken': get_token(request)})


class MeAPIView(APIView):
    permission_classes = []

    def get(self, request):
        return Response({'authenticated': request.user.is_authenticated, 'user': _user(request.user)})


class LoginAPIView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        username = str(request.data.get('username', '')).strip()
        password = str(request.data.get('password', ''))
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response({'detail': 'Username or password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        get_token(request)
        return Response({'ok': True, 'user': _user(user)})


class LogoutAPIView(APIView):
    permission_classes = []

    def post(self, request):
        logout(request)
        return Response({'ok': True})


class CustomerHomeAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        refresh_due_membership_qrs_for_user(request.user)
        now = timezone.now()
        today = timezone.localdate()
        upcoming = list(
            Session.objects.filter(
                customer=request.user,
                status=Session.Status.UPCOMING,
                start_time__gte=now,
            ).select_related('gym', 'booking__plan').order_by('start_time')[:4]
        )
        subscriptions = list(
            GymSubscription.objects.filter(
                customer=request.user,
                status=GymSubscription.Status.ACTIVE,
                end_date__gte=today,
            ).select_related('gym', 'plan').order_by('end_date')[:4]
        )
        bookings = list(
            Booking.objects.filter(customer=request.user)
            .select_related('gym', 'plan')
            .order_by('-created_at')[:5]
        )
        favorite_qs = Favorite.objects.filter(user=request.user).select_related('gym').order_by('-created_at')[:6]
        favorites = [{'id': item.id, 'gym': _gym(item.gym)} for item in favorite_qs]
        active_visit = (
            GymVisit.objects.filter(customer=request.user, status=GymVisit.Status.ACTIVE)
            .select_related('gym', 'subscription__plan', 'session')
            .first()
        )
        summary = fitness_summary(request.user, activity_days=30)

        # Materialize the limited queryset before using its IDs in another query.
        # Older MySQL/MariaDB versions reject LIMIT inside an IN subquery.
        recommended_gyms = list(
            Gym.objects.filter(status=Gym.Status.APPROVED)
            .annotate(avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)))
            .order_by('-avg_rating', 'starting_price')[:6]
        )
        recommended = []
        recommended_ids = [gym.id for gym in recommended_gyms]
        favorite_ids = set(
            Favorite.objects.filter(user=request.user, gym_id__in=recommended_ids)
            .values_list('gym_id', flat=True)
        ) if recommended_ids else set()
        for gym in recommended_gyms:
            item = _gym(gym)
            item.update({'rating': float(gym.avg_rating or 0), 'is_favorite': gym.id in favorite_ids})
            recommended.append(item)

        return Response({
            'user': _user(request.user),
            'active_visit': _visit(active_visit) if active_visit else None,
            'upcoming_sessions': [_session(request, item) for item in upcoming],
            'active_memberships': [_subscription(request, item) for item in subscriptions],
            'recent_bookings': [_booking(item) for item in bookings],
            'favorites': favorites,
            'recommended': recommended,
            'stats': {
                'bookings': Booking.objects.filter(customer=request.user).count(),
                'pending_bookings': Booking.objects.filter(customer=request.user, status=Booking.Status.PENDING).count(),
                'upcoming_sessions': Session.objects.filter(customer=request.user, status=Session.Status.UPCOMING, start_time__gte=now).count(),
                'active_memberships': GymSubscription.objects.filter(customer=request.user, status=GymSubscription.Status.ACTIVE, end_date__gte=today).count(),
                'favorites': Favorite.objects.filter(user=request.user).count(),
                'reviews': Review.objects.filter(user=request.user).count(),
                'workouts': summary['total_workouts'],
                'minutes': summary['total_minutes'],
                'week_count': summary['week_count'],
                'weekly_target': summary['goal'].weekly_target,
                'streak': summary['streak'],
                'progress_percent': summary['progress_percent'],
            },
        })


class CustomerVisitAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh_due_membership_qrs_for_user(request.user)
        subscriptions = list(
            GymSubscription.objects.filter(customer=request.user)
            .select_related('gym', 'plan')
            .order_by('-end_date')
        )
        active = []
        closed = []
        for item in subscriptions:
            item.mark_expired_if_needed()
            if item.status == GymSubscription.Status.ACTIVE and item.is_active:
                active.append(_subscription(request, item, with_qr=True))
            else:
                closed.append(_subscription(request, item))

        active_visit = (
            GymVisit.objects.filter(customer=request.user, status=GymVisit.Status.ACTIVE)
            .select_related('gym', 'subscription__plan', 'session')
            .first()
        )
        sessions = list(
            Session.objects.filter(customer=request.user)
            .select_related('gym', 'booking__plan')
            .order_by('-start_time')[:20]
        )
        now = timezone.now()
        return Response({
            'active_visit': _visit(active_visit) if active_visit else None,
            'active_memberships': active,
            'closed_memberships': closed,
            'upcoming_sessions': [_session(request, item, with_qr=True) for item in sessions if item.status == Session.Status.UPCOMING and item.start_time >= now],
            'previous_sessions': [_session(request, item) for item in sessions if item.status not in {Session.Status.UPCOMING, Session.Status.CANCELLED}],
            'cancelled_sessions': [_session(request, item) for item in sessions if item.status == Session.Status.CANCELLED],
        })


class CheckoutVisitAPIView(APIView):
    def post(self, request, visit_id):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            visit = GymVisit.objects.select_related('customer', 'gym', 'session').get(id=visit_id, customer=request.user)
        except GymVisit.DoesNotExist:
            return Response({'detail': 'Visit not found.'}, status=status.HTTP_404_NOT_FOUND)
        completed, changed = complete_gym_visit(visit=visit, actor=request.user, request=request)
        return Response({'ok': True, 'changed': changed, 'visit': _visit(completed)})


class RefreshMembershipAPIView(APIView):
    def post(self, request, subscription_id):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            subscription = GymSubscription.objects.select_related('gym', 'plan').get(id=subscription_id, customer=request.user)
        except GymSubscription.DoesNotExist:
            return Response({'detail': 'Membership not found.'}, status=status.HTTP_404_NOT_FOUND)
        subscription.mark_expired_if_needed()
        if not subscription.is_active:
            return Response({'detail': 'This access pass is not active.'}, status=status.HTTP_400_BAD_REQUEST)
        subscription.refresh_qr_if_needed(force=True)
        return Response({'ok': True, 'membership': _subscription(request, subscription, with_qr=True)})


class CancelSessionAPIView(APIView):
    def post(self, request, session_id):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            session = Session.objects.select_related('booking', 'gym').get(id=session_id, customer=request.user)
        except Session.DoesNotExist:
            return Response({'detail': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if session.status != Session.Status.UPCOMING:
            return Response({'detail': 'Only upcoming sessions can be cancelled.'}, status=status.HTTP_400_BAD_REQUEST)
        session.cancel('Cancelled by customer from React app.')
        session.booking.status = Booking.Status.CANCELLED
        session.booking.save(update_fields=['status'])
        return Response({'ok': True})


class CancelBookingAPIView(APIView):
    def post(self, request, booking_id):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            booking = Booking.objects.select_related('gym').get(id=booking_id, customer=request.user)
        except Booking.DoesNotExist:
            return Response({'detail': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)
        if booking.status in {Booking.Status.CANCELLED, Booking.Status.REJECTED}:
            return Response({'detail': 'This booking is already closed.'}, status=status.HTTP_400_BAD_REQUEST)
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status'])
        cancel_operational_records_for_booking(booking, actor=request.user, request=request, reason='Cancelled by customer.')
        return Response({'ok': True})


class ProfileAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        summary = fitness_summary(request.user, activity_days=30)
        favorites = Favorite.objects.filter(user=request.user).select_related('gym').order_by('-created_at')[:10]
        reviews = Review.objects.filter(user=request.user).select_related('gym').order_by('-created_at')[:10]
        bookings = Booking.objects.filter(customer=request.user).select_related('gym', 'plan').order_by('-created_at')[:10]
        return Response({
            'user': _user(request.user),
            'stats': {
                'total_workouts': summary['total_workouts'],
                'week_count': summary['week_count'],
                'weekly_target': summary['goal'].weekly_target,
                'streak': summary['streak'],
                'total_minutes': summary['total_minutes'],
            },
            'favorites': [{'id': item.id, 'gym': _gym(item.gym)} for item in favorites],
            'reviews': [{
                'id': item.id,
                'gym': _gym(item.gym),
                'rating': item.rating,
                'comment': item.comment,
                'created_at': _datetime(item.created_at),
            } for item in reviews],
            'bookings': [_booking(item) for item in bookings],
        })


class CustomerBookingsAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        bookings = (
            Booking.objects.filter(customer=request.user)
            .select_related('gym', 'plan')
            .order_by('-booking_datetime', '-created_at')[:50]
        )
        return Response({'results': [_booking(item) for item in bookings]})


class CustomerFavoritesAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        favorites = (
            Favorite.objects.filter(user=request.user)
            .select_related('gym')
            .order_by('-created_at')[:50]
        )
        return Response({'results': [{'id': item.id, 'gym': _gym(item.gym)} for item in favorites]})


class CustomerNotificationsAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        qs = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:50]
        return Response({
            'unread_count': Notification.objects.filter(recipient=request.user, is_read=False).count(),
            'results': [{
                'id': item.id,
                'kind': item.kind,
                'title': item.title,
                'message': item.message,
                'url': item.url,
                'is_read': item.is_read,
                'created_at': _datetime(item.created_at),
            } for item in qs],
        })


class CustomerNotificationReadAPIView(APIView):
    def post(self, request, notification_id):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            notification = Notification.objects.get(id=notification_id, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({'detail': 'Notification not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response({'ok': True})


class CustomerNotificationsReadAllAPIView(APIView):
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True, 'updated': updated})


class CustomerSettingsAPIView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({'user': _user(request.user)})

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        # Reuse the established Django form rules so React and the legacy UI validate identically.
        form = ProfileUpdateForm(data=request.data, instance=request.user)
        if not form.is_valid():
            errors = {field: [str(message) for message in messages] for field, messages in form.errors.items()}
            return Response({'detail': 'Please correct the highlighted fields.', 'errors': errors}, status=status.HTTP_400_BAD_REQUEST)
        user = form.save()
        log_event(
            level='INFO', category='SYSTEM', event='profile_updated_from_react',
            message='Customer updated profile details from React.', actor=user,
            request=request, related_model='User', related_id=user.id,
        )
        return Response({'ok': True, 'user': _user(user)})


class GymBookingAPIView(APIView):
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            gym = Gym.objects.get(slug=slug, status=Gym.Status.APPROVED)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)

        booking_datetime = normalize_booking_datetime(request.data.get('booking_datetime'))
        if not booking_datetime or booking_datetime <= timezone.now():
            return Response({'detail': 'Choose a future date and time.'}, status=status.HTTP_400_BAD_REQUEST)

        plan = None
        plan_id = request.data.get('plan')
        if plan_id:
            try:
                plan = MembershipPlan.objects.get(id=plan_id, gym=gym)
            except MembershipPlan.DoesNotExist:
                return Response({'detail': 'Selected plan is not available for this gym.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = Booking.objects.create(
                customer=request.user,
                gym=gym,
                booking_datetime=booking_datetime,
                customer_note=str(request.data.get('customer_note', '')).strip(),
                plan=plan,
            )
        except IntegrityError:
            return Response({'detail': 'You already have a booking request for this gym at this time.'}, status=status.HTTP_409_CONFLICT)

        send_booking_created_to_owner(booking, actor=request.user, request=request)
        create_notification_safely(
            request=request,
            recipient=gym.owner,
            sender=request.user,
            kind=Notification.Kind.BOOKING,
            title=f'New booking request for {gym.name}',
            message=f'{request.user.username} requested a visit at {booking.booking_datetime}.',
            url='/dashboard/owner/',
        )
        log_event(level='INFO', category='BOOKING', event='booking_created_from_react', message=f'Booking request for {gym.name}', actor=request.user, request=request, related_model='Booking', related_id=booking.id)
        return Response({'ok': True, 'booking': _booking(booking)}, status=status.HTTP_201_CREATED)


class GymReviewAPIView(APIView):
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            gym = Gym.objects.get(slug=slug, status=Gym.Status.APPROVED)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            rating = int(request.data.get('rating'))
        except (TypeError, ValueError):
            return Response({'detail': 'Choose a rating between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)
        comment = str(request.data.get('comment', '')).strip()
        if rating < 1 or rating > 5:
            return Response({'detail': 'Rating must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(comment) < 10:
            return Response({'detail': 'Please write at least 10 characters.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            review = Review.objects.create(user=request.user, gym=gym, rating=rating, comment=comment)
        except IntegrityError:
            return Response({'detail': 'You already reviewed this gym.'}, status=status.HTTP_409_CONFLICT)
        send_review_notice_to_owner(review, actor=request.user, request=request)
        return Response({
            'ok': True,
            'review': {
                'id': review.id,
                'username': request.user.username,
                'rating': review.rating,
                'comment': review.comment,
                'created_at': _datetime(review.created_at),
            },
        }, status=status.HTTP_201_CREATED)
