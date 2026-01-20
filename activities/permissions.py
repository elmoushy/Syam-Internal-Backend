# activities/permissions.py
"""
Permissions for the Activities system.
"""

from rest_framework import permissions


class IsAdminUser(permissions.BasePermission):
    """
    Permission for admin-only actions.
    Allows users with role 'admin' or 'super_admin'.
    Also checks is_staff for backward compatibility.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Check role-based access (admin or super_admin)
        user_role = getattr(request.user, 'role', None)
        if user_role in ['admin', 'super_admin']:
            return True
        # Fallback to is_staff for backward compatibility
        return request.user.is_staff


class IsTemplateOwner(permissions.BasePermission):
    """
    Permission for template owners.
    Admins can access all templates.
    """
    
    def has_object_permission(self, request, view, obj):
        # Check role-based admin access
        user_role = getattr(request.user, 'role', None)
        if user_role in ['admin', 'super_admin']:
            return True
        # Fallback to is_staff for backward compatibility
        if request.user.is_staff:
            return True
        
        # Owner can access their own
        return obj.owner == request.user


class IsSheetOwner(permissions.BasePermission):
    """
    Permission for sheet owners.
    Admins can access all sheets.
    """
    
    def has_object_permission(self, request, view, obj):
        # Check role-based admin access
        user_role = getattr(request.user, 'role', None)
        if user_role in ['admin', 'super_admin']:
            return True
        # Fallback to is_staff for backward compatibility
        if request.user.is_staff:
            return True
        
        # Owner can access their own
        return obj.owner == request.user


class CanCreateSheetFromTemplate(permissions.BasePermission):
    """
    Permission to create sheets from templates.
    Only published templates can be used.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsColumnDefinitionEditable(permissions.BasePermission):
    """
    Permission for editing column definitions.
    System columns have limited editability.
    """
    
    def has_object_permission(self, request, view, obj):
        # Check role-based admin access
        user_role = getattr(request.user, 'role', None)
        is_admin = user_role in ['admin', 'super_admin'] or request.user.is_staff
        
        # Only admins can edit columns
        if not is_admin:
            return False
        
        # For DELETE, check if column can be deleted
        if request.method == 'DELETE':
            return obj.can_delete()
        
        return True
