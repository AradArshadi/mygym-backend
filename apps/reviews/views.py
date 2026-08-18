from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect
from apps.gyms.models import Gym
from .models import Favorite, Review
from apps.emails.services import send_review_notice_to_owner
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_safely
from apps.systemlogs.services import log_event


@login_required
def create_review(request, gym_id):
    gym = get_object_or_404(Gym, id=gym_id, status=Gym.Status.APPROVED)
    if request.method != 'POST':
        return redirect('gym_detail', slug=gym.slug)

    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '').strip()

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        messages.error(request, 'Please choose a valid rating.')
        return redirect('gym_detail', slug=gym.slug)

    if rating < 1 or rating > 5:
        messages.error(request, 'Rating must be between 1 and 5.')
        return redirect('gym_detail', slug=gym.slug)

    if len(comment) < 10:
        messages.error(request, 'Please write at least 10 characters for your review.')
        return redirect('gym_detail', slug=gym.slug)

    try:
        review = Review.objects.create(user=request.user, gym=gym, rating=rating, comment=comment)
    except IntegrityError:
        messages.error(request, 'You already reviewed this gym.')
        return redirect('gym_detail', slug=gym.slug)

    create_notification_safely(
        request=request,
        recipient=gym.owner,
        sender=request.user,
        kind=Notification.Kind.REVIEW,
        title=f'New review for {gym.name}',
        message=f'{request.user.username} left a {rating}/5 review.',
        url=f'/gyms/{gym.slug}/',
    )

    send_review_notice_to_owner(review, actor=request.user, request=request)
    log_event(level='INFO', category='REVIEW', event='review_created', message=f'{request.user.username} reviewed {gym.name}', actor=request.user, request=request, related_model='Review', related_id=review.id, metadata={'rating': rating})

    messages.success(request, 'Review submitted. Thanks for helping other customers!')
    return redirect('gym_detail', slug=gym.slug)


@login_required
def toggle_favorite(request, gym_id):
    gym = get_object_or_404(Gym, id=gym_id, status=Gym.Status.APPROVED)
    if request.method != 'POST':
        return redirect('gym_detail', slug=gym.slug)
    favorite, created = Favorite.objects.get_or_create(user=request.user, gym=gym)
    if created:
        messages.success(request, f'{gym.name} was added to your favorite gyms.')
        log_event(level='INFO', category='SYSTEM', event='favorite_created', message=f'{request.user.username} favorited {gym.name}', actor=request.user, request=request, related_model='Favorite', related_id=favorite.id)
    else:
        favorite.delete()
        messages.info(request, f'{gym.name} was removed from your favorite gyms.')
        log_event(level='INFO', category='SYSTEM', event='favorite_removed', message=f'{request.user.username} removed favorite {gym.name}', actor=request.user, request=request, related_model='Gym', related_id=gym.id)
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('gym_detail', slug=gym.slug)
