from django.apps import AppConfig


class LearningConfig(AppConfig):
    name = "apps.learning"

    def ready(self):
        from . import signals  # noqa: F401
