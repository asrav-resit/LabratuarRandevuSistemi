"""
ASGI config for lab_sistemi project.

This module exposes an ASGI `application` callable for asynchronous servers
(e.g., Daphne, Uvicorn). Use ASGI when you need WebSocket support or async
workloads; otherwise WSGI is sufficient for traditional synchronous deployment.

For more information: https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lab_sistemi.settings")

application = get_asgi_application()
