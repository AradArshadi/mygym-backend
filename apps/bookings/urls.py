from django.urls import path
from . import views

urlpatterns = [
    path('sessions/', views.my_sessions, name='my_sessions'),
    path('sessions/<int:session_id>/', views.session_detail, name='session_detail'),
    path('sessions/<int:session_id>/cancel/', views.cancel_session, name='cancel_session'),
    path('sessions/check-in/<uuid:token>/', views.session_check_in, name='session_check_in'),
    path('memberships/', views.my_memberships, name='my_memberships'),
    path('memberships/<int:subscription_id>/refresh-qr/', views.refresh_membership_qr, name='refresh_membership_qr'),
    path('memberships/check-in/<uuid:token>/', views.membership_check_in, name='membership_check_in'),
    path('visits/<int:visit_id>/checkout/', views.checkout_visit, name='checkout_visit'),
    path('create/<int:gym_id>/', views.create_booking, name='create_booking'),
    path('<int:booking_id>/cancel/', views.cancel_own_booking, name='cancel_own_booking'),
    path('<int:booking_id>/status/<str:status>/', views.update_booking_status, name='update_booking_status'),
    # Retain older confirm/reject links; cancellation has its own customer URL.
    path('<int:booking_id>/<str:status>/', views.update_booking_status, name='legacy_update_booking_status'),
]
