#!/usr/bin/env python
"""Django yönetim komutları yardımcı betiği.

Bu dosya Django yönetim komutlarını çalıştırmak için kullanılır (runserver, makemigrations, migrate, createsuperuser vb.).
Geliştirme sırasında yerel küçük kontrolleri çalıştırmak için `scripts/run_local_checks.py` betiği de bulunmaktadır.
"""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lab_sistemi.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
