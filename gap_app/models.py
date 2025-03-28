from django.contrib.auth.models import User
from django.db import models


class Kind(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
