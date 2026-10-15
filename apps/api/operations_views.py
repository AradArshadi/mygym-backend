"""JSON operations for the React owner workspace and Control Deck.

All mutations are scoped on the server. Existing forms and booking services
remain the source of validation and operational side effects.
"""
from uuid import UUID
from datetime import timedelta

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.bookings.models import Booking, GymCheckIn, GymSubscription, GymVisit, Session
from apps.bookings.services import (
    attach_membership_qr, attach_session_qr, cancel_operational_records_for_booking,
    complete_gym_visit, create_operational_records_for_confirmed_booking, start_gym_visit,
)
from apps.controlpanel.views import _base_metrics, _security_check_rows
from apps.emails.services import (
    send_booking_status_to_customer, send_gym_status_to_owner,
    send_membership_access_pass_to_customer, send_session_qr_to_customer,
)
from apps.gyms.forms import GymForm, MembershipPlanForm, TrainerProfileForm
from apps.gyms.models import Facility, Gym, MembershipPlan, TrainerProfile
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_safely
from apps.reviews.models import Review
from apps.systemlogs.models import SystemLog
from apps.systemlogs.services import log_event
from .permissions import IsOwnerOrStaffAdmin, IsStaffOrPlatformAdmin


def is_admin(user):
    return user.is_staff or user.is_superuser or user.role == User.Role.ADMIN


def gym_scope(user):
    qs = Gym.objects.select_related('owner')
    return qs if is_admin(user) else qs.filter(owner=user)


def person(user):
    return {'id': user.id, 'name': user.get_full_name() or user.username,
            'username': user.username, 'email': user.email, 'role': user.role,
            'is_active': user.is_active, 'is_staff': user.is_staff, 'is_superuser': user.is_superuser}


def gym_data(gym):
    return {
        'id': gym.id, 'owner': person(gym.owner), 'name': gym.name, 'slug': gym.slug,
        'description': gym.description, 'city': gym.city, 'address': gym.address,
        'email': gym.email, 'phone': gym.phone, 'website': gym.website,
        'latitude': str(gym.latitude) if gym.latitude is not None else '',
        'longitude': str(gym.longitude) if gym.longitude is not None else '',
        'starting_price': str(gym.starting_price), 'status': gym.status,
        'facilities': list(gym.facilities.values_list('id', flat=True)),
    }


def booking_data(item):
    return {'id': item.id, 'customer': person(item.customer),
            'gym': {'id': item.gym_id, 'name': item.gym.name}, 'status': item.status,
            'plan': item.plan.title if item.plan else None,
            'booking_datetime': item.booking_datetime.isoformat(), 'customer_note': item.customer_note}


def paginate(request, qs, serialize):
    page = Paginator(qs, 20).get_page(request.query_params.get('page', 1))
    return {'results': [serialize(item) for item in page], 'count': page.paginator.count,
            'page': page.number, 'num_pages': page.paginator.num_pages}


def save_form(form, **attributes):
    if not form.is_valid():
        raise ValidationError({key: list(value) for key, value in form.errors.items()})
    obj = form.save(commit=False)
    for key, value in attributes.items():
        setattr(obj, key, value)
    obj.save()
    if hasattr(form, 'save_m2m'):
        form.save_m2m()
    return obj


class BookingActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=['confirm', 'reject', 'cancel'])


class BookingActionAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    def post(self, request, booking_id):
        data = BookingActionInput(data=request.data)
        data.is_valid(raise_exception=True)
        target = {'confirm': Booking.Status.CONFIRMED, 'reject': Booking.Status.REJECTED,
                  'cancel': Booking.Status.CANCELLED}[data.validated_data['action']]
        with transaction.atomic():
            qs = Booking.objects.select_for_update().select_related('gym__owner', 'customer', 'plan')
            if not is_admin(request.user):
                qs = qs.filter(gym__owner=request.user)
            booking = get_object_or_404(qs, pk=booking_id)
            if booking.status == target:
                return Response({'ok': True, 'booking': booking_data(booking), 'changed': False})
            if booking.status in {Booking.Status.CANCELLED, Booking.Status.REJECTED}:
                raise ValidationError('Closed bookings cannot be reopened.')
            if booking.status == Booking.Status.CONFIRMED and target == Booking.Status.REJECTED:
                raise ValidationError('Cancel a confirmed booking instead of rejecting it.')
            booking.status = target
            booking.save(update_fields=['status'])
            session = subscription = None
            if target == Booking.Status.CONFIRMED:
                session, subscription = create_operational_records_for_confirmed_booking(
                    booking, actor=request.user, request=request)
            else:
                cancel_operational_records_for_booking(booking, actor=request.user, request=request,
                                                      reason='Closed from operations workspace.')
            log_event(category='BOOKING', event='operations_booking_updated', actor=request.user,
                      request=request, related_model='Booking', related_id=booking.id,
                      message=f'Booking {booking.id} changed to {target}')

        create_notification_safely(
            request=request, recipient=booking.customer, sender=request.user,
            kind=Notification.Kind.BOOKING, title=f'Booking {target.lower()}',
            message=f'Your booking at {booking.gym.name} is now {target.lower()}.', url='/bookings/')
        send_booking_status_to_customer(booking, target.lower(), actor=request.user, request=request)
        if session:
            attach_session_qr(request, session)
            send_session_qr_to_customer(session, session.qr_url, session.qr_data_uri, actor=request.user, request=request)
        if subscription:
            attach_membership_qr(request, subscription)
            send_membership_access_pass_to_customer(subscription, subscription.qr_url,
                                                   subscription.qr_data_uri, actor=request.user, request=request)
        return Response({'ok': True, 'booking': booking_data(booking), 'changed': True})


class OwnerDashboardAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    def get(self, request):
        gyms = gym_scope(request.user)
        today = timezone.localdate()
        bookings = Booking.objects.filter(gym__in=gyms).select_related('gym', 'customer', 'plan')
        members = GymSubscription.objects.filter(gym__in=gyms, status='ACTIVE', start_date__lte=today,
                                                 end_date__gte=today).select_related('customer', 'gym', 'plan')
        visits = GymVisit.objects.filter(gym__in=gyms, status='ACTIVE').select_related('customer', 'gym')
        checkins = GymCheckIn.objects.filter(gym__in=gyms, checked_in_at__date=today).select_related('customer', 'gym')
        return Response({
            'stats': {'gyms': gyms.count(), 'pending_bookings': bookings.filter(status='PENDING').count(),
                      'active_members': members.values('customer_id').distinct().count(),
                      'active_visits': visits.count(), 'checkins_today': checkins.count()},
            'gyms': [gym_data(item) for item in gyms.prefetch_related('facilities')],
            'bookings': paginate(request, bookings.order_by('-created_at'), booking_data),
            'members': [{'id': sub.id, 'customer': person(sub.customer), 'gym': sub.gym.name,
                         'plan': sub.plan.title if sub.plan else 'Membership', 'end_date': sub.end_date.isoformat()}
                        for sub in members.order_by('end_date')[:100]],
            'visits': [{'id': visit.id, 'customer': person(visit.customer), 'gym': visit.gym.name,
                        'checked_in_at': visit.checked_in_at.isoformat(), 'duration_minutes': visit.duration_minutes}
                       for visit in visits.order_by('checked_in_at')[:100]],
            'checkins': [{'id': item.id, 'customer': person(item.customer), 'gym': item.gym.name,
                          'checked_in_at': item.checked_in_at.isoformat(), 'type': item.checkin_type}
                         for item in checkins.order_by('-checked_in_at')[:100]],
        })


class OwnerGymAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    def get(self, request, gym_id=None):
        metadata = {'facilities': list(Facility.objects.order_by('name').values('id', 'name')),
                    'trainers': [person(user) for user in User.objects.filter(
                        role='TRAINER', trainer_profile__isnull=True, is_active=True).order_by('username')]}
        if gym_id is None:
            return Response(metadata)
        gym = get_object_or_404(gym_scope(request.user), pk=gym_id)
        return Response({**metadata, 'gym': gym_data(gym),
                         'plans': list(gym.plans.values('id', 'title', 'description', 'price', 'duration_days', 'is_trial')),
                         'trainers_assigned': [{'id': t.id, 'name': t.user.get_full_name() or t.user.username,
                                                'specialties': t.specialties} for t in gym.trainers.select_related('user')],
                         'images': [{'id': image.id, 'url': image.image_url, 'alt_text': image.alt_text,
                                     'is_cover': image.is_cover} for image in gym.images.all()]})

    def post(self, request, gym_id=None):
        if gym_id is not None:
            raise ValidationError('Use PUT to update a gym.')
        gym = save_form(GymForm(request.data), owner=request.user, status=Gym.Status.PENDING)
        log_event(category='GYM', event='operations_gym_created', actor=request.user, request=request,
                  related_model='Gym', related_id=gym.id, message=f'Created {gym.name}')
        return Response(gym_data(gym), status=201)

    def put(self, request, gym_id):
        gym = get_object_or_404(gym_scope(request.user), pk=gym_id)
        gym = save_form(GymForm(request.data, instance=gym))
        log_event(category='GYM', event='operations_gym_updated', actor=request.user, request=request,
                  related_model='Gym', related_id=gym.id, message=f'Updated {gym.name}')
        return Response(gym_data(gym))


class OwnerGymResourceAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    def post(self, request, gym_id, resource):
        gym = get_object_or_404(gym_scope(request.user), pk=gym_id)
        forms = {'plans': MembershipPlanForm, 'trainers': TrainerProfileForm}
        if resource not in forms:
            raise ValidationError('Unknown gym resource.')
        form = forms[resource](request.data)
        if resource == 'trainers':
            form.fields['user'].queryset = User.objects.filter(role='TRAINER', is_active=True,
                                                               trainer_profile__isnull=True)
        obj = save_form(form, gym=gym)
        log_event(category='GYM', event='operations_resource_created', actor=request.user, request=request,
                  related_model=obj.__class__.__name__, related_id=obj.id, message=f'Added {resource} to {gym.name}')
        return Response({'id': obj.id}, status=201)

    def delete(self, request, gym_id, resource, resource_id):
        gym = get_object_or_404(gym_scope(request.user), pk=gym_id)
        models = {'plans': MembershipPlan, 'trainers': TrainerProfile}
        if resource not in models:
            raise ValidationError('Unknown gym resource.')
        obj = get_object_or_404(models[resource], gym=gym, pk=resource_id)
        obj.delete()
        log_event(category='GYM', event='operations_resource_deleted', actor=request.user, request=request,
                  related_model=models[resource].__name__, related_id=resource_id, message=f'Removed {resource} from {gym.name}')
        return Response(status=204)


class OwnerCheckoutAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    def post(self, request, visit_id):
        visit = get_object_or_404(GymVisit.objects.filter(gym__in=gym_scope(request.user)), pk=visit_id)
        _, changed = complete_gym_visit(visit=visit, actor=request.user, request=request)
        return Response({'ok': True, 'changed': changed})


class OwnerCheckInAPIView(APIView):
    permission_classes = [IsOwnerOrStaffAdmin]

    def post(self, request):
        try:
            token = UUID(str(request.data.get('token', '')).strip().rstrip('/').split('/')[-1])
        except (ValueError, AttributeError):
            raise ValidationError('Enter a valid QR URL or token.')
        with transaction.atomic():
            session = Session.objects.select_for_update().filter(qr_token=token, gym__in=gym_scope(request.user)).first()
            subscription = None
            if session:
                if not session.is_one_time_qr_available:
                    raise ValidationError('This session has been cancelled or already used.')
                now = timezone.now()
                if now < session.start_time - timedelta(minutes=30) or now > (session.end_time or session.start_time + timedelta(hours=1)):
                    raise ValidationError('This session is outside its arrival window.')
                if session.booking.status != Booking.Status.CONFIRMED:
                    raise ValidationError('The booking is no longer confirmed.')
                customer, gym = session.customer, session.gym
                method = GymVisit.EntryMethod.SESSION_QR
            else:
                subscription = get_object_or_404(GymSubscription.objects.select_for_update().filter(
                    current_qr_token=token, gym__in=gym_scope(request.user)))
                if not subscription.is_active or not subscription.qr_is_fresh:
                    raise ValidationError('This membership is inactive or its QR needs refreshing.')
                customer, gym = subscription.customer, subscription.gym
                method = GymVisit.EntryMethod.MEMBERSHIP_QR
            if gym.status != Gym.Status.APPROVED:
                raise ValidationError('This gym is not currently approved for entry.')
            try:
                visit, created = start_gym_visit(customer=customer, gym=gym, actor=request.user,
                                                entry_method=method, session=session, subscription=subscription, request=request)
            except ValueError as exc:
                raise ValidationError(str(exc))
            if session:
                session.mark_checked_in()
            elif created:
                GymCheckIn.objects.create(customer=customer, gym=gym, subscription=subscription, checkin_type='MEMBERSHIP')
        return Response({'ok': True, 'created': created, 'customer': person(customer), 'gym': gym.name, 'visit_id': visit.id})


class ControlOverviewAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    def get(self, request):
        return Response({'metrics': _base_metrics(), 'security': _security_check_rows()})


class ControlListAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    def get(self, request, resource):
        query = request.query_params.get('q', '').strip()
        selected = request.query_params.get('status', '')
        if resource == 'users':
            qs = User.objects.order_by('-date_joined')
            if query:
                qs = qs.filter(Q(username__icontains=query) | Q(email__icontains=query))
            if selected:
                qs = qs.filter(role=selected)
            serialize = person
        elif resource == 'gyms':
            qs = Gym.objects.select_related('owner').prefetch_related('facilities').order_by('-created_at')
            if query:
                qs = qs.filter(Q(name__icontains=query) | Q(city__icontains=query))
            if selected:
                qs = qs.filter(status=selected)
            serialize = gym_data
        elif resource == 'bookings':
            qs = Booking.objects.select_related('customer', 'gym', 'plan').order_by('-created_at')
            if query:
                qs = qs.filter(Q(customer__username__icontains=query) | Q(gym__name__icontains=query))
            if selected:
                qs = qs.filter(status=selected)
            serialize = booking_data
        elif resource == 'reviews':
            qs = Review.objects.select_related('user', 'gym').order_by('-created_at')
            if query:
                qs = qs.filter(Q(comment__icontains=query) | Q(gym__name__icontains=query))
            if selected in {'visible', 'hidden'}:
                qs = qs.filter(is_visible=selected == 'visible')
            serialize = lambda r: {'id': r.id, 'customer': person(r.user), 'gym': r.gym.name,
                                   'rating': r.rating, 'comment': r.comment, 'is_visible': r.is_visible}
        elif resource == 'logs':
            qs = SystemLog.objects.select_related('actor').order_by('-created_at')
            if query:
                qs = qs.filter(Q(message__icontains=query) | Q(event__icontains=query))
            if selected:
                qs = qs.filter(level=selected)
            serialize = lambda item: {'id': item.id, 'level': item.level, 'category': item.category,
                                       'event': item.event, 'message': item.message,
                                       'actor': item.actor.username if item.actor else 'System',
                                       'created_at': item.created_at.isoformat()}
        else:
            raise ValidationError('Unknown Control Deck resource.')
        return Response(paginate(request, qs, serialize))


class UserActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=['role', 'active'])
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class ControlUserAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    def post(self, request, user_id):
        data = UserActionInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
            if user.id == request.user.id:
                raise PermissionDenied('Use another administrator to change your own access.')
            if user.is_superuser or ((user.is_staff or user.role == 'ADMIN') and not request.user.is_superuser):
                raise PermissionDenied('This account is protected. Only superusers may manage other operators.')
            if values['action'] == 'role':
                role = values.get('role')
                if not role:
                    raise ValidationError({'role': 'Select a role.'})
                if role == 'ADMIN' and not request.user.is_superuser:
                    raise PermissionDenied('Only superusers can promote administrators.')
                user.role = role
                user.is_staff = role == 'ADMIN'
                user.save(update_fields=['role', 'is_staff'])
            else:
                if 'is_active' not in values:
                    raise ValidationError({'is_active': 'Choose the account state.'})
                user.is_active = values['is_active']
                user.save(update_fields=['is_active'])
            log_event(category='ADMIN', event='operations_user_updated', actor=request.user, request=request,
                      related_model='User', related_id=user.id, message=f'Updated {user.username}: {values}')
        return Response(person(user))


class ControlGymActionInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=['APPROVED', 'REJECTED'])


class ControlGymAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    def post(self, request, gym_id):
        data = ControlGymActionInput(data=request.data)
        data.is_valid(raise_exception=True)
        gym = get_object_or_404(Gym, pk=gym_id)
        gym.status = data.validated_data['status']
        gym.save(update_fields=['status', 'updated_at'])
        create_notification_safely(request=request, recipient=gym.owner, sender=request.user,
                                   kind=Notification.Kind.GYM, title=f'Gym {gym.status.lower()}',
                                   message=f'{gym.name} is now {gym.status.lower()}.', url='/owner')
        send_gym_status_to_owner(gym, gym.status.lower(), actor=request.user, request=request)
        log_event(category='GYM', event='operations_gym_moderated', actor=request.user, request=request,
                  related_model='Gym', related_id=gym.id, message=f'{gym.name}: {gym.status}')
        return Response({'ok': True, 'status': gym.status})


class ControlReviewInput(serializers.Serializer):
    is_visible = serializers.BooleanField()


class ControlReviewAPIView(APIView):
    permission_classes = [IsStaffOrPlatformAdmin]

    def post(self, request, review_id):
        data = ControlReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        review = get_object_or_404(Review, pk=review_id)
        review.is_visible = data.validated_data['is_visible']
        review.save(update_fields=['is_visible'])
        log_event(category='REVIEW', event='operations_review_moderated', actor=request.user, request=request,
                  related_model='Review', related_id=review.id, message=f'Review visibility: {review.is_visible}')
        return Response({'ok': True, 'is_visible': review.is_visible})
