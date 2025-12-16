"""
Serializers for Audit Log API.
"""

from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer for AuditLog model."""
    
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id',
            'actor',
            'actor_name',
            'action',
            'action_display',
            'object_name',
            'description',
            'changes',
            'timestamp',
        ]
        read_only_fields = fields  # All fields are read-only
