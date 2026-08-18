from django.db.models import Avg, Count, Prefetch, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.services import get_peak_hour_data
from apps.gyms.models import Gym, GymImage
from apps.reviews.models import Favorite


def _money(value):
    return f"{value or 0:.2f}"


def _image_url(image):
    # GymImage.image_url is the storage abstraction. It prefers ImgBB/external
    # storage and falls back to a surviving legacy local image when available.
    try:
        return image.image_url or ''
    except Exception:
        return ''


def _cover_url(gym):
    images = getattr(gym, 'display_images', [])
    for image in images:
        url = _image_url(image)
        if image.is_cover and url:
            return url
    for image in images:
        url = _image_url(image)
        if url:
            return url
    return ''


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
        'favorite_count': int(getattr(gym, 'favorite_count', 0) or 0),
        'is_favorite': bool(
            request.user.is_authenticated
            and Favorite.objects.filter(user=request.user, gym=gym).exists()
        ),
        'cover_image': _cover_url(gym),
        'latitude': str(gym.latitude) if gym.latitude is not None else None,
        'longitude': str(gym.longitude) if gym.longitude is not None else None,
    }


class V1GymDetailAPIView(APIView):
    """UI-oriented gym detail contract used by the React app.

    This intentionally exposes the same traffic source used by the Django
    analytics UI so React and server-rendered pages cannot drift apart.
    """

    permission_classes = []

    def get(self, request, slug):
        try:
            gym = (
                Gym.objects.filter(status=Gym.Status.APPROVED)
                .prefetch_related(
                    'facilities',
                    'plans',
                    'reviews__user',
                    'trainers__user',
                    Prefetch(
                        'images',
                        queryset=GymImage.objects.order_by('-is_cover', 'id'),
                        to_attr='display_images',
                    ),
                )
                .annotate(
                    avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)),
                    review_count=Count(
                        'reviews',
                        filter=Q(reviews__is_visible=True),
                        distinct=True,
                    ),
                    favorite_count=Count('favorited_by', distinct=True),
                )
                .get(slug=slug)
            )
        except Gym.DoesNotExist:
            return Response({'detail': 'Gym not found.'}, status=status.HTTP_404_NOT_FOUND)

        peak = get_peak_hour_data(gym, days=30)
        payload = _gym_card(gym, request)

        payload.update({
            'email': gym.email or '',
            'phone': gym.phone or '',
            'website': gym.website or '',
            'facilities': [
                {'id': item.id, 'name': item.name, 'icon': item.icon}
                for item in gym.facilities.all()
            ],
            'plans': [
                {
                    'id': plan.id,
                    'title': plan.title,
                    'description': plan.description,
                    'price': _money(plan.price),
                    'duration_days': plan.duration_days,
                    'is_trial': plan.is_trial,
                }
                for plan in gym.plans.all()
            ],
            'images': [
                {
                    'id': image.id,
                    'url': url,
                    'is_cover': image.is_cover,
                    'alt_text': image.alt_text,
                }
                for image in getattr(gym, 'display_images', [])
                if (url := _image_url(image))
            ],
            'trainers': [
                {
                    'id': trainer.id,
                    'name': trainer.user.get_full_name() or trainer.user.username,
                    'specialties': [
                        item.strip()
                        for item in (trainer.specialties or '').split(',')
                        if item.strip()
                    ],
                    'bio': trainer.bio or '',
                    'hourly_rate': _money(trainer.hourly_rate) if trainer.hourly_rate is not None else None,
                    'is_available': bool(trainer.is_available),
                }
                for trainer in gym.trainers.all()
            ],
            'reviews': [
                {
                    'id': review.id,
                    'user': review.user.get_full_name() or review.user.username,
                    'rating': review.rating,
                    'comment': review.comment,
                    'created_at': review.created_at.isoformat(),
                    'is_mine': bool(
                        request.user.is_authenticated and review.user_id == request.user.id
                    ),
                }
                for review in gym.reviews.all()
                if review.is_visible
            ],
            'popular_times': {
                'days': 30,
                'hours': peak.get('hours', []),
            },
        })

        return Response(payload)
