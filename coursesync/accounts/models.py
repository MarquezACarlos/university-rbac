from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Roles(models.TextChoices):
        STUDENT = "student", "Student"
        TA = "ta", "Teaching Assistant"
        PROFESSOR = "professor", "Professor"
        ADVISOR = "advisor", "Advisor"
        REGISTRAR = "registrar", "Registrar"
        SYSADMIN = "sysadmin", "System Admin"

    role = models.CharField(max_length=20, choices=Roles.choices)
    university_id = models.CharField(max_length=20, unique=True, null=True, blank=True)

    def is_student(self):
        return self.role == self.Roles.STUDENT

    def is_ta(self):
        return self.role == self.Roles.TA

    def is_professor(self):
        return self.role == self.Roles.PROFESSOR

    def is_advisor(self):
        return self.role == self.Roles.ADVISOR

    def is_registrar(self):
        return self.role == self.Roles.REGISTRAR

    def is_sysadmin(self):
        return self.role == self.Roles.SYSADMIN