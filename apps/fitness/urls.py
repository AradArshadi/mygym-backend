from django.urls import path

from . import views

urlpatterns = [
    path('', views.fitness_home, name='fitness_home'),
    path('log/', views.log_workout, name='log_workout'),
    path('history/', views.workout_history, name='workout_history'),
    path('goal/', views.update_goal, name='update_workout_goal'),
    path('discover/', views.discover, name='discover'),
    path('chat/', views.chat_home, name='chat_home'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/', views.profile_hub, name='profile_hub'),
    path('more/', views.more_menu, name='more_menu'),
]
