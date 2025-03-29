import pathlib
import tempfile

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.views.generic.edit import FormView

from gap_app.models import Activity
from gap_app.models import Kind
from geo_activity_playground.core.enrichment import _embellish_single_time_series
from geo_activity_playground.core.enrichment import _get_metadata_from_timeseries
from geo_activity_playground.importers.activity_parsers import read_activity


def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")


def activity_view(request: HttpRequest, activity_id) -> HttpResponse:
    activity = get_object_or_404(Activity, pk=activity_id)
    return render(request, "gap_app/activity_view.html.j2", {"activity": activity})


class ActivityUploadForm(forms.Form):
    def __init__(self, user: User, data=None, files=None) -> None:
        super().__init__(data, files)
        self._user = user

        self.fields["kind"] = forms.ModelChoiceField(
            queryset=Kind.objects.filter(owner_id=self._user),
            to_field_name="name",
            required=False,
            widget=forms.Select(attrs={"class": "form-control"}),
        )

    file = forms.FileField()


def _import_activity_file(request: HttpRequest, f: UploadedFile) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        original_name = f.name
        upload_path = pathlib.Path(tmp_dir) / original_name
        with open(upload_path, "wb") as tmp_file:
            for chunk in f.chunks():
                tmp_file.write(chunk)

        activity_meta, timeseries = read_activity(upload_path)

    timeseries = _embellish_single_time_series(timeseries, None, 0)
    activity_meta.update(_get_metadata_from_timeseries(timeseries))

    activity = Activity(
        owner=request.user,
        name=original_name,
        start=activity_meta.get("start", None),
        distance_km=activity_meta.get("distance_km", 0.0),
        elapsed_time=activity_meta.get("elapsed_time", None),
        moving_time=activity_meta.get("moving_time", None),
        start_latitude=activity_meta.get("start_latitude", None),
        start_longitude=activity_meta.get("start_longitude", None),
        end_latitude=activity_meta.get("end_latitude", None),
        end_longitude=activity_meta.get("end_longitude", None),
        calories=activity_meta.get("calories", None),
        steps=activity_meta.get("steps", None),
        elevation_gain=activity_meta.get("elevation_gain", None),
    )
    activity.save()
    timeseries.to_parquet(activity.timeseries_path)
    return activity


@login_required
def activity_upload(request: HttpRequest):
    if request.method == "POST":
        form = ActivityUploadForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            activity = _import_activity_file(request, request.FILES["file"])
            if (kind := form.cleaned_data["kind"]) is not None:
                activity.kind = kind
                activity.save()
            return redirect("activity-view", activity_id=activity.id)
    else:
        form = ActivityUploadForm(request.user)

    return render(request, "gap_app/activity_add.html.j2", {"form": form})


def settings_index(request):
    return HttpResponse("Not implemented yet.")


def settings_index(request):
    return HttpResponse("Not implemented yet.")
