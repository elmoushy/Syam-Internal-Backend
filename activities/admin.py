# activities/admin.py
"""
Django Admin configuration for Activities system.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ActivityColumnDefinition,
    ActivityColumnValidation,
    ActivityTemplate,
    ActivityTemplateColumn,
    ActivitySheet,
    ActivitySheetRow,
)


class ActivityColumnValidationInline(admin.TabularInline):
    """Inline for validation rules in column admin"""
    model = ActivityColumnValidation
    extra = 0
    fields = ['rule_type', 'rule_value', 'error_message', 'is_active', 'order']


@admin.register(ActivityColumnDefinition)
class ActivityColumnDefinitionAdmin(admin.ModelAdmin):
    list_display = ['key', 'label', 'data_type', 'default_width', 'is_system', 'is_active', 'order', 'validation_count']
    list_filter = ['is_system', 'is_active', 'data_type']
    search_fields = ['key', 'label']
    ordering = ['order']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ActivityColumnValidationInline]
    
    fieldsets = (
        (None, {
            'fields': ('key', 'label', 'data_type')
        }),
        ('Display', {
            'fields': ('default_width', 'min_width', 'order')
        }),
        ('Options', {
            'fields': ('options',),
            'classes': ('collapse',),
            'description': 'Only used for "select" data type'
        }),
        ('Status', {
            'fields': ('is_system', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def validation_count(self, obj):
        count = obj.validations.count()
        return format_html('<span style="color: {};">{}</span>', 
                          'green' if count > 0 else 'gray', count)
    validation_count.short_description = 'Validations'
    
    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ActivityColumnValidation)
class ActivityColumnValidationAdmin(admin.ModelAdmin):
    list_display = ['column', 'rule_type', 'rule_value_preview', 'is_active', 'order']
    list_filter = ['rule_type', 'is_active', 'column']
    search_fields = ['column__key', 'column__label', 'error_message']
    ordering = ['column', 'order']
    
    def rule_value_preview(self, obj):
        if len(obj.rule_value) > 50:
            return obj.rule_value[:50] + '...'
        return obj.rule_value or '-'
    rule_value_preview.short_description = 'Rule Value'


class ActivityTemplateColumnInline(admin.TabularInline):
    """Inline for template columns"""
    model = ActivityTemplateColumn
    extra = 0
    fields = ['column_definition', 'order', 'width', 'is_required', 'is_visible']
    autocomplete_fields = ['column_definition']


@admin.register(ActivityTemplate)
class ActivityTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'status', 'column_count', 'sheet_count', 'is_deleted', 'created_at']
    list_filter = ['status', 'is_deleted', 'created_at']
    search_fields = ['name', 'description', 'owner__username', 'owner__email']
    readonly_fields = ['created_at', 'updated_at', 'published_at']
    inlines = [ActivityTemplateColumnInline]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'owner')
        }),
        ('Status', {
            'fields': ('status', 'is_deleted')
        }),
        ('Header Image', {
            'fields': ('header_image',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )
    
    def column_count(self, obj):
        return obj.template_columns.count()
    column_count.short_description = 'Columns'
    
    def sheet_count(self, obj):
        count = obj.sheets.count()
        color = 'blue' if count > 0 else 'gray'
        return format_html('<span style="color: {};">{}</span>', color, count)
    sheet_count.short_description = 'Sheets'
    
    actions = ['archive_templates', 'publish_templates']
    
    @admin.action(description='Archive selected templates')
    def archive_templates(self, request, queryset):
        for template in queryset:
            template.archive()
        self.message_user(request, f'{queryset.count()} templates archived.')
    
    @admin.action(description='Publish selected templates')
    def publish_templates(self, request, queryset):
        published = 0
        for template in queryset.filter(status='draft'):
            try:
                template.publish()
                published += 1
            except ValueError:
                pass
        self.message_user(request, f'{published} templates published.')


@admin.register(ActivitySheet)
class ActivitySheetAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'template', 'row_count', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at', 'template']
    search_fields = ['name', 'owner__username', 'owner__email', 'template__name']
    readonly_fields = ['created_at', 'updated_at', 'row_count', 'column_snapshot']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('name', 'owner', 'template')
        }),
        ('Status', {
            'fields': ('is_active', 'row_count')
        }),
        ('Column Snapshot', {
            'fields': ('column_snapshot',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        # Sheets should be created via API, not admin
        return False


@admin.register(ActivitySheetRow)
class ActivitySheetRowAdmin(admin.ModelAdmin):
    list_display = ['sheet', 'row_number', 'data_preview', 'height', 'updated_at']
    list_filter = ['sheet', 'created_at']
    search_fields = ['sheet__name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['sheet', 'row_number']
    
    def data_preview(self, obj):
        preview = str(obj.data)
        if len(preview) > 100:
            return preview[:100] + '...'
        return preview
    data_preview.short_description = 'Data'
    
    def has_add_permission(self, request):
        # Rows should be created via API, not admin
        return False
