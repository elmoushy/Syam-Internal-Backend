# activities/permissions.py
"""
Permissions for the Activities system.
"""

from rest_framework import permissions


class IsAdminUser(permissions.BasePermission):
    """
    Permission for admin-only actions (column management).
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class IsTemplateOwner(permissions.BasePermission):
    """
    Permission for template owners.
    Admins can access all templates.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admins can access all
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
        # Admins can access all
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
        # Only admins can edit columns
        if not request.user.is_staff:
            return False
        
        # For DELETE, check if column can be deleted
        if request.method == 'DELETE':
            return obj.can_delete()
        
        return True
