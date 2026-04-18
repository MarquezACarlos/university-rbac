from django.contrib import admin
from .models import StudentProfile, Course, Enrollment, Assignment, Submission, Grade

admin.site.register(StudentProfile)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Assignment)
admin.site.register(Submission)
admin.site.register(Grade)