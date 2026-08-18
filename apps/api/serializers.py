from rest_framework import serializers

from apps.fitness.models import WorkoutLog
from apps.analytics.demo_seed import TRAFFIC_PROFILES


class DemoAnalyticsSeedRequestSerializer(serializers.Serializer):
    """Request body for generating realistic test/demo analytics data."""

    days = serializers.ChoiceField(
        choices=[30, 90, 120, 180, 360],
        default=120,
        help_text='How far back demo events should be distributed.',
    )
    customers = serializers.IntegerField(
        min_value=1,
        max_value=500,
        default=25,
        help_text='Number of demo customer accounts to ensure before seeding.',
    )
    owner_username = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text='Optional owner username. Leave empty to seed all owner gyms.',
    )
    reset_demo = serializers.BooleanField(
        default=True,
        help_text='If true, deletes only demo analytics records created by the demo tool before seeding fresh data.',
    )
    dry_run = serializers.BooleanField(
        default=False,
        help_text='If true, validates and shows what would run without writing records.',
    )
    subscriptions_per_gym = serializers.IntegerField(min_value=0, max_value=500, default=24)
    bookings_per_gym = serializers.IntegerField(min_value=0, max_value=1000, default=45)
    checkins_per_gym = serializers.IntegerField(min_value=0, max_value=5000, default=220)
    favorites_per_gym = serializers.IntegerField(min_value=0, max_value=1000, default=12)
    workouts_per_customer = serializers.IntegerField(min_value=0, max_value=365, default=18)
    traffic_profile = serializers.ChoiceField(
        choices=TRAFFIC_PROFILES,
        default='balanced',
        help_text=(
            'Arrival pattern used for QR check-ins: balanced, evening-heavy, '
            'morning-heavy, or student. Weekends automatically use a different pattern.'
        ),
    )
    seed = serializers.IntegerField(default=9309, help_text='Random seed for repeatable demo data.')


class EmailProbeRequestSerializer(serializers.Serializer):
    to_email = serializers.EmailField(
        required=False,
        allow_blank=True,
        help_text='Recipient for the test email. Defaults to the current admin user email.',
    )
    subject = serializers.CharField(
        required=False,
        allow_blank=True,
        default='myGym API email probe',
        max_length=160,
    )


class WorkoutLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutLog
        fields = ['id', 'title', 'workout_type', 'duration_minutes', 'logged_at', 'notes', 'source', 'created_at']
        read_only_fields = ['id', 'source', 'created_at']

    def create(self, validated_data):
        request = self.context['request']
        return WorkoutLog.objects.create(
            user=request.user,
            source=WorkoutLog.Source.MANUAL,
            **validated_data,
        )
