CourseSync Django Template Conversion

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
