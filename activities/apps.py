from django.apps import AppConfig


class ActivitiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'activities'
    verbose_name = 'Activities Management'
    
    def ready(self):
        try:
            import activities.signals  # noqa
        except ImportError:
            pass
