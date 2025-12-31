"""
Signal handlers for automatic audit logging.

This module contains Django signal handlers that automatically track
critical business actions across the system.
"""

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from surveys.models import Survey
from newsletters.models import Newsletter
from authentication.models import User, PagePermission
from .models import AuditLog
import threading

# ============================================================================
# ARABIC MESSAGE TEMPLATES
# ============================================================================

# News type translations
NEWS_TYPE_AR = {
    'SLIDER': 'خبر رئيسي',
    'NORMAL': 'خبر عادي',
    'URGENT': 'خبر عاجل',
}

# Role translations
ROLE_AR = {
    'super_admin': 'مدير عام',
    'admin': 'مدير',
    'user': 'مستخدم',
    'None': 'بدون دور',
}

# Custom role translations
CUSTOM_ROLE_AR = {
    'quicklinks_admin': 'مدير الروابط السريعة',
    'newsletter_admin': 'مدير الأخبار',
    'survey_admin': 'مدير الاستبيانات',
}

# Field name translations
FIELD_AR = {
    'title': 'العنوان',
    'visibility': 'مستوى الظهور',
    'start_date': 'تاريخ البداية',
    'end_date': 'تاريخ الانتهاء',
    'status': 'الحالة',
    'is_active': 'التفعيل',
    'role': 'الدور',
    'user_role': 'الدور المخصص',
    'news_type': 'نوع الخبر',
}


def get_arabic_news_type(news_type: str) -> str:
    """Get Arabic translation for news type."""
    return NEWS_TYPE_AR.get(news_type, news_type)


def get_arabic_role(role: str) -> str:
    """Get Arabic translation for role."""
    if role is None:
        return 'بدون دور'
    return ROLE_AR.get(role, role)


def get_arabic_custom_role(role_name: str) -> str:
    """Get Arabic translation for custom role."""
    if not role_name or role_name == 'None':
        return 'بدون دور مخصص'
    role_key = role_name.lower().replace(' ', '_').replace('-', '_')
    for key, value in CUSTOM_ROLE_AR.items():
        if key in role_key:
            return value
    return role_name


def get_arabic_fields(fields: list) -> str:
    """Get Arabic translation for field names."""
    arabic_fields = [FIELD_AR.get(f, f) for f in fields]
    return '، '.join(arabic_fields)
# Thread-local storage for current user context
_thread_locals = threading.local()


def set_current_user(user):
    """Store current user in thread-local storage for signal handlers."""
    _thread_locals.user = user


def get_current_user():
    """Retrieve current user from thread-local storage."""
    return getattr(_thread_locals, 'user', None)


# ============================================================================
# SURVEY SIGNALS
# ============================================================================

@receiver(pre_save, sender=Survey)
def capture_survey_old_values(sender, instance, **kwargs):
    """Capture old values before save for change detection."""
    import logging
    logger = logging.getLogger(__name__)
    
    if instance.pk:
        try:
            instance._old = Survey.objects.get(pk=instance.pk)
            logger.info(f"[AUDIT] Captured old values for survey {instance.pk}: is_active={instance._old.is_active}")
        except Survey.DoesNotExist:
            logger.warning(f"[AUDIT] Survey {instance.pk} not found in pre_save")
            pass


