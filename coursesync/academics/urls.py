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
    create_course,
    edit_course,
    delete_course,
    create_user,
    create_major,
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

    path("courses/new/", create_course, name="create_course"),
    path("courses/<int:course_id>/edit/", edit_course, name="edit_course"),
    path("courses/<int:course_id>/delete/", delete_course, name="delete_course"),

    path("users/new/", create_user, name="create_user"),
    path("students/new/", create_user, name="create_student"),
    path("majors/new/", create_major, name="create_major"),
]