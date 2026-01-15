# Generated migration for adding row_order field
"""
Add row_order field to ActivitySheetRow for explicit ordering.

This is a critical change that separates:
- row_number: Deprecated, kept for backward compatibility
- row_order: New field for explicit row ordering within a sheet

The row_order field allows for:
- Inserting rows in the middle (shift subsequent rows)
- Reordering rows without data loss
- Stable identification of rows by database PK
"""

from django.db import migrations, models


def populate_row_order(apps, schema_editor):
    """
    Initialize row_order from row_number for existing data.
    """
    ActivitySheetRow = apps.get_model('activities', 'ActivitySheetRow')
    
    # Process in batches to avoid memory issues with large datasets
    batch_size = 1000
    offset = 0
    
    while True:
        rows = list(
            ActivitySheetRow.objects.all()
            .order_by('sheet_id', 'row_number')[offset:offset + batch_size]
        )
        
        if not rows:
            break
        
        for row in rows:
            row.row_order = row.row_number
        
        ActivitySheetRow.objects.bulk_update(rows, ['row_order'], batch_size=batch_size)
        offset += batch_size


def reverse_populate(apps, schema_editor):
    """
    Reverse: copy row_order back to row_number if needed.
    """
    # Nothing to do - row_number still exists
    pass


class Migration(migrations.Migration):
    
    dependencies = [
        ('activities', '0003_add_sheet_description'),
    ]
    
    operations = [
        # 1. Add row_order field (allow null initially)
        migrations.AddField(
            model_name='activitysheetrow',
            name='row_order',
            field=models.PositiveIntegerField(
                null=True,
                help_text='Display order of the row within the sheet (1-indexed)',
            ),
        ),
        
        # 2. Populate row_order from existing row_number
        migrations.RunPython(populate_row_order, reverse_populate),
        
        # 3. Make row_order non-nullable now that it's populated
        migrations.AlterField(
            model_name='activitysheetrow',
            name='row_order',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Display order of the row within the sheet (1-indexed)',
            ),
        ),
        
        # 4. Add index for efficient ordering queries
        migrations.AddIndex(
            model_name='activitysheetrow',
            index=models.Index(fields=['sheet', 'row_order'], name='activities_row_order_idx'),
        ),
        
        # 5. Remove unique constraint on sheet+row_number (row_order is now primary)
        # But keep row_number for backward compatibility
        migrations.AlterUniqueTogether(
            name='activitysheetrow',
            unique_together=set(),  # Remove old constraint
        ),
        
        # 6. Add new unique constraint on sheet+row_order
        migrations.AddConstraint(
            model_name='activitysheetrow',
            constraint=models.UniqueConstraint(
                fields=['sheet', 'row_order'],
                name='unique_sheet_row_order'
            ),
        ),
    ]
