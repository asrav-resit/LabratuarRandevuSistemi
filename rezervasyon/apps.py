"""App konfigürasyonu: `rezervasyon` uygulaması için AppConfig.

Bu dosya Django'ya uygulamanın var olduğunu bildirir ve gelecekte sinyaller
ve uygulama başlatma (ready) kodu koymak için kullanılabilir.
"""

from django.apps import AppConfig


class RezervasyonConfig(AppConfig):
    name = "rezervasyon"
