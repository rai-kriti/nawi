from django.urls import path
from . import views

urlpatterns = [
    path("", views.weight_list_view, name="weight_list"),
    path("new/", views.weight_create_view, name="weight_create"),
    path("<int:weight_id>/toggle/", views.weight_toggle_view, name="weight_toggle"),
]

