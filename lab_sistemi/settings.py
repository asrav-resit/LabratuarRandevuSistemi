"""
Django settings for lab_sistemi project.

Bu dosya:
1. Senin Jazzmin (Admin Paneli) tasarımlarını korur.
2. Sunucu için gerekli güvenlik (.env, WhiteNoise) ayarlarını içerir.
3. Gmail ve PDF ayarlarını aktif eder.
"""

from pathlib import Path
import os
from decouple import config  # pip install python-decouple

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# ========================================================
# 1. GÜVENLİK AYARLARI (KRİTİK)
# ========================================================

# .env dosyasından okur. Yoksa varsayılan güvensize döner (ama uyarı verir).
SECRET_KEY = config('SECRET_KEY', default='django-insecure-CHANGE-THIS-IN-PRODUCTION')

# Sunucuda False, Localde True olacak (Yine .env'den okur)
DEBUG = config('DEBUG', default=True, cast=bool)

# Sunucu adresini buraya ekleyeceğiz (Şimdilik herkese açık)
ALLOWED_HOSTS = ['*']


# ========================================================
# 2. UYGULAMA TANIMLARI
# ========================================================

INSTALLED_APPS = [
    # 1. Admin Teması (Mutlaka en üstte)
    "jazzmin",
    
    # 2. Django Varsayılanları
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    
    # WhiteNoise: Statik dosyaları sunmak için (Sunucu için ŞART)
    "whitenoise.runserver_nostatic", 
    "django.contrib.staticfiles",
    
    # 3. Üçüncü Parti Araçlar
    "xhtml2pdf",     # PDF Üretimi
    "widget_tweaks", # Formları güzelleştirmek için
    "django_extensions", # (Opsiyonel) Geliştirici araçları

    # 4. Sizin Uygulamalarınız
    "rezervasyon",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise Middleware (Hemen Security'den sonra olmalı)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lab_sistemi.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "lab_sistemi.wsgi.application"


# ========================================================
# 3. VERİTABANI AYARLARI
# ========================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# ========================================================
# 4. ŞİFRE DOĞRULAMA
# ========================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ========================================================
# 5. DİL VE ZAMAN AYARLARI
# ========================================================

LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True # Sayıları 1.000,00 şeklinde yazar


# ========================================================
# 6. STATİK VE MEDYA DOSYALARI (WHITENOISE UYUMLU)
# ========================================================

STATIC_URL = "/static/"
# collectstatic komutu çalıştığında dosyaların toplanacağı klasör (Sunucu için)
STATIC_ROOT = BASE_DIR / "staticfiles"

# Geliştirme aşamasında statik dosyaların bulunduğu yer
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# WhiteNoise Sıkıştırma Ayarı (Sunucu performansını artırır)
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ========================================================
# 7. E-POSTA AYARLARI (GMAIL - .ENV)
# ========================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
# Bilgileri .env dosyasından gizlice çeker, yoksa boş döner
EMAIL_HOST_USER = config("EMAIL_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_PASS", default="")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# ========================================================
# 8. GİRİŞ / ÇIKIŞ YÖNLENDİRMELERİ
# ========================================================

LOGIN_REDIRECT_URL = "anasayfa"
LOGOUT_REDIRECT_URL = "anasayfa"
LOGIN_URL = "giris"


# ========================================================
# 9. UYGULAMA-SPESİFİK AYARLAR
# ========================================================

MAX_RANDEVU_SAATI = 3
IPTAL_MIN_SURE_SAAT = 1
OKUL_MAIL_UZANTISI = "@ogr.btu.edu.tr"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ========================================================
# 10. JAZZMIN (ADMİN PANELİ) AYARLARI
# ========================================================

JAZZMIN_SETTINGS = {
    "site_title": "Lab Yönetim",
    "site_header": "Okul Lab Sistemi",
    "site_brand": "Yönetim Paneli",
    "welcome_sign": "Laboratuvar Yönetim Merkezine Hoşgeldiniz",
    "copyright": "Okul Lab Sistemi 2025",
    "search_model": "auth.User",
    "custom_css": "fonts/css/custom_admin.css",
    "user_avatar": None,
    # Kırmızı Bildirim Scripti
    "custom_js": "fonts/js/admin_ozel.js",
    "topmenu_links": [
        {"name": "Ana Sayfa", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "Siteyi Görüntüle", "url": "/", "new_window": True},
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "rezervasyon.Laboratuvar": "fas fa-flask",
        "rezervasyon.Cihaz": "fas fa-microscope",
        "rezervasyon.Randevu": "fas fa-calendar-check",
        "rezervasyon.Ariza": "fas fa-tools",
        "rezervasyon.Duyuru": "fas fa-bullhorn",
        "rezervasyon.Profil": "fas fa-id-card",
        "rezervasyon.OnayBekleyenler": "fas fa-user-clock",
        "rezervasyon.AktifOgrenciler": "fas fa-user-graduate",
    },
    "order_with_respect_to": [
        "rezervasyon.AktifOgrenciler",
        "rezervasyon.OnayBekleyenler",
        "rezervasyon.Randevu",
        "rezervasyon.Ariza",
        "rezervasyon.Cihaz",
        "rezervasyon.Laboratuvar",
    ],
    "show_ui_builder": True,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-primary",
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "theme": "flatly",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}