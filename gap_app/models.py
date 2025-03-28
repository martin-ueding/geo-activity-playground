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
    elapsed_time = models.DurationField(blank=True, null=True)
    moving_time = models.DurationField(blank=True, null=True)
