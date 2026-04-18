from django.urls import path
from .views import (
    student_dashboard,
    professor_dashboard,
    advisor_dashboard,
    registrar_dashboard,
    sysadmin_dashboard,
    propose_enrollment,
    approve_enrollment,
    deny_enrollment,
)

urlpatterns = [
    path("student/", student_dashboard, name="student_dashboard"),
    path("professor/", professor_dashboard, name="professor_dashboard"),
    path("advisor/", advisor_dashboard, name="advisor_dashboard"),
    path("registrar/", registrar_dashboard, name="registrar_dashboard"),
    path("sysadmin/", sysadmin_dashboard, name="sysadmin_dashboard"),

    path("enroll/<int:course_id>/", propose_enrollment, name="propose_enrollment"),
    path("approve/<int:enrollment_id>/", approve_enrollment, name="approve_enrollment"),
    path("deny/<int:enrollment_id>/", deny_enrollment, name="deny_enrollment"),
]