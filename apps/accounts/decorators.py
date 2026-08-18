from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
def owner_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request,*args,**kwargs):
        if not (getattr(request.user,"is_owner",False) or getattr(request.user,"is_platform_admin",False)):
            raise PermissionDenied("Only gym owners can access this page.")
        return view_func(request,*args,**kwargs)
    return wrapper
def platform_admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request,*args,**kwargs):
        if not getattr(request.user,"is_platform_admin",False):
            raise PermissionDenied("Only platform admins can access this page.")
        return view_func(request,*args,**kwargs)
    return wrapper
