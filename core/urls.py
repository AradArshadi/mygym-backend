from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('fitness/', include('apps.fitness.urls')),
    path('', include('apps.gyms.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('reviews/', include('apps.reviews.urls')),
    path('control/', include('apps.controlpanel.urls')),
    path('api/', include('apps.api.urls')),
    path('api/schema/', staff_member_required(SpectacularAPIView.as_view()), name='api_schema'),
    path('api/docs/', staff_member_required(SpectacularSwaggerView.as_view(url_name='api_schema')), name='api_docs'),
    path('api/redoc/', staff_member_required(SpectacularRedocView.as_view(url_name='api_schema')), name='api_redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
