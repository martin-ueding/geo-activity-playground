import pathlib
from typing import Optional

from django.contrib.auth.models import User
from django.db import models


class Kind(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name


class Equipment(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, unique=True)
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

    @property
    def average_speed_elapsed_kmh(self) -> Optional[float]:
        if self.elapsed_time is not None:
            return self.distance_km / self.elapsed_time

    @property
    def average_speed_moving_kmh(self) -> Optional[float]:
        if self.moving_time is not None:
            return self.distance_km / self.moving_time

    @property
    def timeseries_path(self) -> pathlib.Path:
        return pathlib.Path(f"{self.id}.parquet")
