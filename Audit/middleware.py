"""
Middleware for audit logging.

This middleware injects the current user into thread-local storage
so that signal handlers can access the user who made the request.

IMPORTANT: For DRF views with JWT authentication, the user is not available
in middleware (request.user is AnonymousUser). This middleware provides a
fallback for session-based auth. For DRF, use the AuditMixin in views.
"""

from .signals import set_current_user, get_current_user


class AuditUserMiddleware:
    """
    Middleware to inject current user into thread-local storage.
    
    This allows signal handlers to access the user who made the request
    without passing it explicitly through every function call.
    
    Note: For DRF with JWT auth, the user is set by the view's dispatch method
    via the AuditMixin. This middleware handles session-based auth as fallback.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set current user before processing request
        # This works for session-based auth (Django admin, etc.)
        if hasattr(request, 'user') and request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)
        
        response = self.get_response(request)
        
        # Clear user after processing
        set_current_user(None)
        
        return response


class AuditMixin:
    """
    Mixin for DRF views to set the audit user after authentication.
    
    Add this mixin to your ViewSet or APIView to ensure the audit user
    is set correctly for JWT-authenticated requests.
    
    Usage:
        class MyViewSet(AuditMixin, ModelViewSet):
            ...
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to set audit user after DRF authentication."""
        response = super().dispatch(request, *args, **kwargs)
        return response
    
    def initial(self, request, *args, **kwargs):
        """
        Called after authentication but before the view method.
        This is the right place to set the audit user for DRF views.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        super().initial(request, *args, **kwargs)
        # At this point, DRF has authenticated the user
        if hasattr(request, 'user') and request.user.is_authenticated:
            set_current_user(request.user)
            logger.info(f"[AUDIT MIXIN] Set current user to: {request.user.email}")
        else:
            logger.warning(f"[AUDIT MIXIN] No authenticated user in request")
    
    def finalize_response(self, request, response, *args, **kwargs):
        """Clear the audit user after the response is finalized."""
        import logging
        logger = logging.getLogger(__name__)
        
        response = super().finalize_response(request, response, *args, **kwargs)
        # Clear user after processing
        current = get_current_user()
        logger.info(f"[AUDIT MIXIN] Clearing user (was: {current.email if current else None})")
        set_current_user(None)
        return response
