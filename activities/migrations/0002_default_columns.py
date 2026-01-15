# activities/migrations/0002_default_columns.py
"""
Data migration to create the 9 default system columns.
These columns are marked as is_system=True and cannot be deleted.
"""

from django.db import migrations


DEFAULT_COLUMNS = [
    {
        'key': 'activityType',
        'label': 'نوع النشاط',
        'data_type': 'select',
        'default_width': 150,
        'min_width': 100,
        'order': 1,
        'is_system': True,
        'options': ['اجتماع', 'ورشة عمل', 'تدريب', 'مؤتمر', 'أخرى'],
    },
    {
        'key': 'hasMeetingMinutes',
        'label': 'هل يوجد محضر اجتماع',
        'data_type': 'boolean',
        'default_width': 120,
        'min_width': 80,
        'order': 2,
        'is_system': True,
        'options': [],
    },
    {
        'key': 'department',
        'label': 'القسم',
        'data_type': 'text',
        'default_width': 150,
        'min_width': 100,
        'order': 3,
        'is_system': True,
        'options': [],
    },
    {
        'key': 'activityName',
        'label': 'اسم النشاط',
        'data_type': 'text',
        'default_width': 200,
        'min_width': 150,
        'order': 4,
        'is_system': True,
        'options': [],
    },
    {
        'key': 'representationType',
        'label': 'نوع التمثيل',
        'data_type': 'select',
        'default_width': 150,
        'min_width': 100,
        'order': 5,
        'is_system': True,
        'options': ['رسمي', 'غير رسمي', 'تطوعي'],
    },
    {
        'key': 'activityScope',
        'label': 'نطاق النشاط',
        'data_type': 'select',
        'default_width': 150,
        'min_width': 100,
        'order': 6,
        'is_system': True,
        'options': ['داخلي', 'خارجي', 'مشترك'],
    },
    {
        'key': 'activitySource',
        'label': 'مصدر النشاط',
        'data_type': 'text',
        'default_width': 150,
        'min_width': 100,
        'order': 7,
        'is_system': True,
        'options': [],
    },
    {
        'key': 'participatingEntities',
        'label': 'الجهات المشاركة',
        'data_type': 'text',
        'default_width': 200,
        'min_width': 150,
        'order': 8,
        'is_system': True,
        'options': [],
    },
    {
        'key': 'outputs',
        'label': 'المخرجات',
        'data_type': 'text',
        'default_width': 250,
        'min_width': 150,
        'order': 9,
        'is_system': True,
        'options': [],
    },
]


def create_default_columns(apps, schema_editor):
    """Create the 9 default system columns"""
    ActivityColumnDefinition = apps.get_model('activities', 'ActivityColumnDefinition')
    
    for column_data in DEFAULT_COLUMNS:
        ActivityColumnDefinition.objects.get_or_create(
            key=column_data['key'],
            defaults={
                'label': column_data['label'],
                'data_type': column_data['data_type'],
                'default_width': column_data['default_width'],
                'min_width': column_data['min_width'],
                'order': column_data['order'],
                'is_system': column_data['is_system'],
                'is_active': True,
                'options': column_data['options'],
            }
        )


def reverse_default_columns(apps, schema_editor):
    """Remove the default system columns (only non-system can be deleted)"""
    ActivityColumnDefinition = apps.get_model('activities', 'ActivityColumnDefinition')
    # Only delete system columns that we created
    keys = [col['key'] for col in DEFAULT_COLUMNS]
    ActivityColumnDefinition.objects.filter(key__in=keys, is_system=True).delete()


class Migration(migrations.Migration):
    
    dependencies = [
        ('activities', '0001_initial_models'),
    ]
    
    operations = [
        migrations.RunPython(
            create_default_columns,
            reverse_default_columns
        ),
    ]
