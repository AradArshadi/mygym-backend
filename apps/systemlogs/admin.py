from django.contrib import admin
from .models import SystemLog


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'level', 'category', 'event', 'actor', 'related_model', 'related_id')
    list_filter = ('level', 'category', 'created_at')
    search_fields = ('event', 'message', 'actor__username', 'actor__email', 'related_model', 'related_id')
    readonly_fields = ('created_at',)
