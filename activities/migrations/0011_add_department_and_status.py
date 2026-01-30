# Generated migration for Department model and related fields
# activities/migrations/0011_add_department_and_status.py

from django.db import migrations, models
import django.db.models.deletion


def create_default_department(apps, schema_editor):
    """Create the default department and assign it to existing templates/sheets."""
    Department = apps.get_model('activities', 'Department')
    ActivityTemplate = apps.get_model('activities', 'ActivityTemplate')
    ActivitySheet = apps.get_model('activities', 'ActivitySheet')
    
    # Create default department
    default_dept, created = Department.objects.get_or_create(
        code='ALL',
        defaults={
            'name': 'القسم العام',
            'description': 'القسم الافتراضي الذي يشمل جميع المستخدمين',
            'is_default': True,
            'is_active': True,
        }
    )
    
    # Assign default department to all existing templates
    ActivityTemplate.objects.filter(target_department__isnull=True).update(
        target_department=default_dept
    )
    
    # Assign default department to all existing sheets
    ActivitySheet.objects.filter(department__isnull=True).update(
        department=default_dept
    )


def reverse_default_department(apps, schema_editor):
    """Remove default department assignment (reverse migration)."""
    ActivityTemplate = apps.get_model('activities', 'ActivityTemplate')
    ActivitySheet = apps.get_model('activities', 'ActivitySheet')
    
    # Set department to NULL for all
    ActivityTemplate.objects.all().update(target_department=None)
    ActivitySheet.objects.all().update(department=None)


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0010_add_attachment_support'),
    ]

    operations = [
        # Step 1: Create Department model
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="Department name (e.g., 'القسم العام')", max_length=255)),
                ('code', models.CharField(help_text="Unique department code (e.g., 'ALL', 'HR', 'IT')", max_length=50, unique=True)),
                ('description', models.TextField(blank=True, help_text='Optional department description')),
                ('is_default', models.BooleanField(default=False, help_text='True = default department for all users. Only one can be default.')),
                ('is_active', models.BooleanField(default=True, help_text='Soft delete flag')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Department',
                'verbose_name_plural': 'Departments',
                'ordering': ['-is_default', 'name'],
            },
        ),
        
        # Step 2: Add target_department to ActivityTemplate
        migrations.AddField(
            model_name='activitytemplate',
            name='target_department',
            field=models.ForeignKey(
                blank=True,
                help_text='Target department for this template. NULL = all departments (legacy)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='templates',
                to='activities.department'
            ),
        ),
        
        # Step 3: Add department to ActivitySheet
        migrations.AddField(
            model_name='activitysheet',
            name='department',
            field=models.ForeignKey(
                blank=True,
                help_text='Department that owns this sheet. NULL = default department (legacy)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sheets',
                to='activities.department'
            ),
        ),
        
        # Step 4: Add activity_status to ActivitySheetRow
        migrations.AddField(
            model_name='activitysheetrow',
            name='activity_status',
            field=models.CharField(
                choices=[
                    ('not_started', 'لم يبدأ'),
                    ('in_progress', 'قيد التنفيذ'),
                    ('completed', 'مكتمل')
                ],
                default='not_started',
                help_text='Status of this activity for KPI calculations',
                max_length=20
            ),
        ),
        
        # Step 5: Create default department and assign to existing records
        migrations.RunPython(create_default_department, reverse_default_department),
    ]
