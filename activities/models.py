# activities/models.py
"""
Models for the Dynamic Activities Template System.

Architecture:
- ActivityColumnDefinition: Global column definitions (admin-managed)
- ActivityColumnValidation: Validation rules per column
- ActivityTemplate: User templates (draft/published/archived)
- ActivityTemplateColumn: Column config per template
- ActivitySheet: User's saved spreadsheet data
- ActivitySheetRow: Row data with chunked operations support
"""

from django.db import models
from django.conf import settings
from django.utils import timezone


class ActivityColumnDefinition(models.Model):
    """
    Global column definitions managed by admin.
    System columns (is_system=True) are created by migration and cannot be deleted.
    """
    
    DATA_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Yes/No'),
        ('select', 'Dropdown'),
    ]
    
    key = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Unique identifier for the column (e.g., 'activityType')"
    )
    label = models.CharField(
        max_length=255,
        help_text="Display label for the column"
    )
    data_type = models.CharField(
        max_length=20, 
        choices=DATA_TYPE_CHOICES, 
        default='text'
    )
    default_width = models.PositiveIntegerField(default=120)
    min_width = models.PositiveIntegerField(default=80)
    order = models.PositiveIntegerField(default=0)
    is_system = models.BooleanField(
        default=False,
        help_text="System columns cannot be deleted"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft delete flag"
    )
    options = models.JSONField(
        default=list, 
        blank=True,
        help_text="Options for 'select' data type"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Column Definition'
        verbose_name_plural = 'Column Definitions'
    
    def __str__(self):
        return f"{self.key} - {self.label}"
    
    def can_delete(self):
        """Check if column can be deleted (not system and not used in templates)"""
        if self.is_system:
            return False
        return not self.template_usages.exists()


class ActivityColumnValidation(models.Model):
    """
    Validation rules for columns.
    Multiple rules can be applied to a single column.
    """
    
    RULE_TYPE_CHOICES = [
        ('required', 'Required'),
        ('regex', 'Regular Expression'),
        ('min_length', 'Minimum Length'),
        ('max_length', 'Maximum Length'),
        ('min_value', 'Minimum Value'),
        ('max_value', 'Maximum Value'),
        ('options', 'Must Be One Of'),
        ('unique', 'Unique In Sheet'),
        ('date_format', 'Date Format'),
    ]
    
    column = models.ForeignKey(
        ActivityColumnDefinition,
        on_delete=models.CASCADE,
        related_name='validations'
    )
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES)
    rule_value = models.CharField(
        max_length=500, 
        blank=True,
        help_text="Rule value (e.g., regex pattern, min length number)"
    )
    error_message = models.CharField(
        max_length=500,
        help_text="Error message shown when validation fails"
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order']
        verbose_name = 'Validation Rule'
        verbose_name_plural = 'Validation Rules'
    
    def __str__(self):
        return f"{self.column.key} - {self.rule_type}"


class ActivityTemplate(models.Model):
    """
    User-created templates.
    
    Lifecycle: draft -> published -> archived
    - Draft: Can be edited, cannot create sheets from it
    - Published: Cannot edit columns, users can create sheets
    - Archived: Soft-deleted but sheets remain accessible
    
    IMPORTANT: Templates with sheets are NEVER hard-deleted.
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_templates'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='draft'
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete flag - archived templates keep this True"
    )
    
    # Only one template can be active at a time - this is the default for users
    is_active_title = models.BooleanField(
        default=False,
        help_text="If True, this is the active title users will see by default. Only one title can be active."
    )
    
    # Header image for Excel export
    header_image = models.ImageField(
        upload_to='activity_templates/headers/',
        blank=True,
        null=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Activity Template'
        verbose_name_plural = 'Activity Templates'
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def can_delete(self):
        """Check if template can be hard deleted (no sheets)"""
        return not self.sheets.exists()
    
    def archive(self):
        """Archive the template instead of deleting"""
        self.status = 'archived'
        self.is_deleted = True
        self.save(update_fields=['status', 'is_deleted', 'updated_at'])
    
    def publish(self):
        """Publish the template"""
        if self.status != 'draft':
            raise ValueError("Can only publish draft templates")
        if not self.template_columns.exists():
            raise ValueError("Cannot publish template without columns")
        
        self.status = 'published'
        self.published_at = timezone.now()
        self.save(update_fields=['status', 'published_at', 'updated_at'])


class ActivityTemplateColumn(models.Model):
    """
    Links column definitions to templates with custom configuration.
    Each template can have different order, width, and requirements for columns.
    """
    
    template = models.ForeignKey(
        ActivityTemplate,
        on_delete=models.CASCADE,
        related_name='template_columns'
    )
    column_definition = models.ForeignKey(
        ActivityColumnDefinition,
        on_delete=models.PROTECT,  # Prevent deletion if used in templates
        related_name='template_usages'
    )
    order = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Override default column width"
    )
    is_required = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['order']
        unique_together = ['template', 'column_definition']
        verbose_name = 'Template Column'
        verbose_name_plural = 'Template Columns'
    
    def __str__(self):
        return f"{self.template.name} - {self.column_definition.key}"
    
    def get_effective_width(self):
        """Get width (override or default)"""
        return self.width or self.column_definition.default_width


class ActivitySheet(models.Model):
    """
    User's saved spreadsheet data.
    
    Stores a snapshot of columns at creation time for data integrity.
    Even if template is deleted/archived, sheets remain accessible.
    """
    
    name = models.CharField(max_length=255)
    description = models.TextField(
        blank=True, 
        default='',
        help_text="Optional description for the sheet"
    )
    template = models.ForeignKey(
        ActivityTemplate,
        on_delete=models.SET_NULL,  # Keep sheet if template deleted
        null=True,
        related_name='sheets'
    )
    # Snapshot of columns at sheet creation for data integrity
    column_snapshot = models.JSONField(
        default=list,
        help_text="Frozen copy of template columns at creation time"
    )
    
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_sheets'
    )
    
    is_active = models.BooleanField(default=True)
    row_count = models.PositiveIntegerField(
        default=0,
        help_text="Cached row count for performance"
    )
    
    # Submission status - once submitted, user cannot edit
    is_submitted = models.BooleanField(
        default=False,
        help_text="If True, sheet has been submitted to admin and cannot be edited."
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when sheet was submitted"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Activity Sheet'
        verbose_name_plural = 'Activity Sheets'
    
    def __str__(self):
        template_name = self.template.name if self.template else "(No Template)"
        return f"{self.name} - {template_name}"
    
    def update_row_count(self):
        """Update cached row count"""
        self.row_count = self.rows.count()
        self.save(update_fields=['row_count', 'updated_at'])


class ActivitySheetRow(models.Model):
    """
    Individual row in a sheet.
    
    IMPORTANT: Row identification system:
    - `id` (PK): Stable database identifier, never changes
    - `row_order`: Display position within sheet (1-indexed), CAN change with inserts/deletes
    - `row_number`: DEPRECATED - kept for backward compatibility
    
    When inserting a row at position N:
    1. All rows with row_order >= N get their row_order incremented
    2. New row gets row_order = N
    
    This allows proper row shifting without data loss.
    """
    
    sheet = models.ForeignKey(
        ActivitySheet,
        on_delete=models.CASCADE,
        related_name='rows'
    )
    # DEPRECATED: Use row_order instead
    row_number = models.PositiveIntegerField(
        help_text="DEPRECATED: Use row_order for ordering. Kept for backward compatibility."
    )
    # NEW: Explicit display order
    row_order = models.PositiveIntegerField(
        default=1,
        help_text="Display order of the row within the sheet (1-indexed). Can change with inserts."
    )
    data = models.JSONField(
        default=dict,
        help_text="Row data: {column_key: value}"
    )
    styles = models.JSONField(
        default=dict,
        help_text="Cell styles: {column_key: {bold, italic, backgroundColor, textColor}}"
    )
    height = models.PositiveIntegerField(default=32)
    
    # For tracking changes and conflict resolution
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['row_order']
        verbose_name = 'Sheet Row'
        verbose_name_plural = 'Sheet Rows'
        indexes = [
            models.Index(fields=['sheet', 'row_order'], name='activities_row_order_idx'),
            models.Index(fields=['sheet', 'updated_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['sheet', 'row_order'],
                name='unique_sheet_row_order'
            ),
        ]
    
    def __str__(self):
        return f"Row {self.row_order} (ID: {self.id}) - {self.sheet.name}"
    
    def get_cell_value(self, column_key: str):
        """Get value for a specific column"""
        return self.data.get(column_key, '')
    
    def set_cell_value(self, column_key: str, value: str):
        """Set value for a specific column"""
        self.data[column_key] = value
    
    def get_cell_style(self, column_key: str):
        """Get style for a specific column"""
        return self.styles.get(column_key, {})
    
    def set_cell_style(self, column_key: str, style: dict):
        """Set style for a specific column"""
        self.styles[column_key] = style
    
    def save(self, *args, **kwargs):
        """Override save to keep row_number in sync with row_order for backward compatibility."""
        if self.row_number != self.row_order:
            self.row_number = self.row_order
        super().save(*args, **kwargs)
