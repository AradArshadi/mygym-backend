from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking, GymCheckIn, GymSubscription, GymVisit, Session
from apps.bookings.services import create_operational_records_for_confirmed_booking, refresh_due_membership_qrs_for_user
from apps.gyms.models import Gym, MembershipPlan


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SITE_URL='http://testserver',
)
class BookingInfrastructureTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='pass12345',
            role=User.Role.OWNER,
        )
        self.customer = User.objects.create_user(
            username='customer',
            email='customer@example.com',
            password='pass12345',
            role=User.Role.CUSTOMER,
        )
        self.admin = User.objects.create_user(
            username='operator',
            email='operator@example.com',
            password='pass12345',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.gym = Gym.objects.create(
            owner=self.owner,
            name='Infrastructure Gym',
            slug='infrastructure-gym',
            description='A gym for infrastructure tests.',
            city='Bamberg',
            address='Test Street 1',
            email='gym@example.com',
            starting_price=Decimal('29.90'),
            status=Gym.Status.APPROVED,
        )
        self.plan = MembershipPlan.objects.create(
            gym=self.gym,
            title='Monthly Pass',
            description='Test membership plan',
            price=Decimal('49.00'),
            duration_days=30,
            is_trial=False,
        )
        self.when = timezone.make_aware(datetime(2026, 8, 5, 14, 0), timezone.get_current_timezone())

    def make_booking(self, *, plan=None, status=Booking.Status.PENDING):
        return Booking.objects.create(
            customer=self.customer,
            gym=self.gym,
            plan=plan,
            booking_datetime=self.when,
            status=status,
            customer_note='I want to visit.',
        )

    def test_owner_confirmation_creates_session_and_access_pass(self):
        booking = self.make_booking(plan=self.plan)
        self.client.force_login(self.owner)

        response = self.client.post(reverse('update_booking_status', args=[booking.id, 'confirm']))

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertTrue(Session.objects.filter(booking=booking).exists())
        self.assertTrue(GymSubscription.objects.filter(source_booking=booking, status=GymSubscription.Status.ACTIVE).exists())

    def test_admin_control_confirmation_creates_session_and_access_pass(self):
        booking = self.make_booking(plan=self.plan)
        self.client.force_login(self.admin)

        response = self.client.post(reverse('control_update_booking_status', args=[booking.id, 'confirm']))

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertTrue(Session.objects.filter(booking=booking).exists())
        self.assertTrue(GymSubscription.objects.filter(source_booking=booking, status=GymSubscription.Status.ACTIVE).exists())

    def test_session_qr_check_in_is_one_time_use(self):
        booking = self.make_booking(plan=None, status=Booking.Status.CONFIRMED)
        session, _ = create_operational_records_for_confirmed_booking(booking, actor=self.owner)
        self.client.force_login(self.owner)

        response = self.client.post(reverse('session_check_in', args=[session.qr_token]))

        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, Session.Status.CHECKED_IN)
        self.assertIsNotNone(session.qr_used_at)
        self.assertEqual(GymCheckIn.objects.filter(session=session).count(), 1)

        second_response = self.client.post(reverse('session_check_in', args=[session.qr_token]))
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(GymCheckIn.objects.filter(session=session).count(), 1)

    def test_expired_membership_is_marked_expired_during_refresh(self):
        booking = self.make_booking(plan=self.plan, status=Booking.Status.CONFIRMED)
        yesterday = timezone.localdate() - timedelta(days=1)
        subscription = GymSubscription.objects.create(
            customer=self.customer,
            gym=self.gym,
            plan=self.plan,
            source_booking=booking,
            status=GymSubscription.Status.ACTIVE,
            start_date=yesterday - timedelta(days=30),
            end_date=yesterday,
        )

        refreshed = refresh_due_membership_qrs_for_user(self.customer)

        subscription.refresh_from_db()
        self.assertEqual(refreshed, 0)
        self.assertEqual(subscription.status, GymSubscription.Status.EXPIRED)

    def test_customer_is_redirected_away_from_owner_dashboard(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse('owner_dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('customer_dashboard'))

    def test_membership_checkin_creates_active_visit_and_customer_can_checkout(self):
        booking = self.make_booking(plan=self.plan, status=Booking.Status.CONFIRMED)
        _, subscription = create_operational_records_for_confirmed_booking(booking, actor=self.owner)
        self.client.force_login(self.owner)

        response = self.client.post(reverse('membership_check_in', args=[subscription.current_qr_token]))

        self.assertEqual(response.status_code, 302)
        visit = GymVisit.objects.get(customer=self.customer, status=GymVisit.Status.ACTIVE)
        self.assertEqual(visit.gym, self.gym)
        self.assertEqual(visit.subscription, subscription)

        self.client.force_login(self.customer)
        checkout = self.client.post(reverse('checkout_visit', args=[visit.id]))
        self.assertEqual(checkout.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(visit.status, GymVisit.Status.COMPLETED)
        self.assertIsNotNone(visit.checked_out_at)

    def test_repeat_membership_scan_does_not_create_duplicate_active_visit(self):
        booking = self.make_booking(plan=self.plan, status=Booking.Status.CONFIRMED)
        _, subscription = create_operational_records_for_confirmed_booking(booking, actor=self.owner)
        self.client.force_login(self.owner)

        self.client.post(reverse('membership_check_in', args=[subscription.current_qr_token]))
        self.client.post(reverse('membership_check_in', args=[subscription.current_qr_token]))

        self.assertEqual(GymVisit.objects.filter(customer=self.customer, status=GymVisit.Status.ACTIVE).count(), 1)
        self.assertEqual(GymCheckIn.objects.filter(subscription=subscription).count(), 1)

    def test_customer_home_and_visit_page_show_active_visit_checkout(self):
        booking = self.make_booking(plan=self.plan, status=Booking.Status.CONFIRMED)
        _, subscription = create_operational_records_for_confirmed_booking(booking, actor=self.owner)
        visit = GymVisit.objects.create(
            customer=self.customer,
            gym=self.gym,
            subscription=subscription,
            checked_in_by=self.owner,
            entry_method=GymVisit.EntryMethod.MEMBERSHIP_QR,
        )
        self.client.force_login(self.customer)

        home = self.client.get(reverse('fitness_home'))
        visit_page = self.client.get(reverse('my_memberships'))

        self.assertContains(home, 'Welcome')
        self.assertContains(home, 'Check out')
        self.assertContains(visit_page, 'Active now')
        self.assertContains(visit_page, reverse('checkout_visit', args=[visit.id]))

    def test_unauthorized_qr_page_hides_customer_details(self):
        outsider = User.objects.create_user(username='outsider', password='pass12345', role=User.Role.OWNER)
        booking = self.make_booking(plan=self.plan, status=Booking.Status.CONFIRMED)
        _, subscription = create_operational_records_for_confirmed_booking(booking, actor=self.owner)
        self.client.force_login(outsider)

        response = self.client.get(reverse('membership_check_in', args=[subscription.current_qr_token]))

        self.assertNotContains(response, self.customer.email)
        self.assertNotContains(response, '<div class="staff-member-profile">', html=True)
        self.assertNotContains(response, self.plan.title)
        self.assertNotContains(response, subscription.end_date.strftime('%d %B %Y'))

    def test_datetime_local_booking_input_is_saved_timezone_aware(self):
        self.client.force_login(self.customer)

        response = self.client.post(reverse('create_booking', args=[self.gym.id]), {
            'booking_datetime': '2026-08-05T14:30',
            'plan': self.plan.id,
            'customer_note': 'Testing local datetime handling.',
        })

        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get(customer=self.customer, gym=self.gym)
        self.assertTrue(timezone.is_aware(booking.booking_datetime))
        local_dt = timezone.localtime(booking.booking_datetime, timezone.get_current_timezone())
        self.assertEqual(local_dt.hour, 14)
        self.assertEqual(local_dt.minute, 30)
