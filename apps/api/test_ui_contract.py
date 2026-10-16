from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.fitness.models import WorkoutLog
from apps.gyms.models import Facility, Gym


class UiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(username='ui_owner', role='OWNER')
        self.other = User.objects.create_user(username='ui_other', role='OWNER')
        self.customer = User.objects.create_user(username='ui_member')
        self.sauna = Facility.objects.create(name='Sauna')
        self.weights = Facility.objects.create(name='Weights')
        self.first = Gym.objects.create(owner=self.owner, name='First', slug='ui-first', description='Gym',
                                        city='Tabriz', address='Test', starting_price=20, status='APPROVED')
        self.second = Gym.objects.create(owner=self.owner, name='Second', slug='ui-second', description='Gym',
                                         city='Berlin', address='Test', starting_price=40, status='APPROVED')
        self.first.facilities.add(self.sauna, self.weights)
        self.second.facilities.add(self.weights)

    def test_filter_metadata_and_all_selected_facilities(self):
        result = self.client.get(f'/api/v1/gyms/?facilities={self.sauna.id}&facilities={self.weights.id}').json()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['id'], self.first.id)
        self.assertEqual(result['filters']['cities'], ['Berlin', 'Tabriz'])
        self.assertEqual({item['id'] for item in result['results'][0]['facilities']}, {self.sauna.id, self.weights.id})
        page = self.client.get('/api/v1/gyms/?page_size=1&page=2').json()
        self.assertEqual(page['page'], 2)
        self.assertFalse(page['has_next'])

    def test_invalid_filter_values_are_validation_errors(self):
        for query in ['max_price=bad', 'max_price=NaN', 'max_price=Infinity', 'max_price=-1',
                      'min_rating=6', 'min_rating=NaN', 'facilities=not-an-id']:
            self.assertEqual(self.client.get(f'/api/v1/gyms/?{query}').status_code, 400, query)

    def test_selected_gym_scopes_owner_statistics_and_bookings(self):
        for gym in [self.first, self.second]:
            Booking.objects.create(customer=self.customer, gym=gym, booking_datetime=timezone.now())
        self.client.force_authenticate(self.owner)
        data = self.client.get(f'/api/v1/owner/dashboard/?gym_id={self.first.id}').json()
        self.assertEqual(data['stats']['gyms'], 1)
        self.assertEqual(data['stats']['pending_bookings'], 1)
        self.assertEqual(data['bookings']['count'], 1)
        self.assertEqual(data['pending_requests'][0]['gym']['id'], self.first.id)
        self.assertEqual(len(data['gyms']), 2)  # Selector retains the owner's other gyms.
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/v1/owner/dashboard/?gym_id={self.first.id}').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/owner/dashboard/?gym_id=bad').status_code, 400)

    def test_day_details_never_include_another_members_workout(self):
        now = timezone.now()
        WorkoutLog.objects.create(user=self.customer, title='Today', logged_at=now)
        WorkoutLog.objects.create(user=self.customer, title='Earlier', logged_at=now - timedelta(days=2))
        WorkoutLog.objects.create(user=self.owner, title='Private workout', logged_at=now)
        self.client.force_authenticate(self.customer)
        data = self.client.get(f'/api/v1/fitness/workouts/?date={timezone.localdate(now)}').json()
        self.assertEqual([item['title'] for item in data['results']], ['Today'])
        self.assertEqual(self.client.get('/api/v1/fitness/workouts/?date=invalid').status_code, 400)
