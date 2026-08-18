from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.models import GymView
from apps.analytics.demo_seed import (
    DEMO_BOOKING_NOTE, DEMO_CHECKIN_NOTE, DEMO_USERNAME_PREFIX,
    DEMO_WORKOUT_NOTE, reset_realistic_demo_data, seed_realistic_demo_data,
)
from apps.analytics.services import get_gym_analytics, get_owner_portfolio_analytics, normalize_analytics_days
from apps.bookings.models import Booking, GymCheckIn, GymSubscription
from apps.emails.services import send_app_email
from apps.fitness.models import WorkoutLog
from apps.fitness.services import fitness_summary, normalize_activity_days, training_activity_calendar
from apps.gyms.forms import GymImageForm
from apps.gyms.models import Gym, GymImage
from apps.reviews.models import Favorite, Review
from apps.systemlogs.models import SystemLog
from apps.systemlogs.services import log_event

from .permissions import IsOwnerOrStaffAdmin, IsStaffOrPlatformAdmin
from .serializers import DemoAnalyticsSeedRequestSerializer, EmailProbeRequestSerializer, WorkoutLogSerializer

User = get_user_model()


# -----------------------------------------------------------------------------
# Small serialization helpers
# -----------------------------------------------------------------------------

def _decimal(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal('0.01')))
    return str(Decimal(value or 0).quantize(Decimal('0.01')))


def _date(value):
    return value.isoformat() if value else None


def _datetime(value):
    return timezone.localtime(value).isoformat() if value else None


def _user_public(user):
    if not user:
        return None
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'name': user.get_full_name() or user.username,
        'role': getattr(user, 'role', ''),
    }


def _gym_image_url(gym):
    image = getattr(gym, 'cover_image', None)
    if image:
        return image.image_url
    display_images = getattr(gym, 'display_images', None)
    if display_images:
        return display_images[0].image_url
    return ''


def _gym_summary(gym, request=None):
    is_favorite = False
    if request and request.user.is_authenticated:
        is_favorite = Favorite.objects.filter(user=request.user, gym=gym).exists()
    return {
        'id': gym.id,
        'name': gym.name,
        'slug': gym.slug,
        'city': gym.city,
        'address': gym.address,
        'description': gym.description,
        'starting_price': _decimal(gym.starting_price),
        'status': gym.status,
        'status_label': gym.get_status_display(),
        'rating': float(getattr(gym, 'avg_rating', 0) or 0),
        'review_count': getattr(gym, 'review_count', 0) or 0,
        'favorite_count': getattr(gym, 'favorite_count', 0) or Favorite.objects.filter(gym=gym).count(),
        'is_favorite': is_favorite,
        'cover_image': _gym_image_url(gym),
        'detail_url': gym.get_absolute_url(),
        'latitude': str(gym.latitude) if gym.latitude is not None else None,
        'longitude': str(gym.longitude) if gym.longitude is not None else None,
    }


def _booking_summary(booking):
    return {
        'id': booking.id,
        'customer': _user_public(booking.customer),
        'gym': {'id': booking.gym_id, 'name': booking.gym.name, 'slug': booking.gym.slug},
        'plan': {'id': booking.plan_id, 'title': booking.plan.title, 'price': _decimal(booking.plan.price)} if booking.plan else None,
        'status': booking.status,
        'booking_datetime': _datetime(booking.booking_datetime),
        'created_at': _datetime(booking.created_at),
    }


def _checkin_summary(checkin):
    return {
        'id': checkin.id,
        'customer': _user_public(checkin.customer),
        'checked_in_at': _datetime(checkin.checked_in_at),
        'type': getattr(checkin, 'checkin_type', getattr(checkin, 'type', '')),
        'notes': checkin.notes,
    }


