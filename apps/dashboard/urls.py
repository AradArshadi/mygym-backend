from django.urls import path
from . import views

urlpatterns = [
    path('owner/', views.owner_dashboard, name='owner_dashboard'),
    path('owner/analytics/', views.owner_analytics, name='owner_analytics'),
    path('owner/gyms/<int:gym_id>/analytics/', views.owner_gym_analytics, name='owner_gym_analytics'),
    path('customer/', views.customer_dashboard, name='customer_dashboard'),
]
