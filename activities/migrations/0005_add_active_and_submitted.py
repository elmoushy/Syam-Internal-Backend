# Generated migration for adding is_active to template and is_submitted to sheet
"""
Add is_active field to ActivityTemplate (only one can be active at a time).
Add is_submitted and submitted_at fields to ActivitySheet.

This supports:
- Single active title that users auto-load
- Sheet submission workflow to admin
- User sheets preserved even if title is deleted/deactivated
"""

from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    
    dependencies = [
        ('activities', '0004_add_row_order'),
    ]
    
    operations = [
        # Add is_active to ActivityTemplate (default False, only one can be True)
        migrations.AddField(
            model_name='activitytemplate',
            name='is_active_title',
            field=models.BooleanField(
                default=False,
                help_text='If True, this is the active title users will see by default. Only one title can be active.'
            ),
        ),
        
        # Add is_submitted to ActivitySheet
        migrations.AddField(
            model_name='activitysheet',
            name='is_submitted',
            field=models.BooleanField(
                default=False,
                help_text='If True, sheet has been submitted to admin and cannot be edited.'
            ),
        ),
        
        # Add submitted_at timestamp
        migrations.AddField(
            model_name='activitysheet',
            name='submitted_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='Timestamp when sheet was submitted'
            ),
        ),
    ]