@receiver(post_save, sender=Survey)
def log_survey_actions(sender, instance, created, **kwargs):
    """Log survey create/update/activate/deactivate/submit."""
    import logging
    logger = logging.getLogger(__name__)
    
    actor = get_current_user()
    
    if not actor:
        logger.warning(f"[AUDIT] No actor found for survey {instance.pk} (is_active={instance.is_active}, status={instance.status})")
        return  # Skip if no user context
    
    actor_name = actor.full_name or actor.email
    object_name = instance.title[:200]  # Truncate long titles
    
    if created:
        # Survey created
        AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name,
            action=AuditLog.SURVEY_CREATE,
            content_type=ContentType.objects.get_for_model(Survey),
            object_id=str(instance.pk),
            object_name=object_name,
            description=f"قام المستخدم {actor_name} بإنشاء استبيان جديد بعنوان «{object_name}»",
            changes={}
        )
        logger.debug(f"Audit: SURVEY_CREATE for {instance.pk}")
    else:
        # Survey updated - check for specific state changes
        old = getattr(instance, '_old', None)
        if not old:
            logger.warning(f"[AUDIT] No old instance found for survey {instance.pk} update (is_active={instance.is_active})")
            return
        
        changes = {}
        
        logger.info(f"[AUDIT] Survey {instance.pk} update detected: old.is_active={old.is_active}, new.is_active={instance.is_active}")
        
        # Check for activation/deactivation
        if old.is_active != instance.is_active:
            if instance.is_active:
                action = AuditLog.SURVEY_ACTIVATE
                description = f"قام المستخدم {actor_name} بتفعيل استبيان «{object_name}»"
            else:
                action = AuditLog.SURVEY_DEACTIVATE
                description = f"قام المستخدم {actor_name} بإلغاء تفعيل استبيان «{object_name}»"
            
            changes['is_active'] = {'old': old.is_active, 'new': instance.is_active}
            
            AuditLog.objects.create(
                actor=actor,
                actor_name=actor_name,
                action=action,
                content_type=ContentType.objects.get_for_model(Survey),
                object_id=str(instance.pk),
                object_name=object_name,
                description=description,
                changes=changes
            )
        
        # Check for submission
        if old.status != instance.status and instance.status == 'submitted':
            AuditLog.objects.create(
                actor=actor,
                actor_name=actor_name,
                action=AuditLog.SURVEY_SUBMIT,
                content_type=ContentType.objects.get_for_model(Survey),
                object_id=str(instance.pk),
                object_name=object_name,
                description=f"قام المستخدم {actor_name} بنشر استبيان «{object_name}»",
                changes={'status': {'old': old.status, 'new': instance.status}}
            )
        
        # Check for other significant updates (title, description, dates)
        significant_changes = {}
        if old.title != instance.title:
            significant_changes['title'] = {'old': old.title, 'new': instance.title}
        if old.visibility != instance.visibility:
            significant_changes['visibility'] = {'old': old.visibility, 'new': instance.visibility}
        if old.start_date != instance.start_date:
            significant_changes['start_date'] = {
                'old': str(old.start_date) if old.start_date else None,
                'new': str(instance.start_date) if instance.start_date else None
            }
        if old.end_date != instance.end_date:
            significant_changes['end_date'] = {
                'old': str(old.end_date) if old.end_date else None,
                'new': str(instance.end_date) if instance.end_date else None
            }
        
        if significant_changes:
            changed_fields_ar = get_arabic_fields(list(significant_changes.keys()))
            AuditLog.objects.create(
                actor=actor,
                actor_name=actor_name,
                action=AuditLog.SURVEY_UPDATE,
                content_type=ContentType.objects.get_for_model(Survey),
                object_id=str(instance.pk),
                object_name=object_name,
                description=f"قام المستخدم {actor_name} بتحديث استبيان «{object_name}» - الحقول المعدّلة: {changed_fields_ar}",
                changes=significant_changes
            )


@receiver(post_delete, sender=Survey)
def log_survey_delete(sender, instance, **kwargs):
    """Log survey deletion."""
    
    actor = get_current_user()
    if not actor:
        return
    
    actor_name = actor.full_name or actor.email
    object_name = instance.title[:200]
    
    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        action=AuditLog.SURVEY_DELETE,
        content_type=ContentType.objects.get_for_model(Survey),
        object_id=str(instance.pk),
        object_name=object_name,
        description=f"قام المستخدم {actor_name} بحذف استبيان «{object_name}»",
        changes={}
    )


# ============================================================================
# NEWSLETTER SIGNALS
# ============================================================================

@receiver(post_save, sender=Newsletter)
def log_newsletter_actions(sender, instance, created, **kwargs):
    """Log newsletter create/update."""
    
    actor = get_current_user()
    if not actor:
        return
    
    actor_name = actor.full_name or actor.email
    object_name = instance.title[:200]
    news_type_ar = get_arabic_news_type(instance.news_type)
    
    if created:
        AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name,
            action=AuditLog.NEWSLETTER_CREATE,
            content_type=ContentType.objects.get_for_model(Newsletter),
            object_id=str(instance.pk),
            object_name=object_name,
            description=f"قام المستخدم {actor_name} بإنشاء {news_type_ar} بعنوان «{object_name}»",
            changes={'news_type': instance.news_type}
        )
    else:
        AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name,
            action=AuditLog.NEWSLETTER_UPDATE,
            content_type=ContentType.objects.get_for_model(Newsletter),
            object_id=str(instance.pk),
            object_name=object_name,
            description=f"قام المستخدم {actor_name} بتحديث خبر «{object_name}»",
            changes={}
        )


@receiver(post_delete, sender=Newsletter)
def log_newsletter_delete(sender, instance, **kwargs):
    """Log newsletter deletion."""
    
    actor = get_current_user()
    if not actor:
        return
    
    actor_name = actor.full_name or actor.email
    object_name = instance.title[:200]
    
    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        action=AuditLog.NEWSLETTER_DELETE,
        content_type=ContentType.objects.get_for_model(Newsletter),
        object_id=str(instance.pk),
        object_name=object_name,
        description=f"قام المستخدم {actor_name} بحذف خبر «{object_name}»",
        changes={}
    )


# ============================================================================
# USER ROLE/PERMISSION SIGNALS
# ============================================================================

