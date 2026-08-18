from django.urls import path
from . import views

urlpatterns = [
    path('create/<int:gym_id>/', views.create_review, name='create_review'),
    path('favorite/<int:gym_id>/toggle/', views.toggle_favorite, name='toggle_favorite'),
]
