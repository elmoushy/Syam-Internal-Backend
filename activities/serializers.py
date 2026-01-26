# activities/serializers.py
"""
Serializers for the Activities system.
Supports chunked operations for large datasets.
"""

from rest_framework import serializers
from django.db import transaction
from .models import (
    ActivityColumnDefinition,
    ActivityColumnValidation,
    ActivityTemplate,
    ActivityTemplateColumn,
    ActivitySheet,
    ActivitySheetRow,
    ActivityRowAttachment,
)
from .constants import MAX_ROWS_PER_REQUEST, MANDATORY_COLUMNS, MANDATORY_COLUMN_KEYS


# ============================================================================
# Column Definition Serializers
# ============================================================================

class ActivityColumnValidationSerializer(serializers.ModelSerializer):
    """Serializer for column validation rules"""
    
    class Meta:
        model = ActivityColumnValidation
        fields = [
            'id', 'rule_type', 'rule_value', 'error_message', 
            'is_active', 'order', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ActivityColumnValidationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating validation rules"""
    
    class Meta:
        model = ActivityColumnValidation
        fields = ['rule_type', 'rule_value', 'error_message', 'is_active', 'order']


class ActivityColumnDefinitionSerializer(serializers.ModelSerializer):
    """Serializer for column definitions with nested validations"""
    
    validations = ActivityColumnValidationSerializer(many=True, read_only=True)
    can_delete = serializers.SerializerMethodField()
    usage_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ActivityColumnDefinition
        fields = [
            'id', 'key', 'label', 'data_type', 'default_width', 'min_width',
            'order', 'is_system', 'is_active', 'options',
            'allows_attachment', 'attachment_required',
            'validations', 'can_delete', 'usage_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_system', 'created_at', 'updated_at']
    
    def get_can_delete(self, obj):
        return obj.can_delete()
    
    def get_usage_count(self, obj):
        return obj.template_usages.count()


class ActivityColumnDefinitionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating column definitions"""
    
    class Meta:
        model = ActivityColumnDefinition
        fields = [
            'key', 'label', 'data_type', 'default_width', 'min_width',
            'order', 'options', 'allows_attachment', 'attachment_required'
        ]
    
    def validate_key(self, value):
        """Ensure key is unique and valid format"""
        if not value.isidentifier():
            raise serializers.ValidationError(
                "Key must be a valid identifier (letters, numbers, underscores, no spaces)"
            )
        if ActivityColumnDefinition.objects.filter(key=value).exists():
            raise serializers.ValidationError(f"Column with key '{value}' already exists")
        return value
    
    def validate_options(self, value):
        """Validate options for select type"""
        if self.initial_data.get('data_type') == 'select':
            if not value or len(value) == 0:
                raise serializers.ValidationError(
                    "Select type columns must have at least one option"
                )
        return value


class ActivityColumnDefinitionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating column definitions"""
    
    class Meta:
        model = ActivityColumnDefinition
        fields = [
            'label', 'data_type', 'default_width', 'min_width',
            'order', 'is_active', 'options', 'allows_attachment', 'attachment_required'
        ]
    
    def validate(self, data):
        """Prevent modifying system columns' key fields"""
        if self.instance and self.instance.is_system:
            # System columns can only update label, width, order, options
            allowed_fields = {'label', 'default_width', 'min_width', 'order', 'options'}
            for field in data.keys():
                if field not in allowed_fields and field != 'is_active':
                    raise serializers.ValidationError(
                        f"Cannot modify '{field}' on system columns"
                    )
        return data


# ============================================================================
# Template Serializers
# ============================================================================

class ActivityTemplateColumnSerializer(serializers.ModelSerializer):
    """Serializer for template columns with nested column definition"""
    
    column_definition = ActivityColumnDefinitionSerializer(read_only=True)
    column_definition_id = serializers.PrimaryKeyRelatedField(
        queryset=ActivityColumnDefinition.objects.filter(is_active=True),
        source='column_definition',
        write_only=True
    )
    effective_width = serializers.SerializerMethodField()
    
    class Meta:
        model = ActivityTemplateColumn
        fields = [
            'id', 'column_definition', 'column_definition_id',
            'order', 'width', 'is_required', 'is_visible', 'effective_width'
        ]
        read_only_fields = ['id']
    
    def get_effective_width(self, obj):
        return obj.get_effective_width()


class ActivityTemplateColumnCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating template columns"""
    
    column_definition_id = serializers.PrimaryKeyRelatedField(
        queryset=ActivityColumnDefinition.objects.filter(is_active=True),
        source='column_definition'
    )
    
    class Meta:
        model = ActivityTemplateColumn
        fields = ['column_definition_id', 'order', 'width', 'is_required', 'is_visible']


class ActivityTemplateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for template listings"""
    
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    column_count = serializers.SerializerMethodField()
    sheet_count = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    
    class Meta:
        model = ActivityTemplate
        fields = [
            'id', 'name', 'description', 'status', 'is_deleted', 'is_active_title',
            'owner', 'owner_name', 'column_count', 'sheet_count', 'can_delete',
            'created_at', 'updated_at', 'published_at'
        ]
        read_only_fields = ['id', 'owner', 'status', 'is_deleted', 'is_active_title', 'created_at', 'updated_at', 'published_at']
    
    def get_column_count(self, obj):
        return obj.template_columns.count()
    
    def get_sheet_count(self, obj):
        return obj.sheets.count()
    
    def get_can_delete(self, obj):
        return obj.can_delete()


class ActivityTemplateDetailSerializer(serializers.ModelSerializer):
    """Full serializer for template details with columns"""
    
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    template_columns = ActivityTemplateColumnSerializer(many=True, read_only=True)
    columns = serializers.SerializerMethodField()  # Simplified columns format for frontend
    can_delete = serializers.SerializerMethodField()
    sheet_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ActivityTemplate
        fields = [
            'id', 'name', 'description', 'notes', 'status', 'is_deleted', 'is_active_title',
            'owner', 'owner_name', 'header_image',
            'template_columns', 'columns', 'can_delete', 'sheet_count',
            'created_at', 'updated_at', 'published_at'
        ]
        read_only_fields = ['id', 'owner', 'status', 'is_deleted', 'created_at', 'updated_at', 'published_at']
    
    def get_columns(self, obj):
        """Return simplified column format for frontend with is_mandatory flag"""
        return [
            {
                'id': tc.column_definition.id,
                'key': tc.column_definition.key,
                'name': tc.column_definition.label,
                'data_type': tc.column_definition.data_type,
                'options': tc.column_definition.options or [],
                'order': tc.order,
                'is_required': tc.is_required,
                'is_visible': tc.is_visible,
                'allows_attachment': tc.column_definition.allows_attachment,
                'attachment_required': tc.column_definition.attachment_required,
                'is_mandatory': tc.column_definition.key in MANDATORY_COLUMN_KEYS or tc.column_definition.is_system
            }
            for tc in obj.template_columns.select_related('column_definition').order_by('order')
        ]
    
    def get_can_delete(self, obj):
        return obj.can_delete()
    
    def get_sheet_count(self, obj):
        return obj.sheets.count()


class ActivityTemplateCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating templates with inline column definitions.
    Columns are created per-template (not global).
    """
    
    # Inline column definitions (not references to existing columns)
    columns = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    
    class Meta:
        model = ActivityTemplate
        fields = ['name', 'description', 'notes', 'header_image', 'columns']
    
    def _generate_key(self, label):
        """Generate a unique key from Arabic/English label."""
        import re
        import unicodedata
        from hashlib import md5
        
        # Normalize and transliterate
        normalized = unicodedata.normalize('NFKD', label)
        # Remove non-ASCII characters and convert to lowercase
        ascii_label = normalized.encode('ascii', 'ignore').decode('ascii').lower()
        
        if ascii_label:
            # Use ASCII version if available
            key = re.sub(r'[^a-z0-9]', '_', ascii_label)
            key = re.sub(r'_+', '_', key).strip('_')
        else:
            # For pure Arabic, use hash
            key = 'col_' + md5(label.encode('utf-8')).hexdigest()[:8]
        
        return key or 'column'
    
    def _ensure_unique_key(self, key, existing_keys):
        """Ensure key is unique by appending suffix if needed."""
        original_key = key
        counter = 1
        while key in existing_keys or ActivityColumnDefinition.objects.filter(key=key).exists():
            key = f"{original_key}_{counter}"
            counter += 1
        return key
    
    def _ensure_mandatory_columns(self, columns_data):
        """
        Ensure mandatory columns are present in the columns list.
        Add them if missing, preserving any user-provided order.
        """
        existing_labels = {col.get('label', '').strip() for col in columns_data}
        existing_keys = set()
        
        # Build set of existing keys (for columns that have explicit keys)
        for col in columns_data:
            if col.get('key'):
                existing_keys.add(col['key'])
        
        # Check for mandatory columns and add if missing
        for mandatory in MANDATORY_COLUMNS:
            mandatory_label = mandatory['label']
            mandatory_key = mandatory['key']
            
            # Check if mandatory column already exists (by label or key)
            found = (
                mandatory_label in existing_labels or
                mandatory_key in existing_keys
            )
            
            if not found:
                # Add mandatory column at the end
                columns_data.append({
                    'label': mandatory_label,
                    'data_type': mandatory['data_type'],
                    'is_required': mandatory.get('is_required', True),
                    'is_mandatory': True,  # Mark as mandatory (cannot be removed)
                    'key': mandatory_key,
                })
        
        return columns_data
    
    def create(self, validated_data):
        columns_data = validated_data.pop('columns', [])
        
        # Ensure mandatory columns are present
        columns_data = self._ensure_mandatory_columns(columns_data)
        
        template = ActivityTemplate.objects.create(**validated_data)
        
        existing_keys = set()
        
        for idx, col_data in enumerate(columns_data):
            # Extract column definition data
            label = col_data.get('label', f'Column {idx + 1}')
            data_type = col_data.get('data_type', 'text')
            options = col_data.get('options', [])
            
            # Use explicit key if provided (for mandatory columns), otherwise generate
            if col_data.get('key'):
                key = col_data['key']
            else:
                key = self._generate_key(label)
            key = self._ensure_unique_key(key, existing_keys)
            existing_keys.add(key)
            
            # Check if this is a mandatory column
            is_mandatory = key in MANDATORY_COLUMN_KEYS or col_data.get('is_mandatory', False)
            
            # Create column definition with fixed widths
            column_def = ActivityColumnDefinition.objects.create(
                key=key,
                label=label,
                data_type=data_type,
                options=options if data_type == 'select' else [],
                default_width=120,  # Fixed default width
                min_width=80,       # Fixed min width
                order=idx,
                is_system=is_mandatory,  # Mark mandatory columns as system columns
                is_active=True,
                allows_attachment=col_data.get('allows_attachment', False),
                attachment_required=col_data.get('attachment_required', False)
            )
            
            # Link to template
            ActivityTemplateColumn.objects.create(
                template=template,
                column_definition=column_def,
                order=idx,
                is_required=col_data.get('is_required', False) or is_mandatory,  # Mandatory columns are always required
                is_visible=True
            )
        
        return template


class ActivityTemplateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating templates"""
    
    # Support inline column updates (only for draft templates)
    columns = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = ActivityTemplate
        fields = ['name', 'description', 'notes', 'header_image', 'status', 'is_active_title', 'columns']
    
    def validate_status(self, value):
        """Validate status transitions"""
        if self.instance:
            current_status = self.instance.status
            # Define allowed transitions
            allowed_transitions = {
                'draft': ['published', 'archived'],
                'published': ['archived'],
                'archived': ['draft'],  # Allow reactivating archived templates
            }
            if value != current_status and value not in allowed_transitions.get(current_status, []):
                raise serializers.ValidationError(
                    f"Cannot transition from '{current_status}' to '{value}'"
                )
        return value
    
    def validate_is_active_title(self, value):
        """Validate is_active_title - only published templates can be active"""
        if value and self.instance:
            # Check if we're also setting status to published in the same request
            new_status = self.initial_data.get('status', self.instance.status)
            if new_status != 'published':
                raise serializers.ValidationError(
                    "Only published templates can be set as active title"
                )
        return value
    
    def validate(self, data):
        if self.instance and self.instance.status != 'draft':
            # Published/archived templates can only update name, description, notes, status, and is_active_title
            if 'header_image' in data:
                raise serializers.ValidationError(
                    "Cannot modify header image on published/archived templates"
                )
            if 'columns' in data:
                raise serializers.ValidationError(
                    "Cannot modify columns on published/archived templates"
                )
        return data
    
    def _generate_key(self, label):
        """Generate a unique key from Arabic/English label."""
        import re
        import unicodedata
        from hashlib import md5
        
        # Normalize and transliterate
        normalized = unicodedata.normalize('NFKD', label)
        # Remove non-ASCII characters and convert to lowercase
        ascii_label = normalized.encode('ascii', 'ignore').decode('ascii').lower()
        
        if ascii_label:
            # Use ASCII version if available
            key = re.sub(r'[^a-z0-9]', '_', ascii_label)
            key = re.sub(r'_+', '_', key).strip('_')
        else:
            # For pure Arabic, use hash
            key = 'col_' + md5(label.encode('utf-8')).hexdigest()[:8]
        
        return key or 'column'
    
    def _ensure_unique_key(self, key, existing_keys):
        """Ensure key is unique by appending suffix if needed."""
        original_key = key
        counter = 1
        while key in existing_keys or ActivityColumnDefinition.objects.filter(key=key).exists():
            key = f"{original_key}_{counter}"
            counter += 1
        return key
    
    def _ensure_mandatory_columns(self, columns_data):
        """
        Ensure mandatory columns are present in the columns list.
        Add them if missing, preserving any user-provided order.
        """
        existing_labels = {col.get('label', '').strip() for col in columns_data}
        existing_keys = set()
        
        # Build set of existing keys (for columns that have explicit keys)
        for col in columns_data:
            if col.get('key'):
                existing_keys.add(col['key'])
        
        # Check for mandatory columns and add if missing
        for mandatory in MANDATORY_COLUMNS:
            mandatory_label = mandatory['label']
            mandatory_key = mandatory['key']
            
            # Check if mandatory column already exists (by label or key)
            found = (
                mandatory_label in existing_labels or
                mandatory_key in existing_keys
            )
            
            if not found:
                # Add mandatory column at the end
                columns_data.append({
                    'label': mandatory_label,
                    'data_type': mandatory['data_type'],
                    'is_required': mandatory.get('is_required', True),
                    'is_mandatory': True,  # Mark as mandatory (cannot be removed)
                    'key': mandatory_key,
                })
        
        return columns_data
    
    def update(self, instance, validated_data):
        """Handle status change, is_active_title exclusivity, and column updates"""
        from django.utils import timezone
        
        columns_data = validated_data.pop('columns', None)
        
        new_status = validated_data.get('status')
        if new_status == 'published' and instance.status == 'draft':
            validated_data['published_at'] = timezone.now()
        
        # Update basic fields (multiple templates can be active now)
        instance = super().update(instance, validated_data)
        
        # Handle column updates (only for draft templates)
        if columns_data is not None and instance.status == 'draft':
            # Ensure mandatory columns are present
            columns_data = self._ensure_mandatory_columns(columns_data)
            
            with transaction.atomic():
                # Get existing column definition IDs to clean up later
                old_column_def_ids = list(
                    instance.template_columns.values_list('column_definition_id', flat=True)
                )
                
                # Remove existing template columns
                instance.template_columns.all().delete()
                
                # Delete old column definitions that were created for this template
                # Only delete non-system columns that are no longer used
                for col_id in old_column_def_ids:
                    col_def = ActivityColumnDefinition.objects.filter(
                        id=col_id, 
                        is_system=False
                    ).first()
                    if col_def and not col_def.template_usages.exists():
                        col_def.delete()
                
                existing_keys = set()
                
                # Create new columns
                for idx, col_data in enumerate(columns_data):
                    label = col_data.get('label', f'Column {idx + 1}')
                    data_type = col_data.get('data_type', 'text')
                    options = col_data.get('options', [])
                    
                    # Use explicit key if provided (for mandatory columns), otherwise generate
                    if col_data.get('key'):
                        key = col_data['key']
                    else:
                        key = self._generate_key(label)
                    key = self._ensure_unique_key(key, existing_keys)
                    existing_keys.add(key)
                    
                    # Check if this is a mandatory column
                    is_mandatory = key in MANDATORY_COLUMN_KEYS or col_data.get('is_mandatory', False)
                    
                    # Create column definition
                    column_def = ActivityColumnDefinition.objects.create(
                        key=key,
                        label=label,
                        data_type=data_type,
                        options=options if data_type == 'select' else [],
                        default_width=120,
                        min_width=80,
                        order=idx,
                        is_system=is_mandatory,  # Mark mandatory columns as system columns
                        is_active=True,
                        allows_attachment=col_data.get('allows_attachment', False),
                        attachment_required=col_data.get('attachment_required', False)
                    )
                    
                    # Link to template
                    ActivityTemplateColumn.objects.create(
                        template=instance,
                        column_definition=column_def,
                        order=idx,
                        is_required=col_data.get('is_required', False) or is_mandatory,  # Mandatory columns are always required
                        is_visible=True
                    )
        
        return instance


class TemplateColumnsUpdateSerializer(serializers.Serializer):
    """
    Serializer for bulk updating template columns.
    Accepts inline column definitions (creates new columns per template).
    """
    
    columns = serializers.ListField(
        child=serializers.DictField(),
        required=True
    )
    
    def validate(self, data):
        template = self.context.get('template')
        if template and template.status != 'draft':
            raise serializers.ValidationError(
                "Cannot modify columns on published/archived templates"
            )
        return data
    
    def _generate_key(self, label):
        """Generate a unique key from Arabic/English label."""
        import re
        import unicodedata
        from hashlib import md5
        
        # Normalize and transliterate
        normalized = unicodedata.normalize('NFKD', label)
        # Remove non-ASCII characters and convert to lowercase
        ascii_label = normalized.encode('ascii', 'ignore').decode('ascii').lower()
        
        if ascii_label:
            # Use ASCII version if available
            key = re.sub(r'[^a-z0-9]', '_', ascii_label)
            key = re.sub(r'_+', '_', key).strip('_')
        else:
            # For pure Arabic, use hash
            key = 'col_' + md5(label.encode('utf-8')).hexdigest()[:8]
        
        return key or 'column'
    
    def _ensure_unique_key(self, key, existing_keys):
        """Ensure key is unique by appending suffix if needed."""
        original_key = key
        counter = 1
        while key in existing_keys or ActivityColumnDefinition.objects.filter(key=key).exists():
            key = f"{original_key}_{counter}"
            counter += 1
        return key
    
    def _ensure_mandatory_columns(self, columns_data):
        """
        Ensure mandatory columns are present in the columns list.
        Add them if missing, preserving any user-provided order.
        """
        existing_labels = {col.get('label', '').strip() for col in columns_data}
        existing_keys = set()
        
        # Build set of existing keys (for columns that have explicit keys)
        for col in columns_data:
            if col.get('key'):
                existing_keys.add(col['key'])
        
        # Check for mandatory columns and add if missing
        for mandatory in MANDATORY_COLUMNS:
            mandatory_label = mandatory['label']
            mandatory_key = mandatory['key']
            
            # Check if mandatory column already exists (by label or key)
            found = (
                mandatory_label in existing_labels or
                mandatory_key in existing_keys
            )
            
            if not found:
                # Add mandatory column at the end
                columns_data.append({
                    'label': mandatory_label,
                    'data_type': mandatory['data_type'],
                    'is_required': mandatory.get('is_required', True),
                    'is_mandatory': True,  # Mark as mandatory (cannot be removed)
                    'key': mandatory_key,
                })
        
        return columns_data
    
    def save(self, template):
        columns_data = self.validated_data['columns']
        
        # Ensure mandatory columns are present
        columns_data = self._ensure_mandatory_columns(columns_data)
        
        with transaction.atomic():
            # Get existing column definition IDs to clean up later
            old_column_def_ids = list(
                template.template_columns.values_list('column_definition_id', flat=True)
            )
            
            # Remove existing template columns
            template.template_columns.all().delete()
            
            # Delete old column definitions that were created for this template
            # Only delete non-system columns that are no longer used
            for col_id in old_column_def_ids:
                col_def = ActivityColumnDefinition.objects.filter(
                    id=col_id, 
                    is_system=False
                ).first()
                if col_def and not col_def.template_usages.exists():
                    col_def.delete()
            
            existing_keys = set()
            
            # Create new columns
            for idx, col_data in enumerate(columns_data):
                label = col_data.get('label', f'Column {idx + 1}')
                data_type = col_data.get('data_type', 'text')
                options = col_data.get('options', [])
                
                # Use explicit key if provided (for mandatory columns), otherwise generate
                if col_data.get('key'):
                    key = col_data['key']
                else:
                    key = self._generate_key(label)
                key = self._ensure_unique_key(key, existing_keys)
                existing_keys.add(key)
                
                # Check if this is a mandatory column
                is_mandatory = key in MANDATORY_COLUMN_KEYS or col_data.get('is_mandatory', False)
                
                # Create column definition
                column_def = ActivityColumnDefinition.objects.create(
                    key=key,
                    label=label,
                    data_type=data_type,
                    options=options if data_type == 'select' else [],
                    default_width=120,
                    min_width=80,
                    order=idx,
                    is_system=is_mandatory,  # Mark mandatory columns as system columns
                    is_active=True,
                    allows_attachment=col_data.get('allows_attachment', False),
                    attachment_required=col_data.get('attachment_required', False)
                )
                
                # Link to template
                ActivityTemplateColumn.objects.create(
                    template=template,
                    column_definition=column_def,
                    order=idx,
                    is_required=col_data.get('is_required', False) or is_mandatory,  # Mandatory columns are always required
                    is_visible=True
                )
        
        return template


# ============================================================================
# Sheet Serializers
# ============================================================================

class ActivitySheetListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for sheet listings"""
    
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)
    
    class Meta:
        model = ActivitySheet
        fields = [
            'id', 'name', 'description', 'template', 'template_name',
            'owner', 'owner_name', 'is_active', 'row_count',
            'is_submitted', 'submitted_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'owner', 'row_count', 'created_at', 'updated_at']


class ActivitySheetDetailSerializer(serializers.ModelSerializer):
    """Full serializer for sheet details"""
    
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True, allow_null=True)
    template_status = serializers.CharField(source='template.status', read_only=True, allow_null=True)
    
    class Meta:
        model = ActivitySheet
        fields = [
            'id', 'name', 'description', 'template', 'template_name', 'template_status',
            'column_snapshot', 'owner', 'owner_name', 
            'is_active', 'row_count',
            'is_submitted', 'submitted_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner', 'column_snapshot', 'row_count', 
            'is_submitted', 'submitted_at',
            'created_at', 'updated_at'
        ]


class ActivitySheetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating sheets from templates"""
    
    template_id = serializers.PrimaryKeyRelatedField(
        queryset=ActivityTemplate.objects.filter(status='published', is_deleted=False),
        source='template'
    )
    
    class Meta:
        model = ActivitySheet
        fields = ['name', 'template_id']
    
    def validate_template_id(self, value):
        if value.status != 'published':
            raise serializers.ValidationError(
                "Can only create sheets from published templates"
            )
        return value
    
    def create(self, validated_data):
        template = validated_data['template']
        
        # Create column snapshot from template
        column_snapshot = []
        for tc in template.template_columns.select_related('column_definition').order_by('order'):
            col_def = tc.column_definition
            column_snapshot.append({
                'key': col_def.key,
                'label': col_def.label,
                'data_type': col_def.data_type,
                'width': tc.get_effective_width(),
                'min_width': col_def.min_width,
                'is_required': tc.is_required,
                'is_visible': tc.is_visible,
                'options': col_def.options,
                'validations': [
                    {
                        'rule_type': v.rule_type,
                        'rule_value': v.rule_value,
                        'error_message': v.error_message
                    }
                    for v in col_def.validations.filter(is_active=True)
                ]
            })
        
        validated_data['column_snapshot'] = column_snapshot
        return super().create(validated_data)


# ============================================================================
# Sheet Row Serializers (with chunked operations support)
# ============================================================================

class ActivitySheetRowSerializer(serializers.ModelSerializer):
    """Serializer for individual rows"""
    
    class Meta:
        model = ActivitySheetRow
        fields = ['id', 'row_number', 'data', 'styles', 'height', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ActivitySheetRowCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a single row"""
    
    class Meta:
        model = ActivitySheetRow
        fields = ['row_number', 'data', 'styles', 'height']
    
    def validate_data(self, value):
        """Validate row data against column snapshot"""
        sheet = self.context.get('sheet')
        if not sheet:
            return value
        
        # Get valid column keys from snapshot
        valid_keys = {col['key'] for col in sheet.column_snapshot}
        
        # Check for invalid keys (warning only, don't reject)
        invalid_keys = set(value.keys()) - valid_keys
        if invalid_keys:
            # Store warning for response but don't fail
            self.context['warnings'] = self.context.get('warnings', [])
            self.context['warnings'].append(f"Unknown columns: {', '.join(invalid_keys)}")
        
        return value


class BulkRowCreateSerializer(serializers.Serializer):
    """
    Serializer for bulk creating rows with chunking support.
    Maximum MAX_ROWS_PER_REQUEST rows per request.
    """
    
    rows = ActivitySheetRowCreateSerializer(many=True)
    chunk_id = serializers.CharField(required=False, allow_blank=True, help_text="For tracking/retry")
    
    def validate_rows(self, value):
        if len(value) > MAX_ROWS_PER_REQUEST:
            raise serializers.ValidationError(
                f"Maximum {MAX_ROWS_PER_REQUEST} rows per request. "
                f"Received {len(value)} rows. Please split into smaller chunks."
            )
        return value
    
    def create(self, validated_data):
        sheet = self.context['sheet']
        rows_data = validated_data['rows']
        chunk_id = validated_data.get('chunk_id', '')
        
        created_rows = []
        errors = []
        
        with transaction.atomic():
            for row_data in rows_data:
                try:
                    row = ActivitySheetRow.objects.create(
                        sheet=sheet,
                        **row_data
                    )
                    created_rows.append(row)
                except Exception as e:
                    errors.append({
                        'row_number': row_data.get('row_number'),
                        'error': str(e)
                    })
        
        # Update sheet row count
        sheet.update_row_count()
        
        return {
            'created': created_rows,
            'errors': errors,
            'chunk_id': chunk_id
        }


class BulkRowUpdateSerializer(serializers.Serializer):
    """
    Serializer for bulk updating rows.
    Maximum MAX_ROWS_PER_REQUEST rows per request.
    """
    
    rows = serializers.ListField(
        child=serializers.DictField(),
        max_length=MAX_ROWS_PER_REQUEST
    )
    chunk_id = serializers.CharField(required=False, allow_blank=True)
    
    def validate_rows(self, value):
        for row in value:
            if 'id' not in row and 'row_number' not in row:
                raise serializers.ValidationError(
                    "Each row must have 'id' or 'row_number' for identification"
                )
        return value
    
    def update(self, sheet, validated_data):
        rows_data = validated_data['rows']
        chunk_id = validated_data.get('chunk_id', '')
        
        updated_rows = []
        errors = []
        
        with transaction.atomic():
            for row_data in rows_data:
                try:
                    row_id = row_data.pop('id', None)
                    row_number = row_data.pop('row_number', None)
                    
                    if row_id:
                        row = sheet.rows.get(id=row_id)
                    else:
                        row = sheet.rows.get(row_number=row_number)
                    
                    # Update fields
                    if 'data' in row_data:
                        row.data = row_data['data']
                    if 'styles' in row_data:
                        row.styles = row_data['styles']
                    if 'height' in row_data:
                        row.height = row_data['height']
                    
                    row.save()
                    updated_rows.append(row)
                    
                except ActivitySheetRow.DoesNotExist:
                    errors.append({
                        'id': row_id,
                        'row_number': row_number,
                        'error': 'Row not found'
                    })
                except Exception as e:
                    errors.append({
                        'id': row_id,
                        'row_number': row_number,
                        'error': str(e)
                    })
        
        return {
            'updated': updated_rows,
            'errors': errors,
            'chunk_id': chunk_id
        }


class BulkRowDeleteSerializer(serializers.Serializer):
    """
    Serializer for bulk deleting rows.
    """
    
    row_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False
    )
    row_numbers = serializers.ListField(
        child=serializers.IntegerField(),
        required=False
    )
    
    def validate(self, data):
        if not data.get('row_ids') and not data.get('row_numbers'):
            raise serializers.ValidationError(
                "Must provide either 'row_ids' or 'row_numbers'"
            )
        return data
    
    def delete(self, sheet):
        row_ids = self.validated_data.get('row_ids', [])
        row_numbers = self.validated_data.get('row_numbers', [])
        
        deleted_count = 0
        
        with transaction.atomic():
            if row_ids:
                deleted_count += sheet.rows.filter(id__in=row_ids).delete()[0]
            if row_numbers:
                deleted_count += sheet.rows.filter(row_number__in=row_numbers).delete()[0]
        
        # Update sheet row count
        sheet.update_row_count()
        
        return {'deleted_count': deleted_count}


# ============================================================================
# Cursor Pagination Serializer for large datasets
# ============================================================================

class RowCursorSerializer(serializers.Serializer):
    """Serializer for cursor-based pagination response"""
    
    rows = ActivitySheetRowSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    prev_cursor = serializers.CharField(allow_null=True)
    total_count = serializers.IntegerField()
    has_more = serializers.BooleanField()


# ============================================================================
# Attachment Serializers
# ============================================================================

class ActivityRowAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for attachment metadata (without file content)"""
    
    download_url = serializers.ReadOnlyField()
    preview_url = serializers.ReadOnlyField()
    
    class Meta:
        model = ActivityRowAttachment
        fields = [
            'id', 'row', 'column_key', 'original_filename', 
            'file_size', 'mime_type', 'is_image',
            'download_url', 'preview_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_image', 'created_at', 'updated_at']


class ActivityRowAttachmentCreateSerializer(serializers.Serializer):
    """Serializer for creating attachments"""
    
    row_id = serializers.IntegerField()
    column_key = serializers.CharField(max_length=100)
    file = serializers.FileField()
    
    def validate_row_id(self, value):
        """Validate row exists"""
        try:
            ActivitySheetRow.objects.get(id=value)
        except ActivitySheetRow.DoesNotExist:
            raise serializers.ValidationError("Row not found")
        return value
    
    def validate_file(self, value):
        """Validate file size (max 10MB)"""
        max_size = 10 * 1024 * 1024  # 10MB
        if value.size > max_size:
            raise serializers.ValidationError("File size must be less than 10MB")
        return value
    
    def create(self, validated_data):
        row = ActivitySheetRow.objects.get(id=validated_data['row_id'])
        file_obj = validated_data['file']
        
        attachment = ActivityRowAttachment.objects.create(
            row=row,
            column_key=validated_data['column_key'],
            original_filename=file_obj.name,
            file_size=file_obj.size,
            mime_type=file_obj.content_type or 'application/octet-stream',
            file_content=file_obj.read()
        )
        
        return attachment
