from django.urls import path
from . import views

urlpatterns = [
    path("new/", views.wizard_start_view, name="wizard_start"),
    path("<int:session_id>/step/<str:step>/", views.wizard_step_view, name="wizard_step"),
    path("<int:session_id>/review/", views.test_review_view, name="test_review"),
    path("<int:session_id>/submit/", views.test_submit_view, name="test_submit"),
    path("<int:session_id>/return/", views.test_return_view, name="test_return"),
    path("<int:session_id>/approve/", views.test_approve_view, name="test_approve"),
    path("revise/<int:report_id>/", views.test_revise_view, name="test_revise"),
    path("api/rules/preview/", views.api_rules_preview, name="api_rules_preview"),
]

