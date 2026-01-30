# activities/models.py
"""
Models for the Dynamic Activities Template System.

Architecture:
- Department: Organizational units (Phase 1: single default department)
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


# ============================================================================
# Department Model (Phase 1: Single Default Department)
# ============================================================================

class Department(models.Model):
    """
    Organizational department for grouping activities.
    
    Phase 1: A single default department "القسم العام" contains all users.
    Future phases will support multiple departments with hierarchy.
    """
    
    name = models.CharField(
        max_length=255,
        help_text="Department name (e.g., 'القسم العام')"
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique department code (e.g., 'ALL', 'HR', 'IT')"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional department description"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="True = default department for all users. Only one can be default."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Soft delete flag"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
    
    def __str__(self):
        return self.name
    
    @classmethod
    def get_default_department(cls):
        """
        Get or create the default department.
        Returns the department with is_default=True.
        """
        department, created = cls.objects.get_or_create(
            is_default=True,
            defaults={
                'name': 'القسم العام',
                'code': 'ALL',
                'description': 'القسم الافتراضي الذي يشمل جميع المستخدمين'
            }
        )
        return department
    
    def save(self, *args, **kwargs):
        """Ensure only one default department exists."""
        if self.is_default:
            # Remove default flag from other departments
            Department.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
    
    def can_delete(self):
        """Check if department can be deleted (not default, not used)"""
        if self.is_default:
            return False
        return not self.sheets.exists() and not self.templates.exists()


class ActivityColumnDefinition(models.Model):
    """
    Global column definitions managed by admin.
    System columns (is_system=True) are created by migration and cannot be deleted.
    """
    
    DATA_TYPE_CHOICES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('email', 'Email'),
        ('tel', 'Phone'),
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
    
    # Attachment settings
    allows_attachment = models.BooleanField(
        default=False,
        help_text="Whether this column allows file attachments"
    )
    attachment_required = models.BooleanField(
        default=False,
        help_text="Whether attachment is required when allows_attachment is True"
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
    notes = models.TextField(
        blank=True, 
        help_text='Instructions or notes for users filling out this template'
    )
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
    
    # Multiple templates can be active at the same time
    is_active_title = models.BooleanField(
        default=False,
        help_text="If True, this template is active and visible to users. Multiple templates can be active."
    )
    
    # Header image for Excel export
    header_image = models.ImageField(
        upload_to='activity_templates/headers/',
        blank=True,
        null=True
    )
    
    # Department targeting (Phase 1: always default department)
    target_department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='templates',
        help_text="Target department for this template. NULL = all departments (legacy)"
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
    
    # Department ownership (Phase 1: always default department)
    department = models.ForeignKey(
        'Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sheets',
        help_text="Department that owns this sheet. NULL = default department (legacy)"
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
    
    # Activity status for KPI tracking
    ACTIVITY_STATUS_CHOICES = [
        ('not_started', 'لم يبدأ'),
        ('in_progress', 'قيد التنفيذ'),
        ('completed', 'مكتمل'),
    ]
    activity_status = models.CharField(
        max_length=20,
        choices=ACTIVITY_STATUS_CHOICES,
        default='not_started',
        help_text="Status of this activity for KPI calculations"
    )
    
    # Per-activity submission status - each activity can be submitted individually
    is_submitted = models.BooleanField(
        default=False,
        help_text="If True, this activity has been submitted and cannot be edited."
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when activity was submitted"
    )
    
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


class ActivityRowAttachment(models.Model):
    """
    Stores file attachments for activity rows.
    Files are stored as binary blobs for data integrity.
    Main API returns only URL, actual file is served via separate download endpoint.
    """
    
    row = models.ForeignKey(
        ActivitySheetRow,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    column_key = models.CharField(
        max_length=100,
        help_text="The column key this attachment belongs to"
    )
    
    # File metadata
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100)
    
    # Binary file content stored as blob
    file_content = models.BinaryField(
        help_text="Binary file content stored as blob"
    )
    
    # For quick identification
    is_image = models.BooleanField(
        default=False,
        help_text="True if file is an image that can be previewed"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Row Attachment'
        verbose_name_plural = 'Row Attachments'
        indexes = [
            models.Index(fields=['row', 'column_key']),
        ]
    
    def __str__(self):
        return f"{self.original_filename} - Row {self.row_id}"
    
    @property
    def download_url(self):
        """Generate download URL for this attachment"""
        return f"/api/activities/attachments/{self.id}/download/"
    
    @property
    def preview_url(self):
        """Generate preview URL for images"""
        if self.is_image:
            return f"/api/activities/attachments/{self.id}/preview/"
        return None
    
    def save(self, *args, **kwargs):
        """Auto-detect if file is an image based on mime type"""
        image_mimes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml']
        self.is_image = self.mime_type in image_mimes
        super().save(*args, **kwargs)
