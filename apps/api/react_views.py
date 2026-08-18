from datetime import datetime
from decimal import Decimal

from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.services import get_peak_hour_data
from apps.bookings.models import Booking, GymSubscription, GymVisit, Session
from apps.fitness.models import WorkoutGoal, WorkoutLog
from apps.gyms.models import Facility, Gym, GymImage
from apps.reviews.models import Favorite


def _money(value):
    return str(Decimal(value or 0).quantize(Decimal('0.01')))


def _dt(value):
    return timezone.localtime(value).isoformat() if value else None


def _user(user):
    if not user or not user.is_authenticated:
        return None
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'name': user.get_full_name() or user.username,
        'role': getattr(user, 'role', ''),
        'is_staff': bool(user.is_staff),
        'is_superuser': bool(user.is_superuser),
    }


def _cover_url(gym):
    images = getattr(gym, 'display_images', None)
    if images:
        for image in images:
            if image.is_cover:
                return image.image_url
        return images[0].image_url
    cover = gym.cover_image
    return cover.image_url if cover else ''


def _gym_card(gym, request):
    return {
        'id': gym.id,
        'name': gym.name,
        'slug': gym.slug,
        'city': gym.city,
        'address': gym.address,
        'description': gym.description,
        'starting_price': _money(gym.starting_price),
        'rating': float(getattr(gym, 'avg_rating', 0) or 0),
        'review_count': int(getattr(gym, 'review_count', 0) or 0),
        'cover_image': _cover_url(gym),
        'facilities': [{'id': f.id, 'name': f.name, 'icon': f.icon} for f in gym.facilities.all()],
        'is_favorite': bool(request.user.is_authenticated and Favorite.objects.filter(user=request.user, gym=gym).exists()),
        'latitude': str(gym.latitude) if gym.latitude is not None else None,
        'longitude': str(gym.longitude) if gym.longitude is not None else None,
    }


class CsrfAPIView(APIView):
    permission_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({'csrfToken': get_token(request)})


