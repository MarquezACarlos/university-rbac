CourseSync Django Template Conversion

*IMPORTANT*
Delete the file called "db.sqlite3"

HOW TO RUN:
cd into coursesync
python -m venv .venv                *not necessary*
.venv\Scripts\activate              *not necessary*
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver


CREATE A SUPERUSER
python manage.py createsuperuser

CREATE SAMPLE ROLE USERS
python manage.py shell

from accounts.models import User

User.objects.create_user(username="student1", password="test1234", role="student")
User.objects.create_user(username="prof1", password="test1234", role="professor")
User.objects.create_user(username="advisor1", password="test1234", role="advisor")
User.objects.create_user(username="registrar1", password="test1234", role="registrar")
User.objects.create_user(username="sysadmin1", password="test1234", role="sysadmin")
exit()

Role passwords:
Admin: admin
advisors: advisor123!
professor: professor123!
registrar: registrar123!



Contents
- templates/
  - base.html
  - login.html
  - student.html
  - professor.html
  - advisor.html
  - registrar.html
  - sysadmin.html
- static/css/
  - coursesync-core.css
  - login.css
  - student.css
  - professor.css
  - advisor.css
  - registrar.css
  - sysadmin.css
- static/js/
  - login.js

How to use
1. Copy the templates folder into your Django project's templates directory.
2. Copy the static folder into your Django project's static directory.
3. Confirm these settings exist in settings.py:
   TEMPLATES['DIRS'] includes BASE_DIR / 'templates'
   STATIC_URL = 'static/'
4. Add django.contrib.staticfiles to INSTALLED_APPS.
5. The login template expects a POST endpoint on the current route and uses field names: username, password.
6. The dashboard templates are now Django-ready and can reference request.user values.

Notes
- The original inline CSS from each uploaded page was moved into a dedicated page stylesheet.
- The login page was converted from button-based mockup behavior into a real HTML form with CSRF support.
- Most dashboard content remains placeholder/demo data from your mockups, but the user badge/footer areas now use Django template variables.
- Links that were originally '#' remain placeholders unless they were clearly the main dashboard entry.
