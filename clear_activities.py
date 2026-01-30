#!/usr/bin/env python
"""
Script to clear all activities from the database.
This deletes all ActivitySheetRow records.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weaponpowercloud_backend.settings')
django.setup()

from activities.models import ActivitySheetRow, ActivitySheet

def clear_activities():
    """Delete all activities from the database."""
    
    # Get counts before deletion
    row_count = ActivitySheetRow.objects.count()
    sheet_count = ActivitySheet.objects.count()
    
    print(f"\n📊 Current database state:")
    print(f"   - ActivitySheetRow (activities): {row_count}")
    print(f"   - ActivitySheet (sheets): {sheet_count}")
    
    if row_count == 0 and sheet_count == 0:
        print("\n✅ Database is already clean!")
        return
    
    # Ask for confirmation
    print(f"\n⚠️  WARNING: This will delete:")
    print(f"   - {row_count} activities (ActivitySheetRow)")
    print(f"   - {sheet_count} activity sheets (ActivitySheet)")
    
    confirm = input("\n❓ Are you sure you want to continue? (yes/no): ")
    
    if confirm.lower() not in ['yes', 'y']:
        print("\n❌ Operation cancelled.")
        return
    
    # Delete activities and sheets
    print("\n🗑️  Deleting activities...")
    deleted_rows, _ = ActivitySheetRow.objects.all().delete()
    print(f"   ✅ Deleted {row_count} activities")
    
    print("\n🗑️  Deleting sheets...")
    deleted_sheets, _ = ActivitySheet.objects.all().delete()
    print(f"   ✅ Deleted {sheet_count} sheets")
    
    print("\n✅ Database cleaned successfully!")
    print("\n📊 Final database state:")
    print(f"   - ActivitySheetRow: {ActivitySheetRow.objects.count()}")
    print(f"   - ActivitySheet: {ActivitySheet.objects.count()}")

if __name__ == '__main__':
    clear_activities()