@receiver(pre_save, sender=User)
def capture_user_old_values(sender, instance, **kwargs):
    """Capture old role values."""
    import logging
    logger = logging.getLogger(__name__)
    
    if instance.pk:
        try:
            instance._old_user = User.objects.get(pk=instance.pk)
            logger.warning(f"[AUDIT PRE_SAVE] Captured old values for user {instance.pk}: user_role_id={instance._old_user.user_role_id}, role={instance._old_user.role}")
        except User.DoesNotExist:
            logger.warning(f"[AUDIT PRE_SAVE] User {instance.pk} not found in pre_save")
            pass


@receiver(post_save, sender=User)
def log_role_changes(sender, instance, created, **kwargs):
    """Log role assignments and changes (including QuickLinks admin)."""
    import logging
    logger = logging.getLogger(__name__)
    
    if created:
        logger.info(f"[AUDIT] User {instance.pk} created, skipping audit log")
        return  # Don't log user creation
    
    actor = get_current_user()
    if not actor:
        logger.warning(f"[AUDIT] No actor found for user {instance.pk} role change (user_role_id={instance.user_role_id}, role={instance.role})")
        return
    
    old = getattr(instance, '_old_user', None)
    if not old:
        logger.warning(f"[AUDIT] No old user values found for user {instance.pk}")
        return
    
    actor_name = actor.full_name or actor.email
    target_name = instance.full_name or instance.email
    
    logger.warning(f"[AUDIT] Checking role changes for user {instance.pk}: old_role={old.role}, new_role={instance.role}, old_user_role_id={old.user_role_id}, new_user_role_id={instance.user_role_id}")
    
    # Check for role column change (super_admin, admin, user)
    if old.role != instance.role:
        old_role_ar = get_arabic_role(old.role)
        new_role_ar = get_arabic_role(instance.role)
        AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name,
            action=AuditLog.ROLE_CHANGE,
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(instance.pk),
            object_name=target_name,
            description=f"قام المستخدم {actor_name} بتغيير دور {target_name} من «{old_role_ar}» إلى «{new_role_ar}»",
            changes={'role': {'old': old.role, 'new': instance.role}}
        )
    
    # Check for user_role FK change (custom roles like Newsletter_admin, Survey_admin, QuickLinks_admin)
    if old.user_role_id != instance.user_role_id:
        old_role_name = old.user_role.display_name if old.user_role else 'None'
        new_role_name = instance.user_role.display_name if instance.user_role else 'None'
        
        logger.warning(f"[AUDIT] user_role CHANGED for {target_name}: {old_role_name} -> {new_role_name}")
        
        # Get Arabic role names
        old_role_ar = get_arabic_custom_role(old_role_name)
        new_role_ar = get_arabic_custom_role(new_role_name)
        
        if new_role_name == 'None':
            # Role was removed
            description = f"قام المستخدم {actor_name} بإزالة الدور المخصص «{old_role_ar}» من {target_name}"
        elif old_role_name == 'None':
            # New role assigned
            description = f"قام المستخدم {actor_name} بتعيين {target_name} كـ «{new_role_ar}»"
        else:
            # Role changed
            description = f"قام المستخدم {actor_name} بتغيير دور {target_name} من «{old_role_ar}» إلى «{new_role_ar}»"
        
        audit_log = AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name,
            action=AuditLog.ROLE_ASSIGN,
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(instance.pk),
            object_name=target_name,
            description=description,
            changes={'user_role': {'old': old_role_name, 'new': new_role_name}}
        )
        logger.warning(f"[AUDIT] ✓ ROLE_ASSIGN audit log created: {audit_log.description}")


@receiver(post_save, sender=PagePermission)
def log_permission_grant(sender, instance, created, **kwargs):
    """Log permission grants."""
    
    if not created:
        return
    
    actor = get_current_user()
    if not actor:
        return
    
    actor_name = actor.full_name or actor.email
    role_name = instance.role.display_name
    page_name = instance.display_name or instance.name
    role_ar = get_arabic_custom_role(role_name)
    
    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        action=AuditLog.PERMISSION_GRANT,
        content_type=ContentType.objects.get_for_model(PagePermission),
        object_id=str(instance.pk),
        object_name=f"{role_name} → {page_name}",
        description=f"قام المستخدم {actor_name} بمنح صلاحية الوصول إلى «{page_name}» لدور «{role_ar}»",
        changes={'role': role_name, 'page': page_name}
    )


@receiver(post_delete, sender=PagePermission)
def log_permission_revoke(sender, instance, **kwargs):
    """Log permission revocations."""
    
    actor = get_current_user()
    if not actor:
        return
    
    actor_name = actor.full_name or actor.email
    role_name = instance.role.display_name
    page_name = instance.display_name or instance.name
    role_ar = get_arabic_custom_role(role_name)
    
    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        action=AuditLog.PERMISSION_REVOKE,
        content_type=ContentType.objects.get_for_model(PagePermission),
        object_id=str(instance.pk),
        object_name=f"{role_name} → {page_name}",
        description=f"قام المستخدم {actor_name} بسحب صلاحية الوصول إلى «{page_name}» من دور «{role_ar}»",
        changes={'role': role_name, 'page': page_name}
    )
