from django.apps import AppConfig

class BrgyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'brgy'

    def ready(self):
        import brgy.signals