from django.urls import path
from . import views

urlpatterns = [
    path("", views.instrument_list_view, name="instrument_list"),
    path("new/", views.instrument_create_view, name="instrument_create"),
    path("<str:instrument_id>/", views.instrument_detail_view, name="instrument_detail"),
    path("<str:instrument_id>/edit/", views.instrument_edit_view, name="instrument_edit"),
    path("api/validate/", views.instrument_validate_api, name="instrument_validate_api"),
    path("api/owner/new/", views.owner_create_inline, name="owner_create_inline"),
]

