from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, GymSubscription
from apps.gyms.models import Gym, MembershipPlan


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OwnerDashboardUXTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner_dash',
            email='owner@example.com',
            password='pass12345',
            role=User.Role.OWNER,
        )
        self.customer = User.objects.create_user(
            username='owner_customer',
            email='customer@example.com',
            password='pass12345',
            role=User.Role.CUSTOMER,
        )
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='Owner UX Gym',
            slug='owner-ux-gym',
            description='Dashboard UX test gym.',
            city='Bamberg',
            address='Test Street 1',
            email='gym@example.com',
            starting_price=Decimal('39.00'),
            status=Gym.Status.APPROVED,
        )
        self.plan = MembershipPlan.objects.create(
            gym=self.gym,
            title='Monthly Pass',
            description='Access plan.',
            price=Decimal('49.00'),
            duration_days=30,
        )
        when = timezone.make_aware(datetime(2026, 8, 5, 14, 0), timezone.get_current_timezone())
        self.pending_booking = Booking.objects.create(
            customer=self.customer,
            gym=self.gym,
            plan=self.plan,
            booking_datetime=when,
            status=Booking.Status.PENDING,
            customer_note='First visit.',
        )
        self.confirmed_booking = Booking.objects.create(
            customer=self.customer,
            gym=self.gym,
            plan=None,
            booking_datetime=when + timedelta(days=1),
            status=Booking.Status.CONFIRMED,
        )
        GymSubscription.objects.create(
            customer=self.customer,
            gym=self.gym,
            plan=self.plan,
            source_booking=self.confirmed_booking,
            status=GymSubscription.Status.ACTIVE,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
        )

    def test_owner_stat_cards_are_clickable_jump_links(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="#owner-pending-requests"')
        self.assertContains(response, 'href="#owner-confirmed-bookings"')
        self.assertContains(response, 'href="#owner-active-members"')
        self.assertContains(response, 'href="#owner-recent-checkins"')
        self.assertContains(response, 'owner-stat-card')

    def test_pending_requests_are_visible_before_gym_portfolio_table(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_dashboard'))
        html = response.content.decode()
        self.assertIn('Pending booking requests', html)
        self.assertIn('First visit.', html)
        self.assertLess(html.index('Pending booking requests'), html.index('Your gyms'))

    def test_owner_dashboard_uses_premium_owner_panel_classes(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_dashboard'))
        self.assertContains(response, 'owner-panel')
        self.assertContains(response, 'owner-gym-panel')
        self.assertContains(response, 'owner-mini-stat')

from apps.bookings.models import GymCheckIn, Session
from apps.analytics.services import get_gym_analytics, get_owner_portfolio_analytics
from apps.reviews.models import Favorite


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OwnerAnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='analytics_owner', email='owner2@example.com', password='pass12345', role=User.Role.OWNER)
        self.customer = User.objects.create_user(username='analytics_customer', email='cust2@example.com', password='pass12345', role=User.Role.CUSTOMER)
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='Analytics Gym',
            slug='analytics-gym',
            description='Analytics test gym.',
            city='Bamberg',
            address='Traffic Street 1',
            email='analytics@example.com',
            starting_price=Decimal('25.00'),
            status=Gym.Status.APPROVED,
        )
        self.plan = MembershipPlan.objects.create(gym=self.gym, title='Analytics Monthly', price=Decimal('59.00'), duration_days=30)
        when = timezone.now() + timedelta(days=2)
        self.booking = Booking.objects.create(customer=self.customer, gym=self.gym, plan=self.plan, booking_datetime=when, status=Booking.Status.CONFIRMED)
        self.subscription = GymSubscription.objects.create(
            customer=self.customer,
            gym=self.gym,
            plan=self.plan,
            source_booking=self.booking,
            status=GymSubscription.Status.ACTIVE,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=30),
        )
        self.session = Session.objects.create(booking=self.booking, customer=self.customer, gym=self.gym, start_time=when)
        GymCheckIn.objects.create(customer=self.customer, gym=self.gym, session=self.session, checkin_type=GymCheckIn.CheckInType.SESSION)
        Favorite.objects.create(user=self.customer, gym=self.gym)

    def test_gym_analytics_service_uses_real_checkins_income_growth_and_conversion(self):
        data = get_gym_analytics(self.gym, days=30)
        self.assertEqual(data['total_checkins'], 1)
        self.assertEqual(data['growth']['active_members'], 1)
        self.assertEqual(data['income']['total'], Decimal('59.00'))
        self.assertEqual(data['conversion']['confirmed'], 1)
        self.assertEqual(data['favorites'], 1)
        self.assertEqual(sum(hour['count'] for hour in data['peak']['hours']), 1)

    def test_owner_dashboard_contains_merged_analytics(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Portfolio analytics')
        self.assertContains(response, 'Analytics Gym')
        self.assertContains(response, 'Estimated income')
        self.assertContains(response, 'Member traffic by hour')

    def test_old_analytics_urls_redirect_to_owner_dashboard_anchors(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('owner_analytics'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('#owner-analytics', response['Location'])
        response = self.client.get(reverse('owner_gym_analytics', args=[self.gym.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'#owner-gym-analytics-{self.gym.id}', response['Location'])

    def test_non_owner_cannot_open_gym_analytics(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('owner_gym_analytics', args=[self.gym.id]))
        self.assertEqual(response.status_code, 302)
