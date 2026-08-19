from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model.

    Swapped in from day one so the project can grow profile fields later
    without a painful migration. Email is unique because it identifies a guest
    for booking confirmations.
    """

    email = models.EmailField("email address", unique=True)

    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username
