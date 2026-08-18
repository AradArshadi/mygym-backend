from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        OWNER = 'OWNER', 'Gym Owner'
        TRAINER = 'TRAINER', 'Trainer'
        ADMIN = 'ADMIN', 'Admin'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=30, blank=True)

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_trainer(self):
        return self.role == self.Role.TRAINER
