from django import forms
from django.utils import timezone

from .models import WorkoutGoal, WorkoutLog


class WorkoutLogForm(forms.ModelForm):
    logged_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text='Leave empty to log it for right now.',
    )

    class Meta:
        model = WorkoutLog
        fields = ['title', 'workout_type', 'duration_minutes', 'logged_at', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4, 'placeholder': 'How did the workout feel?'}),
        }

    def clean_logged_at(self):
        logged_at = self.cleaned_data.get('logged_at')
        if not logged_at:
            return timezone.now()
        if timezone.is_naive(logged_at):
            return timezone.make_aware(logged_at, timezone.get_current_timezone())
        return logged_at


class WorkoutGoalForm(forms.ModelForm):
    class Meta:
        model = WorkoutGoal
        fields = ['weekly_target']
        widgets = {
            'weekly_target': forms.NumberInput(attrs={'min': 1, 'max': 14}),
        }


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        from django.contrib.auth import get_user_model
        model = get_user_model()
        fields = ['username', 'email', 'first_name', 'last_name', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={'autocomplete': 'username'}),
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'first_name': forms.TextInput(attrs={'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={'autocomplete': 'family-name'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel'}),
        }
