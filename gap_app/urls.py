from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("activity/add", views.activity_upload, name="activity-add"),
    path("settings/", views.settings_index, name="settings-index"),
]
