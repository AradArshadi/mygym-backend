from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.gyms.models import Gym, MembershipPlan
from apps.bookings.models import GymCheckIn, GymSubscription


class ApiSmokeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username='api_admin',
            email='api.admin@example.com',
            password='pass12345',
            role=getattr(User.Role, 'ADMIN', 'ADMIN'),
            is_staff=True,
        )
        self.owner = User.objects.create_user(
            username='api_owner',
            email='api.owner@example.com',
            password='pass12345',
            role=getattr(User.Role, 'OWNER', 'OWNER'),
        )
        self.customer = User.objects.create_user(
            username='api_customer',
            email='api.customer@example.com',
            password='pass12345',
            role=getattr(User.Role, 'CUSTOMER', 'CUSTOMER'),
        )
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='API Gym',
            slug='api-gym',
            description='Demo API gym',
            city='Bamberg',
            address='API Street 1',
            starting_price='39.00',
            status=Gym.Status.APPROVED,
        )

    def test_gym_list_api_is_paginated(self):
        response = self.client.get('/api/gyms/?page_size=20')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['page_size'], 20)
        self.assertEqual(payload['results'][0]['slug'], 'api-gym')

    def test_favorite_api_requires_auth(self):
        response = self.client.post('/api/gyms/api-gym/favorite/')
        self.assertIn(response.status_code, [401, 403])

    def test_customer_can_favorite_gym(self):
        self.client.force_login(self.customer)
        response = self.client.post('/api/gyms/api-gym/favorite/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])

    def test_owner_analytics_requires_owner_or_admin(self):
        self.client.force_login(self.customer)
        response = self.client.get('/api/owner/analytics/')
        self.assertEqual(response.status_code, 403)

    def test_owner_can_open_owner_analytics_api(self):
        self.client.force_login(self.owner)
        response = self.client.get('/api/owner/analytics/?days=30')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['owner']['username'], 'api_owner')

    @override_settings(DEMO_TOOLS_ENABLED=False)
    def test_demo_seed_disabled_returns_403(self):
        self.client.force_login(self.admin)
        response = self.client.post('/api/demo/seed-analytics/', data={'days': 30, 'customers': 5}, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_email_config_is_sanitized_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get('/api/email/config/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('SECRET', response.json())
        self.assertIn(response.json()['EMAIL_HOST_PASSWORD'], ['SET', 'EMPTY'])


    @override_settings(DEMO_TOOLS_ENABLED=True)
    def test_demo_seed_spreads_checkins_and_memberships_over_time(self):
        MembershipPlan.objects.create(
            gym=self.gym,
            title='Monthly',
            price='39.00',
            duration_days=30,
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            '/api/demo/seed-analytics/',
            data={
                'days': 90,
                'customers': 8,
                'subscriptions_per_gym': 8,
                'bookings_per_gym': 4,
                'checkins_per_gym': 60,
                'favorites_per_gym': 3,
                'workouts_per_customer': 0,
                'traffic_profile': 'balanced',
                'reset_demo': True,
                'seed': 9310,
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()['result']
        self.assertEqual(payload['traffic_profile'], 'balanced')
        self.assertGreater(len(payload['hour_distribution']), 3)
        self.assertGreater(sum(1 for value in payload['weekday_distribution'].values() if value), 3)

        checkin_dates = {
            value.date()
            for value in GymCheckIn.objects.filter(gym=self.gym).values_list('checked_in_at', flat=True)
        }
        subscription_created_dates = {
            value.date()
            for value in GymSubscription.objects.filter(gym=self.gym).values_list('created_at', flat=True)
        }
        self.assertGreater(len(checkin_dates), 3)
        self.assertGreater(len(subscription_created_dates), 1)

from io import BytesIO
from unittest.mock import patch
from PIL import Image as PILImage
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.gyms.image_hosting import HostedImage
from apps.gyms.models import GymImage


class GymImageApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username='image_owner', email='image-owner@example.com', password='pass12345',
            role=getattr(User.Role, 'OWNER', 'OWNER'),
        )
        self.other = User.objects.create_user(
            username='image_other', email='image-other@example.com', password='pass12345',
            role=getattr(User.Role, 'OWNER', 'OWNER'),
        )
        self.gym = Gym.objects.create(
            owner=self.owner, name='Image API Gym', slug='image-api-gym',
            description='Image API test', city='Bamberg', address='Image Street 1',
            starting_price='30.00', status=Gym.Status.APPROVED,
        )

    def _png(self):
        stream = BytesIO()
        PILImage.new('RGB', (3, 3), (255, 100, 0)).save(stream, format='PNG')
        return SimpleUploadedFile('photo.png', stream.getvalue(), content_type='image/png')

    @patch('apps.gyms.forms.upload_image')
    def test_owner_upload_stores_remote_url_without_local_image(self, mocked_upload):
        mocked_upload.return_value = HostedImage(
            id='imgbb123', url='https://i.ibb.co/example/photo.png',
            display_url='https://i.ibb.co/example/photo.png',
            delete_url='https://ibb.co/delete/private', width=3, height=3, size=75,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            '/api/gyms/image-api-gym/images/',
            data={'image': self._png(), 'alt_text': 'Gym photo', 'is_cover': 'on'},
        )
        self.assertEqual(response.status_code, 201, response.content)
        row = GymImage.objects.get(gym=self.gym)
        self.assertEqual(row.external_url, 'https://i.ibb.co/example/photo.png')
        self.assertFalse(bool(row.image))
        self.assertNotIn('delete_url', response.json())

    @patch('apps.gyms.forms.upload_image')
    def test_non_owner_cannot_upload_gym_image(self, mocked_upload):
        self.client.force_login(self.other)
        response = self.client.post('/api/gyms/image-api-gym/images/', data={'image': self._png()})
        self.assertEqual(response.status_code, 403)
        mocked_upload.assert_not_called()
