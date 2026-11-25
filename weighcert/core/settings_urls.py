from django.urls import path
from . import views

urlpatterns = [
    path("", views.settings_view, name="settings"),
    path("users/<int:user_id>/toggle-active/", views.toggle_user_active, name="toggle_user_active"),
    path("users/<int:user_id>/reset-password/", views.reset_user_password, name="reset_user_password"),
    path("audit/verify/", views.verify_audit_chain_view, name="verify_audit_chain"),
]

