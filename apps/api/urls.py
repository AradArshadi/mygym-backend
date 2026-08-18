from django.urls import include, path

from . import views

urlpatterns = [
    path("v1/", include("apps.api.customer_urls")),
    # Demo / internal control tools
    path('demo/status/', views.DemoStatusAPIView.as_view(), name='api_demo_status'),
    path('demo/seed-analytics/', views.DemoSeedAnalyticsAPIView.as_view(), name='api_demo_seed_analytics'),
    path('demo/reset-analytics/', views.DemoResetAnalyticsAPIView.as_view(), name='api_demo_reset_analytics'),

    # Owner analytics
    path('owner/analytics/', views.OwnerPortfolioAnalyticsAPIView.as_view(), name='api_owner_analytics'),
    path('owner/gyms/<int:gym_id>/analytics/', views.OwnerGymAnalyticsAPIView.as_view(), name='api_owner_gym_analytics'),

    # Customer/explore APIs
    path('gyms/', views.GymListAPIView.as_view(), name='api_gym_list'),
    path('gyms/<slug:slug>/', views.GymDetailAPIView.as_view(), name='api_gym_detail'),
    path('gyms/<slug:slug>/favorite/', views.GymFavoriteAPIView.as_view(), name='api_gym_favorite'),
    path('gyms/<slug:slug>/images/', views.GymImageListCreateAPIView.as_view(), name='api_gym_images'),
    path('gyms/<slug:slug>/images/<int:image_id>/', views.GymImageDeleteAPIView.as_view(), name='api_gym_image_delete'),

    # Fitness APIs
    path('fitness/summary/', views.FitnessSummaryAPIView.as_view(), name='api_fitness_summary'),
    path('fitness/activity/', views.FitnessActivityAPIView.as_view(), name='api_fitness_activity'),
    path('fitness/workouts/', views.WorkoutLogListCreateAPIView.as_view(), name='api_fitness_workouts'),

    # Safety / diagnostics
    path('security/status/', views.SecurityStatusAPIView.as_view(), name='api_security_status'),
    path('email/config/', views.EmailConfigAPIView.as_view(), name='api_email_config'),
    path('email/probe/', views.EmailProbeAPIView.as_view(), name='api_email_probe'),
]
