from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Configuration for the Audit app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Audit'
    verbose_name = 'Audit Log'
    
    def ready(self):
        """Import signals when app is ready."""
        import Audit.signals  # noqa
