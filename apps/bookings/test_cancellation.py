"""Customer cancellation must revoke only the access purchased by that booking."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services
from apps.bookings.models import Booking, GymCheckIn, GymSubscription, GymVisit, Session
from apps.gyms.models import Gym, MembershipPlan
from apps.notifications.models import Notification


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    SITE_URL='http://testserver',
)
class CustomerCancellationTests(TestCase):
    routes = ('api_session', 'api_booking', 'legacy_session', 'legacy_booking')

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username='cancelling_customer', role=User.Role.CUSTOMER)
        cls.other_customer = User.objects.create_user(username='another_customer', role=User.Role.CUSTOMER)
        cls.owner = User.objects.create_user(username='cancellation_owner', role=User.Role.OWNER)
        cls.admin = User.objects.create_user(
            username='cancellation_admin', role=User.Role.ADMIN, is_staff=True,
        )
        cls.gym = Gym.objects.create(
            owner=cls.owner, name='Cancellation Gym', slug='cancellation-gym',
            description='Cancellation regression fixture.', city='Tehran',
            address='Test street', starting_price=20, status=Gym.Status.APPROVED,
        )
        cls.plan = MembershipPlan.objects.create(
            gym=cls.gym, title='Monthly membership', price=30, duration_days=30, is_trial=False,
        )

    def setUp(self):
        self.api = APIClient()
        self.booking_number = 0

    def make_booking(self, *, operational=True, with_plan=True):
        # Distinct times satisfy the booking uniqueness constraint in route matrices.
        self.booking_number += 1
        booking = Booking.objects.create(
            customer=self.customer, gym=self.gym, plan=self.plan if with_plan else None,
            booking_datetime=timezone.now() + timedelta(seconds=self.booking_number),
            status=Booking.Status.CONFIRMED if operational else Booking.Status.PENDING,
        )
        if operational:
            session, subscription = services.create_operational_records_for_confirmed_booking(booking)
            return booking, session, subscription
        return booking, None, None

    def make_unrelated_subscription(self):
        today = timezone.localdate()
        return GymSubscription.objects.create(
            customer=self.customer, gym=self.gym, plan=self.plan,
            start_date=today, end_date=today + timedelta(days=30),
        )

    def post_cancellation(self, route, booking, session, *, user=None):
        user = user or self.customer
        if route.startswith('api_'):
            self.api.force_authenticate(user)
            name = 'react_cancel_session' if route == 'api_session' else 'react_cancel_booking'
            pk = session.pk if route == 'api_session' else booking.pk
            return self.api.post(reverse(name, args=[pk]), {}, format='json')
        self.client.force_login(user)
        name = 'cancel_session' if route == 'legacy_session' else 'cancel_own_booking'
        pk = session.pk if route == 'legacy_session' else booking.pk
        return self.client.post(reverse(name, args=[pk]))

    def assert_cancelled(self, booking, session, subscription):
        booking.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(session.status, Session.Status.CANCELLED)
        self.assertIsNotNone(session.cancelled_at)
        self.assertTrue(session.cancel_reason)
        self.assertFalse(session.is_one_time_qr_available)
        self.assertIsNone(session.qr_used_at)
        if subscription:
            subscription.refresh_from_db()
            self.assertEqual(subscription.status, GymSubscription.Status.CANCELLED)
            self.assertFalse(subscription.is_active)

    def snapshot(self, booking, session, subscription):
        return (
            Booking.objects.filter(pk=booking.pk).values().get(),
            Session.objects.filter(booking=booking).values().first(),
            GymSubscription.objects.filter(source_booking=booking).values().first(),
            Notification.objects.count(), GymVisit.objects.count(), GymCheckIn.objects.count(),
        )

    def test_all_customer_routes_revoke_linked_access_and_preserve_other_memberships(self):
        for route in self.routes:
            with self.subTest(route=route):
                booking, session, subscription = self.make_booking()
                unrelated = self.make_unrelated_subscription()
                unrelated_values = GymSubscription.objects.filter(pk=unrelated.pk).values().get()

                response = self.post_cancellation(route, booking, session)

                self.assertEqual(response.status_code, 200 if route.startswith('api_') else 302)
                self.assert_cancelled(booking, session, subscription)
                self.assertEqual(
                    GymSubscription.objects.filter(pk=unrelated.pk).values().get(), unrelated_values,
                )

    def test_booking_routes_cancel_pending_request_without_creating_access(self):
        for route in ('api_booking', 'legacy_booking'):
            with self.subTest(route=route):
                booking, _, _ = self.make_booking(operational=False)

                response = self.post_cancellation(route, booking, None)

                self.assertEqual(response.status_code, 200 if route.startswith('api_') else 302)
                booking.refresh_from_db()
                self.assertEqual(booking.status, Booking.Status.CANCELLED)
                self.assertFalse(Session.objects.filter(booking=booking).exists())
                self.assertFalse(GymSubscription.objects.filter(source_booking=booking).exists())

    def test_session_routes_also_cancel_bookings_without_a_membership(self):
        for route in ('api_session', 'legacy_session'):
            with self.subTest(route=route):
                booking, session, _ = self.make_booking(with_plan=False)

                response = self.post_cancellation(route, booking, session)

                self.assertEqual(response.status_code, 200 if route.startswith('api_') else 302)
                self.assert_cancelled(booking, session, None)

    def test_cancelled_session_and_membership_qrs_are_denied_by_both_readers(self):
        for route in self.routes:
            with self.subTest(route=route):
                booking, session, subscription = self.make_booking()
                self.post_cancellation(route, booking, session)
                self.api.force_authenticate(self.owner)
                self.client.force_login(self.owner)

                for token, legacy_name in (
                    (session.qr_token, 'session_check_in'),
                    (subscription.current_qr_token, 'membership_check_in'),
                ):
                    with self.subTest(reader=legacy_name):
                        response = self.api.post(
                            '/api/v1/owner/check-in/', {'token': str(token)}, format='json',
                        )
                        self.assertEqual(response.status_code, 400, response.data)
                        self.assertEqual(self.client.post(reverse(legacy_name, args=[token])).status_code, 302)

                self.assertFalse(GymVisit.objects.exists())
                self.assertFalse(GymCheckIn.objects.exists())

    def test_unrelated_membership_still_grants_entry_after_cancelling_booking(self):
        booking, session, subscription = self.make_booking()
        unrelated = self.make_unrelated_subscription()
        self.post_cancellation('api_session', booking, session)
        self.api.force_authenticate(self.owner)

        response = self.api.post(
            '/api/v1/owner/check-in/', {'token': str(unrelated.current_qr_token)}, format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        visit = GymVisit.objects.get(customer=self.customer)
        self.assertEqual(visit.subscription_id, unrelated.pk)
        self.assertFalse(GymCheckIn.objects.filter(subscription=subscription).exists())

    def test_other_customer_cannot_cancel_through_any_route(self):
        for route in self.routes:
            with self.subTest(route=route):
                booking, session, subscription = self.make_booking()
                before = self.snapshot(booking, session, subscription)

                response = self.post_cancellation(route, booking, session, user=self.other_customer)

                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_anonymous_requests_cannot_cancel(self):
        booking, session, subscription = self.make_booking()
        before = self.snapshot(booking, session, subscription)
        for name, pk in (
            ('react_cancel_booking', booking.pk), ('react_cancel_session', session.pk),
        ):
            self.assertEqual(self.api.post(reverse(name, args=[pk])).status_code, 401)
        for name, pk in (('cancel_own_booking', booking.pk), ('cancel_session', session.pk)):
            self.assertEqual(self.client.post(reverse(name, args=[pk])).status_code, 302)
        self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_used_or_finished_session_cannot_be_cancelled_through_session_routes(self):
        for route in ('api_session', 'legacy_session'):
            for session_status in (Session.Status.CHECKED_IN, Session.Status.COMPLETED, Session.Status.NO_SHOW):
                with self.subTest(route=route, status=session_status):
                    booking, session, subscription = self.make_booking()
                    session.status = session_status
                    session.qr_used_at = timezone.now()
                    session.checked_in_at = session.qr_used_at
                    session.save(update_fields=['status', 'qr_used_at', 'checked_in_at'])
                    before = self.snapshot(booking, session, subscription)

                    response = self.post_cancellation(route, booking, session)

                    self.assertEqual(response.status_code, 400 if route.startswith('api_') else 302)
                    self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_legacy_owner_cancel_route_still_updates_booking_and_revokes_access(self):
        booking, session, subscription = self.make_booking()
        self.client.force_login(self.owner)

        response = self.client.post(reverse('update_booking_status', args=[booking.pk, 'cancel']))

        self.assertEqual(response.status_code, 302)
        self.assert_cancelled(booking, session, subscription)

    def test_legacy_owner_and_control_cannot_reopen_cancelled_or_rejected_bookings(self):
        for name, actor in (
            ('update_booking_status', self.owner),
            ('control_update_booking_status', self.admin),
        ):
            for close_action in ('cancel', 'reject'):
                with self.subTest(handler=name, closed_by=close_action):
                    booking, session, subscription = self.make_booking(operational=close_action == 'cancel')
                    if close_action == 'cancel':
                        # Exercise actual customer cancellation before an operator tries to restore access.
                        self.assertEqual(
                            self.post_cancellation('api_session', booking, session).status_code, 200,
                        )
                    else:
                        self.client.force_login(actor)
                        self.assertEqual(self.client.post(
                            reverse(name, args=[booking.pk, 'reject']),
                        ).status_code, 302)
                    booking.refresh_from_db()
                    self.assertEqual(
                        booking.status,
                        Booking.Status.CANCELLED if close_action == 'cancel' else Booking.Status.REJECTED,
                    )
                    if subscription:
                        subscription.refresh_from_db()
                        self.assertEqual(subscription.status, GymSubscription.Status.CANCELLED)
                    before = self.snapshot(booking, session, subscription)
                    self.client.force_login(actor)

                    response = self.client.post(reverse(name, args=[booking.pk, 'confirm']))

                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_repeated_legacy_confirmation_preserves_membership_qr_and_access(self):
        for name, actor in (
            ('update_booking_status', self.owner),
            ('control_update_booking_status', self.admin),
        ):
            with self.subTest(handler=name):
                booking, _, _ = self.make_booking(operational=False)
                self.client.force_login(actor)
                url = reverse(name, args=[booking.pk, 'confirm'])
                self.assertEqual(self.client.post(url).status_code, 302)
                session = Session.objects.get(booking=booking)
                subscription = GymSubscription.objects.get(source_booking=booking)
                self.assertTrue(subscription.is_active)
                before = self.snapshot(booking, session, subscription)

                response = self.client.post(url)

                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.snapshot(booking, session, subscription), before)
                self.assertEqual(Session.objects.filter(booking=booking).count(), 1)
                self.assertEqual(GymSubscription.objects.filter(source_booking=booking).count(), 1)

    def test_legacy_control_cannot_return_confirmed_booking_to_pending(self):
        booking, session, subscription = self.make_booking()
        before = self.snapshot(booking, session, subscription)
        self.client.force_login(self.admin)

        response = self.client.post(reverse('control_update_booking_status', args=[booking.pk, 'pending']))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_repeated_cancellation_has_no_further_side_effects(self):
        for route in self.routes:
            with self.subTest(route=route):
                booking, session, subscription = self.make_booking()
                self.post_cancellation(route, booking, session)
                before = self.snapshot(booking, session, subscription)

                response = self.post_cancellation(route, booking, session)

                self.assertEqual(response.status_code, 400 if route.startswith('api_') else 302)
                self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_closed_booking_does_not_revoke_or_rewrite_existing_records(self):
        for route in self.routes:
            for closed_status in (Booking.Status.CANCELLED, Booking.Status.REJECTED):
                with self.subTest(route=route, status=closed_status):
                    booking, session, subscription = self.make_booking()
                    booking.status = closed_status
                    booking.save(update_fields=['status'])
                    before = self.snapshot(booking, session, subscription)

                    response = self.post_cancellation(route, booking, session)

                    self.assertEqual(response.status_code, 400 if route.startswith('api_') else 302)
                    self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_service_scopes_both_identifier_types_to_customer(self):
        booking, session, subscription = self.make_booking()
        before = self.snapshot(booking, session, subscription)
        with self.assertRaises(Booking.DoesNotExist):
            services.cancel_customer_booking(customer=self.other_customer, booking_id=booking.pk)
        with self.assertRaises(Session.DoesNotExist):
            services.cancel_customer_booking(customer=self.other_customer, session_id=session.pk)
        self.assertEqual(self.snapshot(booking, session, subscription), before)

    def test_revocation_failure_rolls_back_booking_session_and_membership(self):
        revoke = services.cancel_operational_records_for_booking

        def revoke_then_fail(*args, **kwargs):
            revoke(*args, **kwargs)
            raise RuntimeError('Simulated revocation failure')

        for route in self.routes:
            with self.subTest(route=route):
                booking, session, subscription = self.make_booking()
                before = self.snapshot(booking, session, subscription)
                with patch('apps.bookings.services.cancel_operational_records_for_booking', side_effect=revoke_then_fail):
                    with self.assertRaisesMessage(RuntimeError, 'Simulated revocation failure'):
                        self.post_cancellation(route, booking, session)
                self.assertEqual(self.snapshot(booking, session, subscription), before)

