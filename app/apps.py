from django.apps import AppConfig
import threading

class AppConfig(AppConfig):
    name = "app"
    def ready(self):
        from .lpr import _load_models
        import os
        if os.environ.get("RUN_MAIN") == "true":
            threading.Thread(target=_load_models, daemon=True).start()
