from django.urls import path
from . import react_views

urlpatterns = [
    path('auth/csrf/', react_views.CsrfAPIView.as_view(), name='react_api_csrf'),
    path('auth/login/', react_views.LoginAPIView.as_view(), name='react_api_login'),
    path('auth/logout/', react_views.LogoutAPIView.as_view(), name='react_api_logout'),
    path('auth/me/', react_views.MeAPIView.as_view(), name='react_api_me'),
    path('dashboard/', react_views.ReactDashboardAPIView.as_view(), name='react_api_dashboard'),
    path('gyms/', react_views.ReactGymListAPIView.as_view(), name='react_api_gym_list'),
    path('gyms/<slug:slug>/', react_views.ReactGymDetailAPIView.as_view(), name='react_api_gym_detail'),
    path('gyms/<slug:slug>/favorite/', react_views.ReactGymFavoriteAPIView.as_view(), name='react_api_gym_favorite'),
    path('gyms/<slug:slug>/bookings/', react_views.ReactBookingAPIView.as_view(), name='react_api_booking'),
]
