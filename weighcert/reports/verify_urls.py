from django.urls import path
from . import views

urlpatterns = [
    path("", views.public_verify_view, name="public_verify_home"),
    path("<str:token>/", views.public_verify_view, name="public_verify"),
]

