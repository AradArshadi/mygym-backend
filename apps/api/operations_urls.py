from django.urls import path
from . import operations_views as views

urlpatterns = [
    path('owner/dashboard/', views.OwnerDashboardAPIView.as_view()),
    path('owner/gyms/', views.OwnerGymAPIView.as_view()),
    path('owner/gyms/<int:gym_id>/', views.OwnerGymAPIView.as_view()),
    path('owner/gyms/<int:gym_id>/<str:resource>/', views.OwnerGymResourceAPIView.as_view()),
    path('owner/gyms/<int:gym_id>/<str:resource>/<int:resource_id>/', views.OwnerGymResourceAPIView.as_view()),
    path('operations/bookings/<int:booking_id>/', views.BookingActionAPIView.as_view()),
    path('owner/visits/<int:visit_id>/checkout/', views.OwnerCheckoutAPIView.as_view()),
    path('owner/check-in/', views.OwnerCheckInAPIView.as_view()),
    path('control/overview/', views.ControlOverviewAPIView.as_view()),
    path('control/users/<int:user_id>/', views.ControlUserAPIView.as_view()),
    path('control/gyms/<int:gym_id>/', views.ControlGymAPIView.as_view()),
    path('control/reviews/<int:review_id>/', views.ControlReviewAPIView.as_view()),
    path('control/<str:resource>/', views.ControlListAPIView.as_view()),
]
