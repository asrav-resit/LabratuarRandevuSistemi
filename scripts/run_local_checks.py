"""Küçük yerel kontrolleri çalıştıran yardımcı script.

- Ne yapar: Test kullanıcıları ve minimal veri (lab/cihaz/randevu) oluşturur,
  kritik endpoint'leri çağırır (admin, onay-bekleyen API, PDF indirme vb.) ve
  sonucu `local_check_report.json` olarak yazar.
- Kullanım: Sanal ortam aktifken `python scripts/run_local_checks.py` şeklinde
  çalıştırın. Bu script sadece geliştirme/yerel test amaçlıdır; üretimde çalıştırmayın.
"""

import os
import sys
import json
from datetime import date, time

# Ensure project root is on sys.path so Django settings can be imported
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lab_sistemi.settings")
import django

django.setup()

from django.contrib.auth.models import User
from django.test import Client
from rezervasyon.models import Laboratuvar, Cihaz, Randevu, Profil
from django.core.management import call_command
from django.conf import settings

REPORT_PATH = os.path.join(settings.BASE_DIR, "local_check_report.json")
report = {"ok": True, "details": []}

# ensure static files are collected
try:
    call_command("collectstatic", "--noinput")
    report["details"].append({"collectstatic": "ok"})
except Exception as e:
    report["ok"] = False
    report["details"].append({"collectstatic": f"error: {e}"})

# create/get superuser
try:
    admin, created = User.objects.get_or_create(username="testadmin")
    admin.email = "admin@example.com"
    admin.is_staff = True
    admin.is_superuser = True
    admin.set_password("adminpass")
    admin.save()
    report["details"].append({"create_superuser": "ok"})
except Exception as e:
    report["ok"] = False
    report["details"].append({"create_superuser": f"error: {e}"})

# create/get student user
try:
    student, _ = User.objects.get_or_create(
        username="teststudent", defaults={"email": "stud@ogr.btu.edu.tr"}
    )
    student.set_password("studentpass")
    student.save()
    profil, _ = Profil.objects.get_or_create(user=student)
    report["details"].append({"create_student": "ok"})
except Exception as e:
    report["ok"] = False
    report["details"].append({"create_student": f"error: {e}"})

# create minimal lab and device
try:
    lab, _ = Laboratuvar.objects.get_or_create(isim="Test Lab")
    cihaz, _ = Cihaz.objects.get_or_create(
        isim="Test Cihaz", lab=lab, defaults={"aktif_mi": True}
    )
    report["details"].append({"create_lab_device": "ok"})
except Exception as e:
    report["ok"] = False
    report["details"].append({"create_lab_device": f"error: {e}"})

# create a randevu
try:
    r = Randevu.objects.create(
        kullanici=student,
        cihaz=cihaz,
        tarih=date.today(),
        baslangic_saati=time(10, 0),
        bitis_saati=time(11, 0),
    )
    report["details"].append({"create_randevu": "ok"})
except Exception as e:
    report["ok"] = False
    report["details"].append({"create_randevu": f"error: {e}"})

# Ensure test client host is allowed by settings.
# Dikkat: Buradaki değişiklik yalnızca runtime için (memory) yapılır ve settings.py dosyasını
# kalıcı olarak değiştirmez; böylece test client `client.get()` taleplerinin AllowedHost nedeniyle
# reddedilmesi engellenir.
from django.conf import settings

try:
    if (
        not getattr(settings, "ALLOWED_HOSTS", None)
        or "testserver" not in settings.ALLOWED_HOSTS
    ):
        settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + [
            "testserver",
            "localhost",
            "127.0.0.1",
        ]
except Exception:
    settings.ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

client = Client()

# check admin login
try:
    logged_in = client.login(username="testadmin", password="adminpass")
    r = client.get("/admin/")
    report["details"].append(
        {"admin_login": {"logged_in": logged_in, "status_code": r.status_code}}
    )
except Exception as e:
    report["ok"] = False
    report["details"].append({"admin_login": f"error: {e}"})

# check onay bekleyen API
try:
    r = client.get("/api/onay-bekleyen-sayisi/")
    api_ok = r.status_code == 200
    api_json = None
    if r.status_code == 200:
        try:
            api_json = r.json()
            api_ok = api_ok and api_json.get("sayi") is not None
        except Exception:
            api_ok = False
    report["details"].append(
        {
            "onay_bekleyen_api": {
                "status_code": r.status_code,
                "json": api_json,
                "ok": api_ok,
                "content_snippet": (
                    r.content[:1000].decode("utf-8", errors="replace")
                    if r.content
                    else ""
                ),
            }
        }
    )
    if not api_ok:
        report["ok"] = False
except Exception as e:
    report["ok"] = False
    report["details"].append({"onay_bekleyen_api": f"error: {e}"})

# check PDF generation as student
try:
    logged_in = client.login(username="teststudent", password="studentpass")
    r = client.get("/randevularim/pdf-indir/")
    content_type = r.get("Content-Type", "")
    pdf_ok = r.status_code == 200 and "application/pdf" in content_type
    snippet = ""
    if not pdf_ok:
        try:
            snippet = r.content[:2000].decode("utf-8", errors="replace")
        except Exception:
            snippet = str(r.content[:2000])
    report["details"].append(
        {
            "pdf_generation": {
                "status_code": r.status_code,
                "content_type": content_type,
                "ok": pdf_ok,
                "content_snippet": snippet,
            }
        }
    )
    if not pdf_ok:
        report["ok"] = False
except Exception as e:
    report["ok"] = False
    report["details"].append({"pdf_generation": f"error: {e}"})

# check static file exists
try:
    static_file = os.path.join(
        settings.BASE_DIR, "staticfiles", "fonts", "js", "admin_ozel.js"
    )
    static_ok = os.path.exists(static_file)
    report["details"].append(
        {"static_admin_ozel": {"path": static_file, "exists": static_ok}}
    )
    if not static_ok:
        report["ok"] = False
except Exception as e:
    report["ok"] = False
    report["details"].append({"static_admin_ozel": f"error: {e}"})

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print("Local checks finished. Report written to", REPORT_PATH)
print(json.dumps(report, indent=2, ensure_ascii=False))

if not report["ok"]:
    sys.exit(2)
else:
    sys.exit(0)
