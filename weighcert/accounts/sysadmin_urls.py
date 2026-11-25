"""URL patterns for the System Administrator panel."""
from django.urls import path
from . import sysadmin_views as v

urlpatterns = [
    path("",             v.sysadmin_dashboard,          name="sysadmin_dashboard"),
    path("users/new/",   v.sysadmin_create_user,        name="sysadmin_create_user"),
    path("users/<int:user_id>/edit/",   v.sysadmin_edit_user,   name="sysadmin_edit_user"),
    path("users/<int:user_id>/toggle/", v.sysadmin_toggle_user, name="sysadmin_toggle_user"),
    path("users/<int:user_id>/delete/", v.sysadmin_delete_user, name="sysadmin_delete_user"),
    path("change-master-key/",          v.sysadmin_change_own_password, name="sysadmin_change_password"),
]
