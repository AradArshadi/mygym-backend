from django.conf import settings
from django.db import models
from django.urls import reverse


class Notification(models.Model):
    class Kind(models.TextChoices):
        SYSTEM = 'SYSTEM', 'System'
        BOOKING = 'BOOKING', 'Booking'
        REVIEW = 'REVIEW', 'Review'
        GYM = 'GYM', 'Gym'

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=160)
    message = models.TextField()
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient} - {self.title}'
