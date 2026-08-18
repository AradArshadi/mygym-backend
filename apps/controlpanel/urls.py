from django.urls import path
from . import views

urlpatterns = [
    path('', views.control_overview, name='control_overview'),
    path('users/', views.control_users, name='control_users'),
    path('users/<int:user_id>/toggle-active/', views.toggle_user_active, name='control_toggle_user_active'),
    path('users/<int:user_id>/role/', views.change_user_role, name='control_change_user_role'),
    path('gyms/', views.control_gyms, name='control_gyms'),
    path('gyms/<int:gym_id>/approve/', views.approve_gym, name='control_approve_gym'),
    path('gyms/<int:gym_id>/reject/', views.reject_gym, name='control_reject_gym'),
    path('bookings/', views.control_bookings, name='control_bookings'),
    path('bookings/<int:booking_id>/<str:action>/', views.update_booking_status, name='control_update_booking_status'),
    path('reviews/', views.control_reviews, name='control_reviews'),
    path('logs/', views.control_logs, name='control_logs'),
    path('security/', views.control_security, name='control_security'),
    path('demo-tools/', views.control_demo_tools, name='control_demo_tools'),
    path('reviews/<int:review_id>/toggle/', views.toggle_review_visibility, name='control_toggle_review_visibility'),
]