@method_decorator(csrf_protect, name='dispatch')
class LoginAPIView(APIView):
    permission_classes = []

    def post(self, request):
        username = str(request.data.get('username', '')).strip()
        password = str(request.data.get('password', ''))
        if not username or not password:
            return Response({'detail': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({'detail': 'Invalid username or password.'}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response({'user': _user(user)})


class LogoutAPIView(APIView):
    def post(self, request):
        logout(request)
        return Response({'ok': True})


class MeAPIView(APIView):
    permission_classes = []

    def get(self, request):
        return Response({'user': _user(request.user)})


class ReactDashboardAPIView(APIView):
    """One UI-oriented endpoint for the customer Home screen."""

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        now = timezone.now()
        today = timezone.localdate()
        week_start = today - timezone.timedelta(days=today.weekday())
        week_start_dt = timezone.make_aware(datetime.combine(week_start, datetime.min.time()), timezone.get_current_timezone())

        next_session = (
            Session.objects.filter(customer=request.user, status=Session.Status.UPCOMING, start_time__gte=now)
            .select_related('gym')
            .prefetch_related(Prefetch('gym__images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'))
            .order_by('start_time')
            .first()
        )
        membership = (
            GymSubscription.objects.filter(customer=request.user, status=GymSubscription.Status.ACTIVE, end_date__gte=today)
            .select_related('gym', 'plan')
            .prefetch_related(Prefetch('gym__images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'))
            .order_by('end_date')
            .first()
        )
        active_visit = (
            GymVisit.objects.filter(customer=request.user, status=GymVisit.Status.ACTIVE)
            .select_related('gym')
            .first()
        )
        workouts_this_week = WorkoutLog.objects.filter(user=request.user, logged_at__gte=week_start_dt)
        minutes_this_week = workouts_this_week.aggregate(total=Sum('duration_minutes'))['total'] or 0
        weekly_target = getattr(WorkoutGoal.objects.filter(user=request.user).first(), 'weekly_target', 3) or 3
        workout_count = workouts_this_week.count()
        goal_percent = min(100, round((workout_count / weekly_target) * 100)) if weekly_target else 0

        recommended_qs = (
            Gym.objects.filter(status=Gym.Status.APPROVED)
            .prefetch_related('facilities', Prefetch('images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'))
            .annotate(
                avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)),
                review_count=Count('reviews', filter=Q(reviews__is_visible=True), distinct=True),
                favorite_count=Count('favorited_by', distinct=True),
            )
            .order_by('-avg_rating', '-favorite_count', '-created_at')[:6]
        )

        return Response({
            'user': _user(request.user),
            'next_session': {
                'id': next_session.id,
                'gym': {'name': next_session.gym.name, 'slug': next_session.gym.slug, 'cover_image': _cover_url(next_session.gym)},
                'start_time': _dt(next_session.start_time),
                'status': next_session.status,
            } if next_session else None,
            'membership': {
                'id': membership.id,
                'gym': {'name': membership.gym.name, 'slug': membership.gym.slug, 'cover_image': _cover_url(membership.gym)},
                'plan': membership.plan.title if membership.plan else 'Membership',
                'end_date': membership.end_date.isoformat(),
                'days_remaining': membership.days_remaining,
            } if membership else None,
            'active_visit': {
                'id': active_visit.id,
                'gym': {'name': active_visit.gym.name, 'slug': active_visit.gym.slug},
                'checked_in_at': _dt(active_visit.checked_in_at),
                'duration_minutes': active_visit.duration_minutes,
            } if active_visit else None,
            'activity': {
                'workouts_this_week': workout_count,
                'minutes_this_week': minutes_this_week,
                'weekly_target': weekly_target,
                'goal_percent': goal_percent,
            },
            'stats': {
                'bookings': Booking.objects.filter(customer=request.user).count(),
                'favorites': Favorite.objects.filter(user=request.user).count(),
                'reviews': request.user.reviews.count() if hasattr(request.user, 'reviews') else 0,
            },
            'recommended': [_gym_card(gym, request) for gym in recommended_qs],
        })


class ReactGymListAPIView(APIView):
    permission_classes = []

    def get(self, request):
        qs = (
            Gym.objects.filter(status=Gym.Status.APPROVED)
            .prefetch_related('facilities', Prefetch('images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'))
            .annotate(
                avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)),
                review_count=Count('reviews', filter=Q(reviews__is_visible=True), distinct=True),
            )
        )
        q = request.query_params.get('q', '').strip()
        city = request.query_params.get('city', '').strip()
        max_price = request.query_params.get('max_price', '').strip()
        min_rating = request.query_params.get('min_rating', '').strip()
        sort = request.query_params.get('sort', 'newest').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(city__icontains=q) | Q(address__icontains=q) | Q(facilities__name__icontains=q)).distinct()
        if city:
            qs = qs.filter(city__iexact=city)
        if max_price:
            try:
                qs = qs.filter(starting_price__lte=Decimal(max_price))
            except Exception:
                return Response({'detail': 'Maximum price must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        if min_rating:
            try:
                qs = qs.filter(avg_rating__gte=float(min_rating))
            except Exception:
                return Response({'detail': 'Minimum rating must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        sort_options = {'newest': '-created_at', 'rating': '-avg_rating', 'price_asc': 'starting_price', 'price_desc': '-starting_price', 'name': 'name'}
        qs = qs.order_by(sort_options.get(sort, '-created_at'), 'name')
        try:
            page_size = min(max(int(request.query_params.get('page_size', 20)), 1), 50)
        except Exception:
            page_size = 20
        paginator = Paginator(qs, page_size)
        page = paginator.get_page(request.query_params.get('page') or 1)
        approved = Gym.objects.filter(status=Gym.Status.APPROVED)
        return Response({
            'count': paginator.count,
            'page': page.number,
            'page_size': page_size,
            'num_pages': paginator.num_pages,
            'has_next': page.has_next(),
            'has_previous': page.has_previous(),
            'results': [_gym_card(gym, request) for gym in page.object_list],
            'filters': {
                'cities': list(approved.exclude(city='').order_by('city').values_list('city', flat=True).distinct()),
                'facilities': list(Facility.objects.order_by('name').values('id', 'name', 'icon')),
            },
        })


class ReactGymDetailAPIView(APIView):
    permission_classes = []

    def get(self, request, slug):
        try:
            gym = (
                Gym.objects.filter(status=Gym.Status.APPROVED)
                .prefetch_related('facilities', 'plans', 'reviews__user', 'trainers__user', Prefetch('images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'))
                .annotate(avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)), review_count=Count('reviews', filter=Q(reviews__is_visible=True), distinct=True))
                .get(slug=slug)
            )
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        peak = get_peak_hour_data(gym, days=30)
        payload = _gym_card(gym, request)
        payload.update({
            'email': gym.email,
            'phone': gym.phone,
            'website': gym.website,
            'images': [{'id': image.id, 'url': image.image_url, 'is_cover': image.is_cover, 'alt_text': image.alt_text} for image in getattr(gym, 'display_images', []) if image.image_url],
            'plans': [{'id': plan.id, 'title': plan.title, 'description': plan.description, 'price': _money(plan.price), 'duration_days': plan.duration_days, 'is_trial': plan.is_trial} for plan in gym.plans.all()],
            'trainers': [{'id': trainer.id, 'name': trainer.user.get_full_name() or trainer.user.username, 'bio': trainer.bio, 'specialties': [x.strip() for x in trainer.specialties.split(',') if x.strip()], 'hourly_rate': _money(trainer.hourly_rate) if trainer.hourly_rate is not None else None, 'is_available': trainer.is_available} for trainer in gym.trainers.all()],
            'reviews': [{'id': review.id, 'rating': review.rating, 'comment': review.comment, 'created_at': _dt(review.created_at), 'user': review.user.get_full_name() or review.user.username, 'is_mine': bool(request.user.is_authenticated and review.user_id == request.user.id)} for review in gym.reviews.all() if review.is_visible],
            'popular_times': {'days': 30, 'hours': peak['hours']},
        })
        return Response(payload)


class ReactGymFavoriteAPIView(APIView):
    def post(self, request, slug):
        gym = Gym.objects.filter(slug=slug, status=Gym.Status.APPROVED).first()
        if not gym:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        Favorite.objects.get_or_create(user=request.user, gym=gym)
        return Response({'is_favorite': True})

    def delete(self, request, slug):
        Favorite.objects.filter(user=request.user, gym__slug=slug).delete()
        return Response({'is_favorite': False})


class ReactBookingAPIView(APIView):
    def post(self, request, slug):
        gym = Gym.objects.filter(slug=slug, status=Gym.Status.APPROVED).first()
        if not gym:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        raw_dt = str(request.data.get('booking_datetime', '')).strip()
        if not raw_dt:
            return Response({'detail': 'Choose a date and time.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            parsed = datetime.fromisoformat(raw_dt.replace('Z', '+00:00'))
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        except Exception:
            return Response({'detail': 'That date and time is not valid.'}, status=status.HTTP_400_BAD_REQUEST)
        if parsed <= timezone.now():
            return Response({'detail': 'Choose a future time.'}, status=status.HTTP_400_BAD_REQUEST)
        plan = None
        plan_id = request.data.get('plan')
        if plan_id:
            plan = gym.plans.filter(id=plan_id).first()
            if not plan:
                return Response({'detail': 'That plan is not available for this gym.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            booking = Booking.objects.create(customer=request.user, gym=gym, plan=plan, booking_datetime=parsed, customer_note=str(request.data.get('customer_note', '')).strip())
        except IntegrityError:
            return Response({'detail': 'You already have a booking at that time.'}, status=status.HTTP_409_CONFLICT)
        return Response({'booking_id': booking.id, 'status': booking.status}, status=status.HTTP_201_CREATED)
