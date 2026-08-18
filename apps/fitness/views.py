from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.bookings.models import Booking, GymSubscription, GymVisit, Session
from apps.bookings.services import attach_membership_qr, refresh_due_membership_qrs_for_user
from apps.gyms.models import Gym
from apps.reviews.models import Favorite, Review
from apps.systemlogs.services import log_event

from .forms import ProfileUpdateForm, WorkoutGoalForm, WorkoutLogForm
from .models import WorkoutLog
from .services import fitness_summary, get_or_create_goal, normalize_activity_days


@login_required
def fitness_home(request):
    """Customer-first Home screen for v0.9.3 Fitness Home Rebase."""
    if getattr(request.user, 'role', '') == 'OWNER':
        return redirect('owner_dashboard')
    if request.user.is_staff or request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN':
        return redirect('control_overview')

    refresh_due_membership_qrs_for_user(request.user)
    activity_days = normalize_activity_days(request.GET.get('activity_days'))
    summary = fitness_summary(request.user, activity_days=activity_days)

    upcoming_session = (
        Session.objects
        .filter(customer=request.user, status=Session.Status.UPCOMING, start_time__gte=timezone.now())
        .select_related('gym', 'booking', 'booking__plan')
        .order_by('start_time')
        .first()
    )
    active_subscription = (
        GymSubscription.objects
        .filter(customer=request.user, status=GymSubscription.Status.ACTIVE, end_date__gte=timezone.localdate())
        .select_related('gym', 'plan')
        .order_by('end_date')
        .first()
    )
    if active_subscription:
        attach_membership_qr(request, active_subscription)

    active_visit = (
        GymVisit.objects
        .filter(customer=request.user, status=GymVisit.Status.ACTIVE)
        .select_related('gym', 'subscription__plan', 'session')
        .first()
    )

    recent_workouts = WorkoutLog.objects.filter(user=request.user)[:5]
    favorite_gyms = Favorite.objects.filter(user=request.user).select_related('gym')[:4]
    recommended_gyms = (
        Gym.objects
        .filter(status=Gym.Status.APPROVED)
        .annotate(review_count=Count('reviews', distinct=True))
        .prefetch_related('images')[:4]
    )
    recent_bookings = Booking.objects.filter(customer=request.user).select_related('gym', 'plan')[:4]

    return render(request, 'fitness/home.html', {
        'summary': summary,
        'upcoming_session': upcoming_session,
        'active_subscription': active_subscription,
        'active_visit': active_visit,
        'recent_workouts': recent_workouts,
        'favorite_gyms': favorite_gyms,
        'recommended_gyms': recommended_gyms,
        'recent_bookings': recent_bookings,
    })


@login_required
def log_workout(request):
    if request.method == 'POST':
        form = WorkoutLogForm(request.POST)
        if form.is_valid():
            workout = form.save(commit=False)
            workout.user = request.user
            workout.source = WorkoutLog.Source.MANUAL
            workout.save()
            log_event(
                level='INFO',
                category='SYSTEM',
                event='workout_logged',
                message=f'Workout logged: {workout.title}',
                actor=request.user,
                request=request,
                related_model='WorkoutLog',
                related_id=workout.id,
            )
            messages.success(request, 'Workout logged. Your weekly progress is updated.')
            return redirect('fitness_home')
    else:
        form = WorkoutLogForm(initial={'logged_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M')})

    return render(request, 'fitness/log_workout.html', {'form': form})


@login_required
def workout_history(request):
    workouts = WorkoutLog.objects.filter(user=request.user)[:50]
    activity_days = normalize_activity_days(request.GET.get('activity_days'))
    summary = fitness_summary(request.user, activity_days=activity_days)
    return render(request, 'fitness/history.html', {'workouts': workouts, 'summary': summary})


@login_required
def update_goal(request):
    goal = get_or_create_goal(request.user)
    if request.method == 'POST':
        form = WorkoutGoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, 'Weekly workout goal updated.')
            return redirect('fitness_home')
    else:
        form = WorkoutGoalForm(instance=goal)
    return render(request, 'fitness/update_goal.html', {'form': form, 'goal': goal})


@login_required
def discover(request):
    gyms = Gym.objects.filter(status=Gym.Status.APPROVED).prefetch_related('images')[:6]
    sample_posts = [
        {'actor': 'myGym Team', 'title': 'Discover is warming up', 'body': 'Soon you will see gym posts, workout stories, challenges, and videos here.', 'tag': 'Product Preview'},
        {'actor': 'Owners', 'title': 'Gym announcements', 'body': 'Owners will be able to share classes, offers, trainer intros, and community updates.', 'tag': 'Owner Content'},
        {'actor': 'Friends', 'title': 'Social fitness home', 'body': 'Friend activity, streaks, encouragement, and progress updates will arrive after the feed MVP.', 'tag': 'Social Layer'},
    ]
    return render(request, 'fitness/discover.html', {'gyms': gyms, 'sample_posts': sample_posts})


@login_required
def chat_home(request):
    return render(request, 'fitness/chat.html')


@login_required
def more_menu(request):
    return render(request, 'fitness/more.html')


@login_required
def edit_profile(request):
    form = ProfileUpdateForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Account details updated.')
        return redirect('profile_hub')
    return render(request, 'fitness/edit_profile.html', {'form': form})


@login_required
def profile_hub(request):
    refresh_due_membership_qrs_for_user(request.user)
    activity_days = normalize_activity_days(request.GET.get('activity_days'))
    summary = fitness_summary(request.user, activity_days=activity_days)
    sessions = Session.objects.filter(customer=request.user).select_related('gym')[:5]
    subscriptions = GymSubscription.objects.filter(customer=request.user).select_related('gym', 'plan')[:5]
    bookings = Booking.objects.filter(customer=request.user).select_related('gym', 'plan')[:5]
    reviews = Review.objects.filter(user=request.user).select_related('gym')[:5]
    favorites = Favorite.objects.filter(user=request.user).select_related('gym')[:5]
    return render(request, 'fitness/profile.html', {
        'summary': summary,
        'sessions': sessions,
        'subscriptions': subscriptions,
        'bookings': bookings,
        'reviews': reviews,
        'favorites': favorites,
    })
