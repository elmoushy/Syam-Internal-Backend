"""
Audit Log Models

This module defines the AuditLog model for tracking critical business actions
across the entire system.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class AuditLog(models.Model):
    """
    Simplified audit log for critical business actions only.
    
    Tracks:
    - Survey CRUD and status changes (create, update, delete, activate, deactivate, submit)
    - Newsletter CRUD (create, update, delete)
    - Role/Permission assignments (role changes, custom role assignments, permission grants/revokes)
    - QuickLinks admin assignments
    """
    
    # Action choices - Critical business actions only
    SURVEY_CREATE = 'SURVEY_CREATE'
    SURVEY_UPDATE = 'SURVEY_UPDATE'
    SURVEY_DELETE = 'SURVEY_DELETE'
    SURVEY_ACTIVATE = 'SURVEY_ACTIVATE'
    SURVEY_DEACTIVATE = 'SURVEY_DEACTIVATE'
    SURVEY_SUBMIT = 'SURVEY_SUBMIT'
    
    NEWSLETTER_CREATE = 'NEWSLETTER_CREATE'
    NEWSLETTER_UPDATE = 'NEWSLETTER_UPDATE'
    NEWSLETTER_DELETE = 'NEWSLETTER_DELETE'
    
    ROLE_ASSIGN = 'ROLE_ASSIGN'
    ROLE_CHANGE = 'ROLE_CHANGE'
    PERMISSION_GRANT = 'PERMISSION_GRANT'
    PERMISSION_REVOKE = 'PERMISSION_REVOKE'
    
    ACTION_CHOICES = [
        # Survey actions
        (SURVEY_CREATE, 'إنشاء استبيان'),
        (SURVEY_UPDATE, 'تحديث استبيان'),
        (SURVEY_DELETE, 'حذف استبيان'),
        (SURVEY_ACTIVATE, 'تفعيل استبيان'),
        (SURVEY_DEACTIVATE, 'إلغاء تفعيل استبيان'),
        (SURVEY_SUBMIT, 'نشر استبيان'),
        
        # Newsletter actions
        (NEWSLETTER_CREATE, 'إنشاء خبر'),
        (NEWSLETTER_UPDATE, 'تحديث خبر'),
        (NEWSLETTER_DELETE, 'حذف خبر'),
        
        # Role/Permission actions
        (ROLE_ASSIGN, 'تعيين دور'),
        (ROLE_CHANGE, 'تغيير دور'),
        (PERMISSION_GRANT, 'منح صلاحية'),
        (PERMISSION_REVOKE, 'سحب صلاحية'),
    ]
    
    # WHO performed the action
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions',
        help_text='User who performed the action (null for system actions)'
    )
    actor_name = models.CharField(
        max_length=255,
        help_text='Cached full name/email for historical tracking'
    )
    
    # WHAT action was performed
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        db_index=True,
        help_text='Type of action performed'
    )
    
    # ON WHAT object (Generic Foreign Key pattern)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Model being affected (e.g., Survey, Newsletter, User)'
    )
    object_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='ID of the affected object (supports UUID and int)'
    )
    object_name = models.CharField(
        max_length=500,
        help_text='Cached object name (survey title, newsletter title, user email)'
    )
    
    # DETAILS of the change
    description = models.TextField(
        help_text='Human-readable description of the action'
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text='Key changes: {"field": {"old": "...", "new": "..."}}'
    )
    
    # WHEN the action occurred
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='When the action occurred (UAE timezone)'
    )
    
    class Meta:
        db_table = 'audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor', '-timestamp'], name='audit_actor_time_idx'),
            models.Index(fields=['action', '-timestamp'], name='audit_action_time_idx'),
            models.Index(fields=['content_type', 'object_id'], name='audit_object_idx'),
        ]
        verbose_name = 'Audit Log Entry'
        verbose_name_plural = 'Audit Log Entries'
    
    def __str__(self):
        return f"{self.actor_name} - {self.get_action_display()} - {self.object_name} at {self.timestamp}"
