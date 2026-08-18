from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkoutGoal(models.Model):
    """A simple weekly consistency goal for a customer.

    The first fitness foundation should motivate healthy weekly consistency rather
    than forcing a daily streak. A goal of 3 workouts/week is realistic for most users.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workout_goal')
    weekly_target = models.PositiveIntegerField(default=3)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return f'{self.user} goal: {self.weekly_target}/week'


class WorkoutLog(models.Model):
    class Source(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        SESSION = 'SESSION', 'Gym session'
        IMPORTED = 'IMPORTED', 'Imported'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workout_logs')
    title = models.CharField(max_length=120, default='Workout')
    workout_type = models.CharField(max_length=80, blank=True, help_text='Strength, Cardio, Yoga, Boxing, etc.')
    notes = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    logged_at = models.DateTimeField(default=timezone.now, db_index=True)
    source = models.CharField(max_length=30, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-logged_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'logged_at']),
            models.Index(fields=['source']),
        ]

    def __str__(self):
        return f'{self.user} · {self.title} · {self.logged_at:%Y-%m-%d}'