def _analytics_payload(metrics):
    gym = metrics['gym']
    return {
        'gym': _gym_summary(gym),
        'range': {
            'days': metrics['days'],
            'start': _date(metrics['start']),
            'end': _date(metrics['end']),
        },
        'totals': {
            'estimated_income': _decimal(metrics['income']['total']),
            'checkins': metrics['total_checkins'],
            'views': metrics['views'],
            'favorites': metrics['favorites'],
            'active_members': metrics['growth']['active_members'],
            'bookings': metrics['conversion']['total'],
            'conversion_rate': metrics['conversion']['rate'],
            'handled_conversion_rate': metrics['conversion']['handled_rate'],
            'peak_label': metrics['peak_label'],
        },
        'income_streams': [
            {
                'key': item['key'],
                'label': item['label'],
                'amount': _decimal(item['amount']),
                'count': item['count'],
                'description': item.get('description', ''),
            }
            for item in metrics['income']['streams']
        ],
        'peak_hours': metrics['peak']['hours'],
        'peak': metrics['peak']['peak'],
        'weekday_traffic': metrics['traffic_days'],
        'growth': {
            'new_members': metrics['growth']['new_members'],
            'previous_new_members': metrics['growth']['previous_new_members'],
            'change_pct': str(metrics['growth']['change_pct'].quantize(Decimal('0.1'))) if metrics['growth']['change_pct'] is not None else None,
            'change_pct_known': metrics['growth']['change_pct_known'],
            'active_members': metrics['growth']['active_members'],
            'trend': metrics['growth']['trend'],
        },
        'conversion': metrics['conversion'],
        'recent_checkins': [_checkin_summary(checkin) for checkin in metrics.get('recent_checkins', [])],
    }


