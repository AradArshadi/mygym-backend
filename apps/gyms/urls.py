from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('explore/', views.gym_list, name='gym_list'),
    path('gyms/<slug:slug>/', views.gym_detail, name='gym_detail'),

    path('owner/gyms/new/', views.owner_gym_create, name='owner_gym_create'),
    path('owner/gyms/<slug:slug>/manage/', views.owner_gym_manage, name='owner_gym_manage'),
    path('owner/gyms/<slug:slug>/edit/', views.owner_gym_edit, name='owner_gym_edit'),
    path('owner/gyms/<slug:slug>/plans/add/', views.owner_plan_add, name='owner_plan_add'),
    path('owner/gyms/<slug:slug>/plans/<int:plan_id>/delete/', views.owner_plan_delete, name='owner_plan_delete'),
    path('owner/gyms/<slug:slug>/trainers/add/', views.owner_trainer_add, name='owner_trainer_add'),
    path('owner/gyms/<slug:slug>/trainers/<int:trainer_id>/delete/', views.owner_trainer_delete, name='owner_trainer_delete'),
    path('owner/gyms/<slug:slug>/photos/add/', views.owner_image_add, name='owner_image_add'),
    path('owner/gyms/<slug:slug>/photos/<int:image_id>/delete/', views.owner_image_delete, name='owner_image_delete'),
]
