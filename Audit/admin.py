"""
Django Admin configuration for Audit Log.
"""

from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for viewing audit logs.
    
    Audit logs cannot be manually created, edited, or deleted.
    """
    
    list_display = [
        'timestamp',
        'actor_name',
        'action',
        'object_name',
    ]
    
    list_filter = [
        'action',
        'timestamp',
    ]
    
    search_fields = [
        'actor_name',
        'object_name',
        'description',
    ]
    
    readonly_fields = [
        'actor',
        'actor_name',
        'action',
        'content_type',
        'object_id',
        'object_name',
        'description',
        'changes',
        'timestamp',
    ]
    
    # Disable add permission
    def has_add_permission(self, request):
        """Audit logs cannot be manually created."""
        return False
    
    # Disable delete permission
    def has_delete_permission(self, request, obj=None):
        """Audit logs cannot be deleted."""
        return False
    
    # Disable change permission
    def has_change_permission(self, request, obj=None):
        """Audit logs cannot be edited."""
        return False
    
    # Custom display for changes field
    def get_readonly_fields(self, request, obj=None):
        """Make all fields readonly."""
        return self.readonly_fields
