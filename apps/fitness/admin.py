from django.contrib import admin

from .models import WorkoutGoal, WorkoutLog


@admin.register(WorkoutGoal)
class WorkoutGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'weekly_target', 'updated_at')
    search_fields = ('user__username', 'user__email')


@admin.register(WorkoutLog)
class WorkoutLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'workout_type', 'duration_minutes', 'logged_at', 'source')
    list_filter = ('source', 'workout_type', 'logged_at')
    search_fields = ('user__username', 'user__email', 'title', 'workout_type')