def _resolve_owner_for_admin_or_self(request, owner_username=''):
    if owner_username and (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN'):
        return User.objects.get(username=owner_username)
    return request.user


# -----------------------------------------------------------------------------
# Demo Tools API
# -----------------------------------------------------------------------------

class DemoStatusAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    @extend_schema(
        tags=['Demo Tools'],
        summary='Show demo-tool status and current demo data counts.',
        description=(
            'Admin-only endpoint. Shows whether demo tools are enabled and how much demo analytics data exists. '
            'Use this before running seed/reset operations from Swagger.'
        ),
        responses={200: OpenApiResponse(description='Demo tooling status and counts.')},
    )
    def get(self, request):
        demo_users = User.objects.filter(username__startswith=DEMO_USERNAME_PREFIX)
        demo_user_ids = list(demo_users.values_list('id', flat=True))
        return Response({
            'demo_tools_enabled': bool(getattr(settings, 'DEMO_TOOLS_ENABLED', False)),
            'environment': getattr(settings, 'ENVIRONMENT', 'development'),
            'counts': {
                'demo_customers': demo_users.count(),
                'demo_bookings': Booking.objects.filter(customer_id__in=demo_user_ids, customer_note=DEMO_BOOKING_NOTE).count(),
                'demo_subscriptions': GymSubscription.objects.filter(customer_id__in=demo_user_ids).count(),
                'demo_checkins': GymCheckIn.objects.filter(notes=DEMO_CHECKIN_NOTE).count(),
                'demo_favorites': Favorite.objects.filter(user_id__in=demo_user_ids).count(),
                'demo_workouts': WorkoutLog.objects.filter(user_id__in=demo_user_ids, notes=DEMO_WORKOUT_NOTE).count(),
            },
        })


class DemoSeedAnalyticsAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    @extend_schema(
        tags=['Demo Tools'],
        summary='Seed realistic demo analytics data.',
        description=(
            'Creates demo customers, bookings, subscriptions, QR check-ins, favorites, and workout logs. '
            'The generated traffic is spread across many days and hours so owner analytics charts look realistic. '
            'Requires staff/admin access and DEMO_TOOLS_ENABLED=True. This endpoint is for local/demo environments only.'
        ),
        request=DemoAnalyticsSeedRequestSerializer,
        examples=[OpenApiExample(
            'Balanced 180-day traffic',
            value={
                'days': 180,
                'customers': 80,
                'reset_demo': True,
                'dry_run': False,
                'subscriptions_per_gym': 55,
                'bookings_per_gym': 100,
                'checkins_per_gym': 650,
                'favorites_per_gym': 28,
                'workouts_per_customer': 25,
                'traffic_profile': 'balanced',
                'seed': 9309,
            },
            request_only=True,
        )],
        responses={200: OpenApiResponse(description='Command output and parsed options.'), 403: OpenApiResponse(description='Demo tools disabled.')},
    )
    def post(self, request):
        if not getattr(settings, 'DEMO_TOOLS_ENABLED', False):
            return Response({'detail': 'Demo tools are disabled. Set DEMO_TOOLS_ENABLED=True only on test/demo environments.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = DemoAnalyticsSeedRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        options = {
            'owner_username': data.get('owner_username', ''),
            'customers': data['customers'],
            'days': data['days'],
            'subscriptions_per_gym': data['subscriptions_per_gym'],
            'bookings_per_gym': data['bookings_per_gym'],
            'checkins_per_gym': data['checkins_per_gym'],
            'favorites_per_gym': data['favorites_per_gym'],
            'workouts_per_customer': data['workouts_per_customer'],
            'reset_demo': data.get('reset_demo', True),
            'dry_run': data.get('dry_run', False),
            'seed': data['seed'],
            'traffic_profile': data['traffic_profile'],
        }
        try:
            result = seed_realistic_demo_data(**options)
            payload = result.to_dict()
            log_event(
                level='WARNING',
                category='ADMIN',
                event='demo_analytics_seeded_from_api',
                message='Admin ran realistic demo analytics seeding from Swagger/API.',
                actor=request.user,
                request=request,
                metadata={**data, 'result': payload},
            )
            return Response({'ok': True, 'options': data, 'result': payload})
        except Exception as exc:
            log_event(
                level='ERROR',
                category='ADMIN',
                event='demo_analytics_api_seed_failed',
                message=str(exc),
                actor=request.user,
                request=request,
                metadata=data,
            )
            return Response(
                {'ok': False, 'error': f'{exc.__class__.__name__}: {exc}'},
                status=status.HTTP_400_BAD_REQUEST,
            )



class DemoResetAnalyticsAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    @extend_schema(
        tags=['Demo Tools'],
        summary='Reset only demo analytics data.',
        description=(
            'Deletes only records created by the demo analytics tool. Real users, real owners, and real gyms are not deleted. '
            'Requires staff/admin access and DEMO_TOOLS_ENABLED=True.'
        ),
        responses={200: OpenApiResponse(description='Deleted object counts.')},
    )
    def post(self, request):
        if not getattr(settings, 'DEMO_TOOLS_ENABLED', False):
            return Response({'detail': 'Demo tools are disabled.'}, status=status.HTTP_403_FORBIDDEN)
        deleted_count = reset_realistic_demo_data()
        deleted = {'total_objects': deleted_count}
        log_event(
            level='WARNING',
            category='ADMIN',
            event='demo_analytics_reset_from_api',
            message='Admin reset demo analytics data from Swagger/API.',
            actor=request.user,
            request=request,
            metadata=deleted,
        )
        return Response({'ok': True, 'deleted': deleted})


# -----------------------------------------------------------------------------
# Owner Analytics API
# -----------------------------------------------------------------------------

class OwnerPortfolioAnalyticsAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    @extend_schema(
        tags=['Owner Analytics'],
        summary='Get owner portfolio analytics.',
        description=(
            'Returns multi-gym owner analytics for the selected range: total income, check-ins, active members, bookings, '
            'favorites, top gyms, and per-gym analytics cards. Staff/admin users may pass owner_username to inspect an owner.'
        ),
        parameters=[
            OpenApiParameter('days', int, OpenApiParameter.QUERY, description='Analytics range. Allowed: 7, 30, 90, 120, 360.'),
            OpenApiParameter('owner_username', str, OpenApiParameter.QUERY, description='Admin-only owner username filter.'),
        ],
        responses={200: OpenApiResponse(description='Owner analytics payload.')},
    )
    def get(self, request):
        days = normalize_analytics_days(request.query_params.get('days'), default=30)
        owner_username = request.query_params.get('owner_username', '').strip()
        try:
            owner = _resolve_owner_for_admin_or_self(request, owner_username)
        except User.DoesNotExist:
            return Response({'detail': 'Owner not found.'}, status=status.HTTP_404_NOT_FOUND)
        portfolio = get_owner_portfolio_analytics(owner, days=days)
        return Response({
            'owner': _user_public(owner),
            'range': {'days': days},
            'totals': {
                'gyms': portfolio['totals']['gyms'],
                'estimated_income': _decimal(portfolio['totals']['income']),
                'checkins': portfolio['totals']['checkins'],
                'active_members': portfolio['totals']['active_members'],
                'bookings': portfolio['totals']['bookings'],
                'favorites': portfolio['totals']['favorites'],
            },
            'gyms': [_analytics_payload(item) for item in portfolio['gym_cards']],
            'top_by_checkins': [{'gym_id': item['gym'].id, 'gym_name': item['gym'].name, 'checkins': item['total_checkins'], 'share': item['checkin_share']} for item in portfolio['top_by_checkins']],
            'top_by_income': [{'gym_id': item['gym'].id, 'gym_name': item['gym'].name, 'estimated_income': _decimal(item['income']['total']), 'share': item['income_share']} for item in portfolio['top_by_income']],
        })


class OwnerGymAnalyticsAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    @extend_schema(
        tags=['Owner Analytics'],
        summary='Get analytics for one gym.',
        description=(
            'Returns per-gym owner analytics: peak arrival hours from QR check-ins, weekday traffic, member growth, '
            'estimated income streams, conversion metrics, recent check-ins, views, and favorites.'
        ),
        parameters=[OpenApiParameter('days', int, OpenApiParameter.QUERY, description='Analytics range. Allowed: 7, 30, 90, 120, 360.')],
        responses={200: OpenApiResponse(description='Per-gym analytics payload.')},
    )
    def get(self, request, gym_id):
        days = normalize_analytics_days(request.query_params.get('days'), default=30)
        gym_qs = Gym.objects.select_related('owner')
        if not (request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN'):
            gym_qs = gym_qs.filter(owner=request.user)
        try:
            gym = gym_qs.get(id=gym_id)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found or not accessible.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_analytics_payload(get_gym_analytics(gym, days=days)))


# -----------------------------------------------------------------------------
# Gyms / Favorites API
# -----------------------------------------------------------------------------

class GymListAPIView(APIView):
    permission_classes = []

    @extend_schema(
        tags=['Gyms'],
        summary='Explore approved gyms with backend pagination.',
        description='Returns approved gyms in pages. Default page size is 20, matching the Explore page reliability strategy.',
        parameters=[
            OpenApiParameter('page', int, OpenApiParameter.QUERY, description='Page number, starting at 1.'),
            OpenApiParameter('page_size', int, OpenApiParameter.QUERY, description='Items per page. Max 50.'),
            OpenApiParameter('q', str, OpenApiParameter.QUERY, description='Search in name, description, city, address, and facilities.'),
            OpenApiParameter('city', str, OpenApiParameter.QUERY, description='Exact city filter.'),
            OpenApiParameter('max_price', str, OpenApiParameter.QUERY, description='Maximum starting price.'),
            OpenApiParameter('min_rating', str, OpenApiParameter.QUERY, description='Minimum average rating.'),
            OpenApiParameter('sort', str, OpenApiParameter.QUERY, description='newest, rating, price_asc, price_desc, or name.'),
        ],
    )
    def get(self, request):
        qs = (
            Gym.objects.filter(status=Gym.Status.APPROVED)
            .prefetch_related(
                'facilities',
                Prefetch('images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'),
            )
            .annotate(
                avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)),
                review_count=Count('reviews', filter=Q(reviews__is_visible=True), distinct=True),
                favorite_count=Count('favorited_by', distinct=True),
            )
        )
        q = request.query_params.get('q', '').strip()
        city = request.query_params.get('city', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(city__icontains=q) | Q(address__icontains=q) | Q(facilities__name__icontains=q)).distinct()
        if city:
            qs = qs.filter(city__iexact=city)
        max_price = request.query_params.get('max_price', '').strip()
        if max_price:
            try:
                qs = qs.filter(starting_price__lte=max_price)
            except (TypeError, ValueError):
                return Response({'detail': 'max_price must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        min_rating = request.query_params.get('min_rating', '').strip()
        if min_rating:
            try:
                qs = qs.filter(avg_rating__gte=float(min_rating))
            except (TypeError, ValueError):
                return Response({'detail': 'min_rating must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        sort = request.query_params.get('sort', 'newest')
        sort_options = {
            'newest': '-created_at',
            'rating': '-avg_rating',
            'price_asc': 'starting_price',
            'price_desc': '-starting_price',
            'name': 'name',
        }
        qs = qs.order_by(sort_options.get(sort, '-created_at'), 'name')
        try:
            page_size = min(max(int(request.query_params.get('page_size', 20) or 20), 1), 50)
        except (TypeError, ValueError):
            page_size = 20
        paginator = Paginator(qs, page_size)
        page_number = request.query_params.get('page') or 1
        page = paginator.get_page(page_number)
        return Response({
            'count': paginator.count,
            'page': page.number,
            'page_size': page_size,
            'num_pages': paginator.num_pages,
            'has_next': page.has_next(),
            'has_previous': page.has_previous(),
            'results': [_gym_summary(gym, request) for gym in page.object_list],
        })


class GymDetailAPIView(APIView):
    permission_classes = []

    @extend_schema(tags=['Gyms'], summary='Get one approved gym by slug.')
    def get(self, request, slug):
        try:
            gym = (
                Gym.objects.filter(status=Gym.Status.APPROVED)
                .prefetch_related('facilities', 'plans', 'trainers', 'images')
                .annotate(
                    avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)),
                    review_count=Count('reviews', filter=Q(reviews__is_visible=True), distinct=True),
                    favorite_count=Count('favorited_by', distinct=True),
                )
                .get(slug=slug)
            )
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        payload = _gym_summary(gym, request)
        payload.update({
            'email': gym.email,
            'phone': gym.phone,
            'website': gym.website,
            'facilities': [{'id': item.id, 'name': item.name, 'icon': item.icon} for item in gym.facilities.all()],
            'plans': [{'id': plan.id, 'title': plan.title, 'description': plan.description, 'price': _decimal(plan.price), 'duration_days': plan.duration_days, 'is_trial': plan.is_trial} for plan in gym.plans.all()],
            'images': [{'id': image.id, 'url': image.image_url, 'is_cover': image.is_cover, 'alt_text': image.alt_text} for image in gym.images.all()],
        })
        return Response(payload)


class GymFavoriteAPIView(APIView):
    @extend_schema(tags=['Favorites'], summary='Favorite a gym.', description='Adds the selected gym to the authenticated customer/user favorites.')
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            gym = Gym.objects.get(slug=slug, status=Gym.Status.APPROVED)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        favorite, created = Favorite.objects.get_or_create(user=request.user, gym=gym)
        return Response({'ok': True, 'created': created, 'gym': _gym_summary(gym, request)})

    @extend_schema(tags=['Favorites'], summary='Unfavorite a gym.', description='Removes the selected gym from the authenticated user favorites.')
    def delete(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        deleted = Favorite.objects.filter(user=request.user, gym__slug=slug).delete()[0]
        return Response({'ok': True, 'deleted': deleted})


class GymImageListCreateAPIView(APIView):
    """Owner/admin image upload endpoint backed by ImgBB."""

    @extend_schema(tags=['Gyms'], summary='List gym images or upload a new image to ImgBB.')
    def get(self, request, slug):
        try:
            gym = Gym.objects.prefetch_related('images').get(slug=slug)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'results': [
                {
                    'id': image.id,
                    'url': image.image_url,
                    'is_cover': image.is_cover,
                    'alt_text': image.alt_text,
                    'source': image.source,
                    'width': image.remote_width,
                    'height': image.remote_height,
                    'size': image.remote_size,
                }
                for image in gym.images.all()
                if image.image_url
            ]
        })

    @extend_schema(tags=['Gyms'], summary='Upload a gym image to ImgBB.', description='Multipart form fields: image, alt_text, is_cover.')
    def post(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            gym = Gym.objects.get(slug=slug)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not (request.user.is_staff or getattr(request.user, 'role', '') == 'ADMIN' or gym.owner_id == request.user.id):
            return Response({'detail': 'You can only manage images for your own gym.'}, status=status.HTTP_403_FORBIDDEN)

        form = GymImageForm(request.data, request.FILES)
        if not form.is_valid():
            return Response({'detail': 'Invalid image upload.', 'errors': form.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            image = form.save(commit=False)
        except ValidationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        image.gym = gym
        image.save()
        return Response({
            'id': image.id,
            'url': image.image_url,
            'is_cover': image.is_cover,
            'alt_text': image.alt_text,
            'source': image.source,
            'width': image.remote_width,
            'height': image.remote_height,
            'size': image.remote_size,
        }, status=status.HTTP_201_CREATED)


class GymImageDeleteAPIView(APIView):
    @extend_schema(tags=['Gyms'], summary='Remove an image from a gym.')
    def delete(self, request, slug, image_id):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            gym = Gym.objects.get(slug=slug)
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not (request.user.is_staff or getattr(request.user, 'role', '') == 'ADMIN' or gym.owner_id == request.user.id):
            return Response({'detail': 'You can only manage images for your own gym.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            image = GymImage.objects.get(id=image_id, gym=gym)
        except GymImage.DoesNotExist:
            return Response({'detail': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)

        # ImgBB API v1 documents upload but no authenticated deletion endpoint.
        # We remove the myGym reference and retain no secret cleanup URL in the response.
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# -----------------------------------------------------------------------------
# Fitness API
# -----------------------------------------------------------------------------

class FitnessSummaryAPIView(APIView):
    @extend_schema(
        tags=['Fitness'],
        summary='Get current user fitness summary.',
        parameters=[OpenApiParameter('activity_days', int, OpenApiParameter.QUERY, description='Activity map range: 30, 90, 120, or 360.')],
    )
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        activity_days = normalize_activity_days(request.query_params.get('activity_days'))
        summary = fitness_summary(request.user, activity_days=activity_days)
        return Response({
            'weekly_target': summary['goal'].weekly_target,
            'week_count': summary['week_count'],
            'active_days_this_week': summary['active_days'],
            'total_workouts': summary['total_workouts'],
            'total_minutes': summary['total_minutes'],
            'weekly_streak': summary['streak'],
            'progress_percent': summary['progress_percent'],
            'activity': _activity_payload(summary['activity_calendar']),
        })


class FitnessActivityAPIView(APIView):
    @extend_schema(
        tags=['Fitness'],
        summary='Get current user activity calendar.',
        parameters=[OpenApiParameter('days', int, OpenApiParameter.QUERY, description='Range: 30, 90, 120, or 360.')],
    )
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        days = normalize_activity_days(request.query_params.get('days'))
        return Response(_activity_payload(training_activity_calendar(request.user, days=days)))


class WorkoutLogListCreateAPIView(APIView):
    @extend_schema(tags=['Fitness'], summary='List current user workout logs.')
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        qs = WorkoutLog.objects.filter(user=request.user)[:100]
        return Response({'results': WorkoutLogSerializer(qs, many=True).data})

    @extend_schema(
        tags=['Fitness'],
        summary='Create a workout log for the current user.',
        description='Creates a manual workout log. This updates the Fitness Home weekly summary and activity map.',
        request=WorkoutLogSerializer,
    )
    def post(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = WorkoutLogSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        workout = serializer.save()
        log_event(
            level='INFO',
            category='SYSTEM',
            event='workout_logged_from_api',
            message=f'Workout logged through API: {workout.title}',
            actor=request.user,
            request=request,
            related_model='WorkoutLog',
            related_id=workout.id,
        )
        return Response(WorkoutLogSerializer(workout).data, status=status.HTTP_201_CREATED)


def _activity_payload(activity):
    return {
        'days': activity['days'],
        'today': _date(activity['today']),
        'requested_start': _date(activity['requested_start']),
        'range_workouts': activity['range_workouts'],
        'range_active_days': activity['range_active_days'],
        'total_weeks': activity['total_weeks'],
        'month_labels': activity['month_labels'],
        'cells': [
            {
                'date': _date(cell['date']),
                'count': cell['count'],
                'intensity': cell['intensity'],
                'weekday': cell['weekday'],
                'is_today': cell['is_today'],
                'is_in_range': cell['is_in_range'],
                'is_muted': cell['is_muted'],
            }
            for cell in activity['cells']
        ],
    }


# -----------------------------------------------------------------------------
# Security and Email diagnostics API
# -----------------------------------------------------------------------------

class SecurityStatusAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    @extend_schema(tags=['Security'], summary='Get safe security/deployment status.', description='Admin-only sanitized safety snapshot for deployment/debugging.')
    def get(self, request):
        today = timezone.localdate()
        return Response({
            'environment': getattr(settings, 'ENVIRONMENT', 'development'),
            'debug': settings.DEBUG,
            'allowed_hosts': settings.ALLOWED_HOSTS,
            'csrf_trusted_origins': getattr(settings, 'CSRF_TRUSTED_ORIGINS', []),
            'secure_ssl_redirect': getattr(settings, 'SECURE_SSL_REDIRECT', False),
            'session_cookie_secure': getattr(settings, 'SESSION_COOKIE_SECURE', False),
            'csrf_cookie_secure': getattr(settings, 'CSRF_COOKIE_SECURE', False),
            'demo_tools_enabled': getattr(settings, 'DEMO_TOOLS_ENABLED', False),
            'failed_emails_today': SystemLog.objects.filter(category=SystemLog.Category.EMAIL, level__in=[SystemLog.Level.ERROR, SystemLog.Level.CRITICAL], created_at__date=today).count(),
            'recent_errors': [
                {'id': log.id, 'level': log.level, 'category': log.category, 'event': log.event, 'message': log.message, 'created_at': _datetime(log.created_at)}
                for log in SystemLog.objects.filter(level__in=[SystemLog.Level.ERROR, SystemLog.Level.CRITICAL]).order_by('-created_at')[:10]
            ],
        })


class EmailConfigAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    @extend_schema(tags=['Email Diagnostics'], summary='Show sanitized email configuration.', description='Admin-only. Does not return SMTP password or secrets.')
    def get(self, request):
        return Response({
            'EMAIL_BACKEND': settings.EMAIL_BACKEND,
            'EMAIL_HOST': settings.EMAIL_HOST,
            'EMAIL_PORT': settings.EMAIL_PORT,
            'EMAIL_USE_TLS': settings.EMAIL_USE_TLS,
            'EMAIL_USE_SSL': settings.EMAIL_USE_SSL,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'EMAIL_HOST_PASSWORD': 'SET' if settings.EMAIL_HOST_PASSWORD else 'EMPTY',
            'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
            'SERVER_EMAIL': settings.SERVER_EMAIL,
            'SUPPORT_EMAIL': settings.SUPPORT_EMAIL,
            'SITE_URL': settings.SITE_URL,
        })


class EmailProbeAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    @extend_schema(
        tags=['Email Diagnostics'],
        summary='Send a test myGym email.',
        description='Admin-only diagnostic endpoint. Sends a branded email and logs success/failure through SystemLog.',
        request=EmailProbeRequestSerializer,
        responses={200: OpenApiResponse(description='Email probe result.')},
    )
    def post(self, request):
        serializer = EmailProbeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_email = serializer.validated_data.get('to_email') or request.user.email
        if not to_email:
            return Response({'ok': False, 'detail': 'No recipient email provided and current user has no email.'}, status=status.HTTP_400_BAD_REQUEST)
        subject = serializer.validated_data.get('subject') or 'myGym API email probe'
        try:
            ok = send_app_email(
                to_email,
                subject,
                'welcome',
                {'user': request.user, 'role': 'API email diagnostic recipient'},
                fail_silently=False,
                actor=request.user,
                request=request,
                related_model='User',
                related_id=request.user.id,
            )
            return Response({'ok': bool(ok), 'to_email': to_email, 'backend': settings.EMAIL_BACKEND, 'host': settings.EMAIL_HOST})
        except Exception as exc:
            return Response({'ok': False, 'error': f'{exc.__class__.__name__}: {exc}'}, status=status.HTTP_400_BAD_REQUEST)
