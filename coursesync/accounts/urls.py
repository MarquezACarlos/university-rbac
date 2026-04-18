from django.urls import path
from .views import login_view, logout_view, dashboard_router

urlpatterns = [
    path("", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("dashboard/", dashboard_router, name="dashboard_router"),
]