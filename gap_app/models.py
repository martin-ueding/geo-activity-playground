import datetime
import pathlib
from typing import Optional

from django.contrib.auth.models import User
from django.db import models

from gap_site.settings import DATA_DIR


class Kind(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Equipment(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    purchase_date = models.DateField(blank=True, null=True)

    def __str__(self) -> str:
        if self.purchase_date is None:
            return self.name
        else:
            return f"{self.name} ({self.purchase_date.year})"


class Activity(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=500)
    kind = models.ForeignKey(Kind, blank=True, null=True, on_delete=models.CASCADE)
    equipment = models.ForeignKey(
        Equipment, blank=True, null=True, on_delete=models.CASCADE
    )
    start = models.DateTimeField(blank=True, null=True)
    distance_km = models.FloatField(default=0.0)
    elapsed_time = models.DurationField(blank=True, null=True)
    moving_time = models.DurationField(blank=True, null=True)

    start_latitude = models.FloatField(blank=True, null=True)
    start_longitude = models.FloatField(blank=True, null=True)
    end_latitude = models.FloatField(blank=True, null=True)
    end_longitude = models.FloatField(blank=True, null=True)

    calories = models.FloatField(blank=True, null=True)
    steps = models.IntegerField(blank=True, null=True)
    elevation_gain = models.FloatField(blank=True, null=True)

    def __str__(self):
        return self.name

    @property
    def average_speed_elapsed_kmh(self) -> Optional[float]:
        if self.elapsed_time is not None:
            return self.distance_km / (self.elapsed_time.total_seconds() / 3600)

    @property
    def pace_elapsed(self) -> Optional[datetime.timedelta]:
        if self.elapsed_time is not None:
            return self.elapsed_time / self.distance_km

    @property
    def average_speed_moving_kmh(self) -> Optional[float]:
        if self.moving_time is not None:
            return self.distance_km / (self.moving_time.total_seconds() / 3600)

    @property
    def pace_moving(self) -> Optional[datetime.timedelta]:
        if self.elapsed_time is not None:
            return self.moving_time / self.distance_km

    @property
    def timeseries_path(self) -> pathlib.Path:
        directory = DATA_DIR / "Activity Time Series"
        directory.mkdir(exist_ok=True)
        return directory / f"{self.id}.parquet"
