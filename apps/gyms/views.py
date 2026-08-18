from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.analytics.models import GymView, SearchLog
from apps.analytics.services import get_peak_hour_data
from apps.reviews.models import Favorite
from .forms import GymForm, GymImageForm, MembershipPlanForm, TrainerProfileForm
from .models import Gym, GymImage, MembershipPlan, TrainerProfile


def owner_required(user):
    return user.is_authenticated and (user.role == 'OWNER' or user.is_staff or user.role == 'ADMIN')


def get_owner_gym_or_403(request, slug):
    gym = get_object_or_404(Gym, slug=slug)
    if not (request.user.is_staff or request.user.role == 'ADMIN' or gym.owner == request.user):
        raise PermissionDenied('You can only manage gyms that belong to you.')
    return gym



def landing(request):
    """Public brand landing page. Search submits into the dedicated Explore marketplace."""
    approved = Gym.objects.filter(status=Gym.Status.APPROVED)
    city_options = (
        approved.exclude(city='')
        .order_by('city')
        .values_list('city', flat=True)
        .distinct()
    )
    return render(request, 'gyms/landing.html', {
        'results_count': approved.count(),
        'city_options': city_options,
    })

def gym_list(request):
    gyms = (
        Gym.objects.filter(status=Gym.Status.APPROVED)
        .prefetch_related(
            'facilities',
            Prefetch('images', queryset=GymImage.objects.order_by('-is_cover', 'id'), to_attr='display_images'),
        )
        .annotate(
            avg_rating=Avg('reviews__rating', filter=Q(reviews__is_visible=True)),
            review_count=Count('reviews', filter=Q(reviews__is_visible=True)),
        )
    )

    query = request.GET.get('q', '').strip()
    city = request.GET.get('city', '').strip()
    max_price = request.GET.get('max_price', '').strip()
    min_rating = request.GET.get('min_rating', '').strip()
    selected_facilities = [fid for fid in request.GET.getlist('facilities') if fid.isdigit()]
    sort = request.GET.get('sort', 'newest').strip()

    if query:
        gyms = gyms.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(city__icontains=query)
            | Q(address__icontains=query)
            | Q(facilities__name__icontains=query)
        ).distinct()
    if city:
        gyms = gyms.filter(city__iexact=city)
    if selected_facilities:
        gyms = gyms.filter(facilities__id__in=selected_facilities).distinct()
    if max_price:
        try:
            gyms = gyms.filter(starting_price__lte=max_price)
        except ValueError:
            messages.warning(request, 'Max price must be a number.')
    if min_rating:
        try:
            gyms = gyms.filter(avg_rating__gte=float(min_rating))
        except ValueError:
            messages.warning(request, 'Minimum rating must be a number.')

    sort_options = {
        'newest': '-created_at',
        'rating': '-avg_rating',
        'price_asc': 'starting_price',
        'price_desc': '-starting_price',
        'name': 'name',
    }
    if sort not in sort_options:
        sort = 'newest'
    gyms = gyms.order_by(sort_options[sort], 'name')

    if query or city:
        SearchLog.objects.create(user=request.user if request.user.is_authenticated else None, query=query, city=city)

    view_mode = request.GET.get('view', 'cards')
    if view_mode not in ['cards', 'map']:
        view_mode = 'cards'

    filter_params = request.GET.copy()
    filter_params.pop('view', None)
    filter_query_string = filter_params.urlencode()

    facility_options = Gym.facilities.field.remote_field.model.objects.order_by('name')
    city_options = (
        Gym.objects.filter(status=Gym.Status.APPROVED)
        .exclude(city='')
        .order_by('city')
        .values_list('city', flat=True)
        .distinct()
    )

    total_results = gyms.count()
    paginator = Paginator(gyms, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    gym_list_items = list(page_obj.object_list)

    page_params = request.GET.copy()
    page_params.pop('page', None)
    page_query_string = page_params.urlencode()

    map_gyms = []
    for gym in gym_list_items:
        if gym.latitude is not None and gym.longitude is not None:
            map_gyms.append({
                'name': gym.name,
                'city': gym.city,
                'price': str(gym.starting_price),
                'url': request.build_absolute_uri(gym.get_absolute_url()) if hasattr(gym, 'get_absolute_url') else f'/gyms/{gym.slug}/',
                'lat': float(gym.latitude),
                'lng': float(gym.longitude),
            })

    favorite_ids = set()
    if request.user.is_authenticated:
        favorite_ids = set(Favorite.objects.filter(user=request.user, gym__in=gym_list_items).values_list('gym_id', flat=True))

    return render(request, 'gyms/gym_list.html', {
        'gyms': gym_list_items,
        'page_obj': page_obj,
        'paginator': paginator,
        'results_count': total_results,
        'page_query_string': page_query_string,
        'favorite_ids': favorite_ids,
        'map_gyms': map_gyms,
        'query': query,
        'city': city,
        'max_price': max_price,
        'min_rating': min_rating,
        'selected_facilities': selected_facilities,
        'sort': sort,
        'facility_options': facility_options,
        'city_options': city_options,
        'filter_query_string': filter_query_string,
        'view_mode': view_mode,
    })


@login_required(login_url='login')
def gym_detail(request, slug):
    gym = get_object_or_404(
        Gym.objects.prefetch_related('facilities', 'plans', 'trainers', 'images', 'reviews'),
        slug=slug,
        status=Gym.Status.APPROVED,
    )
    if not request.session.session_key:
        request.session.create()
    already_counted_today = GymView.objects.filter(
        gym=gym,
        session_key=request.session.session_key or '',
        created_at__date=timezone.localdate(),
    ).exists()
    if not already_counted_today:
        GymView.objects.create(
            gym=gym,
            user=request.user if request.user.is_authenticated else None,
            session_key=request.session.session_key or '',
            ip_address=request.META.get('REMOTE_ADDR'),
        )
    is_favorited = Favorite.objects.filter(user=request.user, gym=gym).exists()
    public_peak_hours = get_peak_hour_data(gym, days=30)
    return render(request, 'gyms/gym_detail.html', {
        'gym': gym,
        'is_favorited': is_favorited,
        'public_peak_hours': public_peak_hours,
        'public_peak_days': 30,
    })


@login_required
def owner_gym_create(request):
    if not owner_required(request.user):
        raise PermissionDenied('Only gym owners can create gyms.')
    if request.method == 'POST':
        form = GymForm(request.POST)
        if form.is_valid():
            gym = form.save(commit=False)
            gym.owner = request.user
            gym.status = Gym.Status.PENDING
            gym.save()
            form.save_m2m()
            messages.success(request, 'Gym created and submitted for admin approval.')
            return redirect('owner_gym_manage', slug=gym.slug)
    else:
        form = GymForm()
    return render(request, 'gyms/owner_gym_form.html', {'form': form, 'title': 'Add new gym'})


@login_required
def owner_gym_edit(request, slug):
    gym = get_owner_gym_or_403(request, slug)
    if request.method == 'POST':
        form = GymForm(request.POST, instance=gym)
        if form.is_valid():
            gym = form.save(commit=False)
            # Keep already-approved gyms visible after simple owner edits like lat/lng or photos.
            # New gyms still start as PENDING in owner_gym_create. Admin can still reject/remove listings.
            gym.save()
            form.save_m2m()
            messages.success(request, 'Gym updated successfully.')
            return redirect('owner_gym_manage', slug=gym.slug)
    else:
        form = GymForm(instance=gym)
    return render(request, 'gyms/owner_gym_form.html', {'form': form, 'gym': gym, 'title': f'Edit {gym.name}'})


@login_required
def owner_gym_manage(request, slug):
    gym = get_owner_gym_or_403(request, slug)
    return render(request, 'gyms/owner_gym_manage.html', {
        'gym': gym,
        'plan_form': MembershipPlanForm(),
        'trainer_form': TrainerProfileForm(),
        'image_form': GymImageForm(),
    })


@login_required
def owner_plan_add(request, slug):
    gym = get_owner_gym_or_403(request, slug)
    if request.method == 'POST':
        form = MembershipPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.gym = gym
            plan.save()
            messages.success(request, 'Membership plan added.')
    return redirect('owner_gym_manage', slug=gym.slug)


@login_required
def owner_plan_delete(request, slug, plan_id):
    gym = get_owner_gym_or_403(request, slug)
    plan = get_object_or_404(MembershipPlan, id=plan_id, gym=gym)
    if request.method == 'POST':
        plan.delete()
        messages.success(request, 'Membership plan deleted.')
    return redirect('owner_gym_manage', slug=gym.slug)


@login_required
def owner_trainer_add(request, slug):
    gym = get_owner_gym_or_403(request, slug)
    if request.method == 'POST':
        form = TrainerProfileForm(request.POST)
        if form.is_valid():
            trainer = form.save(commit=False)
            trainer.gym = gym
            trainer.save()
            messages.success(request, 'Trainer added to gym.')
        else:
            messages.error(request, 'Trainer could not be added. Make sure the selected user is not already attached to another trainer profile.')
    return redirect('owner_gym_manage', slug=gym.slug)


@login_required
def owner_trainer_delete(request, slug, trainer_id):
    gym = get_owner_gym_or_403(request, slug)
    trainer = get_object_or_404(TrainerProfile, id=trainer_id, gym=gym)
    if request.method == 'POST':
        trainer.delete()
        messages.success(request, 'Trainer removed from gym.')
    return redirect('owner_gym_manage', slug=gym.slug)


@login_required
def owner_image_add(request, slug):
    gym = get_owner_gym_or_403(request, slug)
    if request.method == 'POST':
        form = GymImageForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                image = form.save(commit=False)
                image.gym = gym
                image.save()
                messages.success(request, 'Photo uploaded to external image hosting.')
            except ValidationError as exc:
                messages.error(request, f'Photo upload failed: {exc}')
        else:
            messages.error(request, 'Photo upload failed. ' + ' '.join(form.errors.get('image', [])))
    return redirect('owner_gym_manage', slug=gym.slug)


@login_required
def owner_image_delete(request, slug, image_id):
    gym = get_owner_gym_or_403(request, slug)
    image = get_object_or_404(GymImage, id=image_id, gym=gym)
    if request.method == 'POST':
        image.delete()
        messages.success(request, 'Photo deleted.')
    return redirect('owner_gym_manage', slug=gym.slug)
