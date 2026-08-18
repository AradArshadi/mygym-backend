from django.conf import settings
from django.db import models


class SystemLog(models.Model):
    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        CRITICAL = 'CRITICAL', 'Critical'

    class Category(models.TextChoices):
        AUTH = 'AUTH', 'Authentication'
        EMAIL = 'EMAIL', 'Email'
        BOOKING = 'BOOKING', 'Booking'
        GYM = 'GYM', 'Gym'
        REVIEW = 'REVIEW', 'Review'
        ADMIN = 'ADMIN', 'Admin'
        NOTIFICATION = 'NOTIFICATION', 'Notification'
        SESSION = 'SESSION', 'Session'
        SUBSCRIPTION = 'SUBSCRIPTION', 'Subscription'
        CHECKIN = 'CHECKIN', 'Check-in'
        SYSTEM = 'SYSTEM', 'System'

    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.SYSTEM)
    event = models.CharField(max_length=120)
    message = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='system_logs')
    related_model = models.CharField(max_length=80, blank=True)
    related_id = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['level', 'category']),
            models.Index(fields=['created_at']),
            models.Index(fields=['event']),
        ]

    def __str__(self):
        return f'{self.level} · {self.category} · {self.event}'
