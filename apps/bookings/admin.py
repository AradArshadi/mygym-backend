from django.contrib import admin

from .models import Booking, GymCheckIn, GymSubscription, GymVisit, Session


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'gym', 'booking_datetime', 'status', 'plan', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('customer__username', 'customer__email', 'gym__name')


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'gym', 'start_time', 'status', 'checked_in_at', 'qr_used_at')
    list_filter = ('status', 'start_time', 'created_at')
    search_fields = ('customer__username', 'customer__email', 'gym__name', 'qr_token')
    readonly_fields = ('qr_token', 'qr_used_at', 'checked_in_at', 'created_at', 'updated_at')


@admin.register(GymSubscription)
class GymSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'gym', 'plan', 'status', 'start_date', 'end_date', 'qr_generated_at')
    list_filter = ('status', 'start_date', 'end_date', 'created_at')
    search_fields = ('customer__username', 'customer__email', 'gym__name', 'current_qr_token')
    readonly_fields = ('current_qr_token', 'qr_generated_at', 'created_at', 'updated_at')


@admin.register(GymCheckIn)
class GymCheckInAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'gym', 'checkin_type', 'checked_in_at')
    list_filter = ('checkin_type', 'checked_in_at')
    search_fields = ('customer__username', 'customer__email', 'gym__name')
    readonly_fields = ('checked_in_at',)


@admin.register(GymVisit)
class GymVisitAdmin(admin.ModelAdmin):
    list_display = ('customer', 'gym', 'status', 'entry_method', 'checked_in_at', 'checked_out_at')
    list_filter = ('status', 'entry_method', 'gym')
    search_fields = ('customer__username', 'customer__email', 'gym__name')
    readonly_fields = ('checked_in_at', 'checked_out_at', 'created_at', 'updated_at')
