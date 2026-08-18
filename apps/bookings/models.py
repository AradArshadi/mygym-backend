import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REJECTED = 'REJECTED', 'Rejected'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    gym = models.ForeignKey('gyms.Gym', on_delete=models.CASCADE, related_name='bookings')
    trainer = models.ForeignKey('gyms.TrainerProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    plan = models.ForeignKey('gyms.MembershipPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    booking_datetime = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    customer_note = models.TextField(blank=True)
    payment_status = models.CharField(max_length=30, default='NOT_REQUIRED')
    payment_provider = models.CharField(max_length=40, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['customer', 'gym', 'booking_datetime'], name='unique_customer_gym_booking_time')
        ]

    def __str__(self):
        return f'{self.customer} -> {self.gym} at {self.booking_datetime}'


class Session(models.Model):
    """A confirmed one-time visit created from an accepted booking.

    Booking is the request. Session is the operational visit/check-in record.
    The QR token is one-time-use: after check-in it is marked as used.
    """

    class Status(models.TextChoices):
        UPCOMING = 'UPCOMING', 'Upcoming'
        CHECKED_IN = 'CHECKED_IN', 'Checked in'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        NO_SHOW = 'NO_SHOW', 'No show'

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='session')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions')
    gym = models.ForeignKey('gyms.Gym', on_delete=models.CASCADE, related_name='sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.UPCOMING)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    qr_used_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f'{self.customer} at {self.gym} ({self.start_time:%Y-%m-%d %H:%M})'

    @property
    def is_one_time_qr_available(self):
        return self.status == self.Status.UPCOMING and self.qr_used_at is None and self.cancelled_at is None

    def mark_checked_in(self):
        now = timezone.now()
        self.status = self.Status.CHECKED_IN
        self.checked_in_at = now
        self.qr_used_at = now
        self.save(update_fields=['status', 'checked_in_at', 'qr_used_at', 'updated_at'])
        return GymCheckIn.objects.create(
            customer=self.customer,
            gym=self.gym,
            session=self,
            checkin_type=GymCheckIn.CheckInType.SESSION,
        )

    def cancel(self, reason=''):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancel_reason = reason
        self.save(update_fields=['status', 'cancelled_at', 'cancel_reason', 'updated_at'])


class GymSubscription(models.Model):
    """A customer's membership/access pass for a specific gym.

    The membership QR is valid while the subscription is active, but the token refreshes every 24 hours
    when the user logs in or opens their dashboard/access pass page.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gym_subscriptions')
    gym = models.ForeignKey('gyms.Gym', on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey('gyms.MembershipPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    source_booking = models.OneToOneField(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscription')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField()
    current_qr_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    qr_generated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-end_date', 'gym__name']

    def __str__(self):
        return f'{self.customer} subscription at {self.gym} until {self.end_date}'

    @property
    def is_active(self):
        today = timezone.localdate()
        return self.status == self.Status.ACTIVE and self.start_date <= today <= self.end_date

    @property
    def qr_is_fresh(self):
        return self.qr_generated_at and self.qr_generated_at >= timezone.now() - timedelta(hours=24)

    @property
    def needs_qr_refresh(self):
        return not self.qr_is_fresh

    def refresh_qr_if_needed(self, *, force=False):
        if force or self.needs_qr_refresh:
            self.current_qr_token = uuid.uuid4()
            self.qr_generated_at = timezone.now()
            self.save(update_fields=['current_qr_token', 'qr_generated_at', 'updated_at'])
        return self

    def mark_expired_if_needed(self):
        if self.status == self.Status.ACTIVE and self.end_date < timezone.localdate():
            self.status = self.Status.EXPIRED
            self.save(update_fields=['status', 'updated_at'])
        return self

    @property
    def days_remaining(self):
        return max((self.end_date - timezone.localdate()).days, 0)


class GymVisit(models.Model):
    """A live customer presence at a gym, from check-in until check-out."""

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        EXPIRED = 'EXPIRED', 'Expired'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class EntryMethod(models.TextChoices):
        SESSION_QR = 'SESSION_QR', 'Session QR'
        MEMBERSHIP_QR = 'MEMBERSHIP_QR', 'Membership QR'
        MANUAL = 'MANUAL', 'Manual'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gym_visits')
    gym = models.ForeignKey('gyms.Gym', on_delete=models.CASCADE, related_name='visits')
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    subscription = models.ForeignKey(GymSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='visits')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    entry_method = models.CharField(max_length=24, choices=EntryMethod.choices)
    checked_in_at = models.DateTimeField(default=timezone.now, db_index=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='gym_visits_started')
    checked_out_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='gym_visits_finished')
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-checked_in_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer'],
                condition=models.Q(status='ACTIVE'),
                name='one_active_gym_visit_per_customer',
            ),
        ]
        indexes = [models.Index(fields=['gym', 'status', '-checked_in_at'], name='bookings_gy_gym_id_8384b0_idx')]

    def __str__(self):
        return f'{self.customer} at {self.gym} ({self.status})'

    @property
    def duration_seconds(self):
        end = self.checked_out_at or timezone.now()
        return max(int((end - self.checked_in_at).total_seconds()), 0)

    @property
    def duration_minutes(self):
        return self.duration_seconds // 60


class GymCheckIn(models.Model):
    """Attendance/check-in log for both one-time sessions and membership access passes."""

    class CheckInType(models.TextChoices):
        SESSION = 'SESSION', 'Session'
        MEMBERSHIP = 'MEMBERSHIP', 'Membership'

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gym_checkins')
    gym = models.ForeignKey('gyms.Gym', on_delete=models.CASCADE, related_name='checkins')
    session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True, related_name='checkins')
    subscription = models.ForeignKey(GymSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='checkins')
    checkin_type = models.CharField(max_length=20, choices=CheckInType.choices)
    checked_in_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-checked_in_at']

    def __str__(self):
        return f'{self.customer} checked in at {self.gym} ({self.checkin_type})'
