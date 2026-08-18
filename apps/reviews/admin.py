from django.contrib import admin
from .models import Favorite, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('gym', 'user', 'rating', 'is_visible', 'created_at')
    list_filter = ('rating', 'is_visible')


admin.site.register(Favorite)
