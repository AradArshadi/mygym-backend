from django.urls import path
from . import customer_views as views
from . import views as core_views
from .v1_gym_views import V1GymDetailAPIView

urlpatterns = [
    path('auth/csrf/', views.CsrfAPIView.as_view(), name='react_csrf'),
    path('auth/me/', views.MeAPIView.as_view(), name='react_me'),
    path('auth/login/', views.LoginAPIView.as_view(), name='react_login'),
    path('auth/logout/', views.LogoutAPIView.as_view(), name='react_logout'),
    path('customer/home/', views.CustomerHomeAPIView.as_view(), name='react_customer_home'),
    path('customer/visit/', views.CustomerVisitAPIView.as_view(), name='react_customer_visit'),
    path('customer/visits/<int:visit_id>/checkout/', views.CheckoutVisitAPIView.as_view(), name='react_checkout_visit'),
    path('customer/memberships/<int:subscription_id>/refresh/', views.RefreshMembershipAPIView.as_view(), name='react_refresh_membership'),
    path('customer/sessions/<int:session_id>/cancel/', views.CancelSessionAPIView.as_view(), name='react_cancel_session'),
    path('customer/bookings/<int:booking_id>/cancel/', views.CancelBookingAPIView.as_view(), name='react_cancel_booking'),
    path('customer/profile/', views.ProfileAPIView.as_view(), name='react_profile'),
    path('customer/bookings/', views.CustomerBookingsAPIView.as_view(), name='react_customer_bookings'),
    path('customer/favorites/', views.CustomerFavoritesAPIView.as_view(), name='react_customer_favorites'),
    path('customer/notifications/', views.CustomerNotificationsAPIView.as_view(), name='react_customer_notifications'),
    path('customer/notifications/read-all/', views.CustomerNotificationsReadAllAPIView.as_view(), name='react_customer_notifications_read_all'),
    path('customer/notifications/<int:notification_id>/read/', views.CustomerNotificationReadAPIView.as_view(), name='react_customer_notification_read'),
    path('customer/settings/', views.CustomerSettingsAPIView.as_view(), name='react_customer_settings'),
    path('gyms/<slug:slug>/bookings/', views.GymBookingAPIView.as_view(), name='react_gym_booking'),
    path('gyms/<slug:slug>/reviews/', views.GymReviewAPIView.as_view(), name='react_gym_review'),

    # Public gym + fitness endpoints exposed through the same v1 contract used by React.
    path('gyms/', core_views.GymListAPIView.as_view(), name='v1_gym_list'),
    path('gyms/<slug:slug>/', V1GymDetailAPIView.as_view(), name='v1_gym_detail'),
    path('gyms/<slug:slug>/favorite/', core_views.GymFavoriteAPIView.as_view(), name='v1_gym_favorite'),
    path('fitness/summary/', core_views.FitnessSummaryAPIView.as_view(), name='v1_fitness_summary'),
    path('fitness/activity/', core_views.FitnessActivityAPIView.as_view(), name='v1_fitness_activity'),
    path('fitness/workouts/', core_views.WorkoutLogListCreateAPIView.as_view(), name='v1_fitness_workouts'),
]
