"""
Clean Activities Data Script
Deletes all activity sheets and specific templates from the database.
Run with: python manage.py shell < clean_activities_data.py
Or: python clean_activities_data.py
"""

import os
import sys
import django

# Setup Django environment
if __name__ == '__main__':
    # Add the project directory to the path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weaponpowercloud_backend.settings')
    django.setup()

from activities.models import ActivitySheet, ActivityTemplate, ActivitySheetRow

def clean_activities_data():
    """Delete all sheets and specific templates"""
    
    print("=" * 60)
    print("CLEANING ACTIVITIES DATA")
    print("=" * 60)
    
    # Count before deletion
    sheet_count = ActivitySheet.objects.count()
    row_count = ActivitySheetRow.objects.count()
    
    print(f"\n📊 Current State:")
    print(f"   - Activity Sheets: {sheet_count}")
    print(f"   - Activity Sheet Rows: {row_count}")
    
    # Delete all sheet rows first (foreign key dependency)
    print(f"\n🗑️  Deleting all sheet rows...")
    deleted_rows = ActivitySheetRow.objects.all().delete()
    print(f"   ✅ Deleted {deleted_rows[0]} rows")
    
    # Delete all sheets
    print(f"\n🗑️  Deleting all sheets...")
    deleted_sheets = ActivitySheet.objects.all().delete()
    print(f"   ✅ Deleted {deleted_sheets[0]} sheets")
    
    # Delete specific templates (IDs: 4, 1)
    template_ids_to_delete = [4, 1]
    print(f"\n🗑️  Deleting specific templates (IDs: {template_ids_to_delete})...")
    
    for template_id in template_ids_to_delete:
        try:
            template = ActivityTemplate.objects.get(id=template_id)
            template_name = template.name
            # Delete the template (cascade will delete related columns)
            template.delete()
            print(f"   ✅ Deleted template ID {template_id}: '{template_name}'")
        except ActivityTemplate.DoesNotExist:
            print(f"   ⚠️  Template ID {template_id} not found (already deleted?)")
    
    # Show remaining templates
    remaining_templates = ActivityTemplate.objects.filter(is_deleted=False)
    print(f"\n📋 Remaining Templates: {remaining_templates.count()}")
    for template in remaining_templates:
        status_icon = "✓" if template.is_active_title else " "
        print(f"   [{status_icon}] ID {template.id}: {template.name} (Status: {template.status})")
    
    print("\n" + "=" * 60)
    print("✅ CLEANUP COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("\n💡 You can now test with no sheets existing.\n")

if __name__ == '__main__':
    try:
        clean_activities_data()
    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
