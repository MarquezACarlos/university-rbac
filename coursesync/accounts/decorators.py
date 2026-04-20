from functools import wraps
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied
            # Allow access if the user has the required role 
            # OR if they are a sysadmin (to support impersonation)
            if request.user.role in allowed_roles or request.user.role == 'sysadmin':
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator