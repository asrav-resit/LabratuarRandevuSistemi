"""
WSGI config for lab_sistemi project.

This module exposes a WSGI `application` callable used by most synchronous
WSGI servers (e.g., Gunicorn, uWSGI) for production deployment. For async
or WebSocket-heavy workloads prefer ASGI.

For more information: https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lab_sistemi.settings")

application = get_wsgi_application()
