# activities/signals.py
"""
Django signals for Activities system.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ActivitySheetRow, ActivitySheet


@receiver(post_save, sender=ActivitySheetRow)
def update_sheet_row_count_on_save(sender, instance, created, **kwargs):
    """Update sheet row count when a row is added"""
    if created:
        sheet = instance.sheet
        sheet.row_count = sheet.rows.count()
        sheet.save(update_fields=['row_count'])


@receiver(post_delete, sender=ActivitySheetRow)
def update_sheet_row_count_on_delete(sender, instance, **kwargs):
    """Update sheet row count when a row is deleted"""
    try:
        sheet = instance.sheet
        sheet.row_count = sheet.rows.count()
        sheet.save(update_fields=['row_count'])
    except ActivitySheet.DoesNotExist:
        # Sheet was also deleted
        pass
