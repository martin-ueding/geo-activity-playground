from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("activity/add", views.activity_upload, name="activity-add"),
    path("activity/view/<int:activity_id>", views.activity_view, name="activity-view"),
    path("settings/", views.settings_index, name="settings-index"),
]
