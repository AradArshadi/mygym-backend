from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Booking, GymCheckIn, GymSubscription, GymVisit, Session
from apps.bookings.services import create_operational_records_for_confirmed_booking
from apps.gyms.models import Gym, MembershipPlan
from apps.notifications.models import Notification
from apps.reviews.models import Review


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_URL='http://testserver')
class OperationsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(username='customer_ops', email='customer@example.com')
        self.owner = User.objects.create_user(username='owner_ops', role='OWNER')
        self.other = User.objects.create_user(username='other_owner_ops', role='OWNER')
        self.admin = User.objects.create_user(username='operator_ops', role='ADMIN', is_staff=True)
        self.root = User.objects.create_superuser(username='root_ops', email='', password='testpassword')
        self.gym = Gym.objects.create(owner=self.owner, name='Operations Gym', slug='operations-gym',
                                      description='Test gym', city='Test', address='Test road',
                                      starting_price=20, status='APPROVED')
        self.plan = MembershipPlan.objects.create(gym=self.gym, title='Monthly', price=30, duration_days=30)
        self.booking = Booking.objects.create(customer=self.customer, gym=self.gym,
                                               plan=self.plan, booking_datetime=timezone.now())

    def auth(self, user):
        self.client.force_authenticate(user)

    def test_customer_and_anonymous_cannot_enter_operations(self):
        for user in [None, self.customer]:
            self.auth(user)
            for url in ['/api/v1/owner/dashboard/', '/api/v1/control/overview/', '/api/v1/control/users/']:
                self.assertIn(self.client.get(url).status_code, [401, 403])

    def test_owner_dashboard_scopes_data(self):
        self.auth(self.other)
        data = self.client.get('/api/v1/owner/dashboard/').json()
        self.assertEqual(data['gyms'], [])
        self.assertEqual(data['bookings']['count'], 0)
        self.auth(self.owner)
        data = self.client.get('/api/v1/owner/dashboard/').json()
        self.assertEqual(data['gyms'][0]['id'], self.gym.id)
        self.assertEqual(data['bookings']['results'][0]['customer']['id'], self.customer.id)

    def test_owner_cannot_read_or_update_another_gym(self):
        self.auth(self.other)
        url = f'/api/v1/owner/gyms/{self.gym.id}/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.put(url, {'name': 'Stolen'}, format='json').status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/owner/gyms/{self.gym.id}/plans/', {}, format='json').status_code, 404)

    def test_owner_cannot_moderate_platform_or_other_bookings(self):
        self.auth(self.owner)
        self.assertEqual(self.client.get('/api/v1/control/users/').status_code, 403)
        self.auth(self.other)
        self.assertEqual(self.client.post(f'/api/v1/operations/bookings/{self.booking.id}/', {'action': 'confirm'}, format='json').status_code, 404)

    def test_owner_and_admin_confirmation_creates_records_and_repeat_is_idempotent(self):
        for actor in [self.owner, self.admin]:
            booking = Booking.objects.create(customer=self.customer, gym=self.gym, plan=self.plan,
                                               booking_datetime=timezone.now() + timedelta(minutes=actor.id))
            self.auth(actor)
            url = f'/api/v1/operations/bookings/{booking.id}/'
            self.assertEqual(self.client.post(url, {'action': 'confirm'}, format='json').status_code, 200)
            sub = GymSubscription.objects.get(source_booking=booking)
            token = sub.current_qr_token
            result = self.client.post(url, {'action': 'confirm'}, format='json')
            self.assertFalse(result.json()['changed'])
            sub.refresh_from_db()
            self.assertEqual(sub.current_qr_token, token)
            self.assertEqual(Session.objects.filter(booking=booking).count(), 1)
            self.assertTrue(Notification.objects.filter(recipient=self.customer).exists())

    def test_cancellation_revokes_linked_access_and_closed_bookings_stay_closed(self):
        self.auth(self.owner)
        url = f'/api/v1/operations/bookings/{self.booking.id}/'
        self.client.post(url, {'action': 'confirm'}, format='json')
        self.assertEqual(self.client.post(url, {'action': 'cancel'}, format='json').status_code, 200)
        self.assertEqual(Session.objects.get(booking=self.booking).status, 'CANCELLED')
        self.assertEqual(GymSubscription.objects.get(source_booking=self.booking).status, 'CANCELLED')
        self.assertEqual(self.client.post(url, {'action': 'confirm'}, format='json').status_code, 400)

    def test_owner_create_cannot_spoof_approval_or_owner(self):
        self.auth(self.owner)
        result = self.client.post('/api/v1/owner/gyms/', {
            'name': 'New gym', 'slug': 'new-ops-gym', 'description': 'New', 'city': 'Test',
            'address': 'Test', 'starting_price': '10', 'facilities': [],
            'status': 'APPROVED', 'owner': self.other.id,
        }, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        gym = Gym.objects.get(pk=result.data['id'])
        self.assertEqual(gym.owner, self.owner)
        self.assertEqual(gym.status, 'PENDING')

    def test_gym_form_returns_validation_errors(self):
        self.auth(self.owner)
        result = self.client.post('/api/v1/owner/gyms/', {'name': 'Incomplete'}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertIn('slug', result.data)

    def test_owner_can_add_plan_and_delete_only_scoped_resource(self):
        self.auth(self.owner)
        url = f'/api/v1/owner/gyms/{self.gym.id}/plans/'
        result = self.client.post(url, {'title': 'Day', 'price': '8', 'duration_days': 1, 'is_trial': True}, format='json')
        self.assertEqual(result.status_code, 201)
        self.auth(self.other)
        self.assertEqual(self.client.delete(f'{url}{result.data["id"]}/').status_code, 404)
        self.auth(self.owner)
        self.assertEqual(self.client.delete(f'{url}{result.data["id"]}/').status_code, 204)

    def test_operator_cannot_promote_admin_or_deactivate_privileged_accounts(self):
        self.auth(self.admin)
        result = self.client.post(f'/api/v1/control/users/{self.customer.id}/', {'action': 'role', 'role': 'ADMIN'}, format='json')
        self.assertEqual(result.status_code, 403)
        for user in [self.root, self.admin]:
            self.assertEqual(self.client.post(f'/api/v1/control/users/{user.id}/', {'action': 'active', 'is_active': False}, format='json').status_code, 403)
        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)

    def test_superuser_promotes_user_and_me_exposes_role_flags(self):
        self.auth(self.root)
        self.assertEqual(self.client.post(f'/api/v1/control/users/{self.customer.id}/', {'action': 'role', 'role': 'ADMIN'}, format='json').status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_staff)
        data = self.client.get('/api/v1/auth/me/').json()['user']
        self.assertTrue(data['is_staff'])
        self.assertTrue(data['is_superuser'])

    def test_admin_moderates_gym_and_review(self):
        self.auth(self.admin)
        result = self.client.post(f'/api/v1/control/gyms/{self.gym.id}/', {'status': 'REJECTED'}, format='json')
        self.assertEqual(result.status_code, 200)
        review = Review.objects.create(user=self.customer, gym=self.gym, rating=4, comment='A good gym.')
        self.assertEqual(self.client.post(f'/api/v1/control/reviews/{review.id}/', {'is_visible': False}, format='json').status_code, 200)
        review.refresh_from_db()
        self.assertFalse(review.is_visible)

    def test_control_search_and_pagination(self):
        self.auth(self.admin)
        response = self.client.get('/api/v1/control/users/?q=customer_ops&status=CUSTOMER')
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['id'], self.customer.id)
        self.assertEqual(self.client.get('/api/v1/control/overview/').status_code, 200)

    def test_membership_checkin_is_scoped_and_repeat_does_not_duplicate(self):
        self.booking.status = 'CONFIRMED'
        self.booking.save()
        _, subscription = create_operational_records_for_confirmed_booking(self.booking)
        payload = {'token': f'http://testserver/bookings/memberships/check-in/{subscription.current_qr_token}/'}
        self.auth(self.other)
        self.assertEqual(self.client.post('/api/v1/owner/check-in/', payload, format='json').status_code, 404)
        self.auth(self.owner)
        for _ in range(2):
            result = self.client.post('/api/v1/owner/check-in/', payload, format='json')
            self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(GymVisit.objects.filter(customer=self.customer, status='ACTIVE').count(), 1)
        self.assertEqual(GymCheckIn.objects.filter(subscription=subscription).count(), 1)
        visit = GymVisit.objects.get(customer=self.customer)
        self.auth(self.other)
        self.assertEqual(self.client.post(f'/api/v1/owner/visits/{visit.id}/checkout/').status_code, 404)
        self.auth(self.owner)
        self.assertEqual(self.client.post(f'/api/v1/owner/visits/{visit.id}/checkout/').status_code, 200)
        visit.refresh_from_db()
        self.assertEqual(visit.status, 'COMPLETED')

    def test_session_checkin_rejects_expired_session(self):
        self.booking.status = 'CONFIRMED'
        self.booking.booking_datetime = timezone.now() - timedelta(days=2)
        self.booking.save()
        session, _ = create_operational_records_for_confirmed_booking(self.booking)
        self.auth(self.owner)
        result = self.client.post('/api/v1/owner/check-in/', {'token': str(session.qr_token)}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertFalse(GymVisit.objects.exists())

    def test_session_authenticated_mutations_enforce_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.admin)
        result = client.post(f'/api/v1/control/gyms/{self.gym.id}/', {'status': 'REJECTED'}, format='json')
        self.assertEqual(result.status_code, 403)
