# ============================================================
# admin.py – Laboratuvar Randevu Sistemi Yönetim Paneli
# ============================================================
from django.contrib import admin

admin.site.site_header = "BTÜ Randevu Sistemi Yönetimi"
admin.site.site_title = "BTÜ Randevu Paneli"
admin.site.index_title = "Yönetim Merkezine Hoş Geldiniz"

from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.http import HttpResponse
from django.shortcuts import redirect, get_object_or_404
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.core.mail import send_mail
from django.conf import settings
from django.db import models
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.shortcuts import render
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .forms import AdminMassEmailForm
import csv

from .models import (
    Laboratuvar, Cihaz, Randevu, Profil, Ariza, Duyuru,
    OnayBekleyenler, AktifOgrenciler
)

# ============================================================
# GÜVENLİ REDIRECT
# ============================================================

def safe_redirect(request, fallback=".."):
    # Güvenli redirect: yalnızca aynı host içindeki tam URL'lere veya
    # göreli path'lere izin ver. Dış hostlara yönlendirmeyi engelle.
    from urllib.parse import urlparse

    referer = request.META.get("HTTP_REFERER")
    if not referer:
        return redirect(fallback)

    parsed = urlparse(referer)
    # Eğer netloc (host) yoksa referer göreli path'tir -> güvenli
    if not parsed.netloc:
        return redirect(referer)

    # Eğer host var ise, yalnızca aynı host içerisindeyse izin ver
    if parsed.netloc == request.get_host():
        return redirect(referer)

    return redirect(fallback)

# ============================================================
# ORTAK ACTIONLAR
# ============================================================

@admin.action(description="📥 Excel (CSV) indir")
def excel_indir(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="liste.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response, delimiter=';')
    writer.writerow(["Kullanıcı", "Cihaz", "Tarih", "Saat", "Durum"])
    for obj in queryset:
        user = getattr(obj, "kullanici", None)
        if user:
            full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            if not full_name:
                full_name = getattr(user, 'username', '-')
        else:
            full_name = "-"

        writer.writerow([
            full_name,
            getattr(obj, "cihaz", "-"),
            getattr(obj, "tarih", "-"),
            f"{getattr(obj,'baslangic_saati','')}-{getattr(obj,'bitis_saati','')}",
            obj.get_durum_display() if hasattr(obj, "get_durum_display") else "-"
        ])
    return response

@admin.action(description="📧 Bilgilendirme maili gönder")
def mail_gonder(modeladmin, request, queryset):
    sayac = 0
    for obj in queryset:
        user = obj.kullanici if hasattr(obj, "kullanici") else obj
        if user.email:
            send_mail(
                "BTÜ Lab Bilgilendirme",
                "Hesabınızla ilgili bir bilgilendirme bulunmaktadır.",
                settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True
            )
            sayac += 1
    modeladmin.message_user(request, f"{sayac} kullanıcıya mail gönderildi.", messages.SUCCESS)


@admin.action(description="📧 Özel Mail Gönder")
def ozel_mail_action(modeladmin, request, queryset):
    # Store selected IDs and model info in session then redirect to the admin view
    ids = list(queryset.values_list('pk', flat=True))
    request.session['ozel_mail_data'] = {
        'app_label': modeladmin.model._meta.app_label,
        'model': modeladmin.model._meta.model_name,
        'pks': ids,
        'repr': str(modeladmin.model._meta.verbose_name_plural)
    }
    # Redirect back to the changelist and then to the custom view
    return redirect('admin:rezervasyon_ozel_mail')

@admin.action(description="🌟 Seçilenleri Süper Kullanıcı Yap")
def super_kullanici_yap(modeladmin, request, queryset):
    # Eğer queryset doğrudan User modeli değilse (Profil veya Randevu üzerinden geliyorsa)
    # ilgili User nesnelerini çekmek için bir kontrol ekliyoruz.
    guncellenen = 0
    for obj in queryset:
        # Nesnenin kendisi User mı yoksa 'user'/'kullanici' adında bir ilişkisi mi var?
        user = None
        if isinstance(obj, User):
            user = obj
        elif hasattr(obj, 'user'):
            user = obj.user
        elif hasattr(obj, 'kullanici'):
            user = obj.kullanici
            
        if user and not user.is_superuser:
            user.is_staff = True      # Yönetim paneline giriş izni
            user.is_superuser = True  # Tam yetki
            user.save()
            guncellenen += 1
            
    if guncellenen > 0:
        modeladmin.message_user(
            request, 
            f"✅ {guncellenen} kullanıcı başarıyla Süper Kullanıcı ve Personel yapıldı.", 
            messages.SUCCESS
        )
    else:
        modeladmin.message_user(
            request, 
            "⚠️ Seçilenler zaten süper kullanıcı veya geçerli kullanıcı bulunamadı.", 
            messages.WARNING
        )

class AdminMassMailMixin:
    """Mixin to add an admin view for sending custom emails to selected objects."""
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('ozel-mail/', self.admin_site.admin_view(self.ozel_mail_view), name='rezervasyon_ozel_mail'),
        ]
        return custom_urls + urls

    def ozel_mail_view(self, request):
        data = request.session.get('ozel_mail_data')
        if not data:
            messages.error(request, "Seçilmiş kullanıcı verisi bulunamadı.")
            return redirect('..')

        # Load queryset for given model and PKs
        app_label = data.get('app_label')
        model_name = data.get('model')
        pks = data.get('pks', [])

        Model = self.model.__class__ if False else None
        # Resolve model using apps
        from django.apps import apps
        Model = apps.get_model(app_label, model_name)
        queryset = Model.objects.filter(pk__in=pks)

        # Collect recipient emails with robust attribute probing
        recipients = []
        missing_emails = []

        def find_email(o):
            # Direct email field
            for attr in ('email',):
                if hasattr(o, attr):
                    val = getattr(o, attr)
                    if val:
                        return val

            # Common relation to User
            for rel in ('user', 'kullanici', 'owner'):
                if hasattr(o, rel):
                    try:
                        u = getattr(o, rel)
                        if u and hasattr(u, 'email') and u.email:
                            return u.email
                    except Exception:
                        pass

            # If object has profil relation
            if hasattr(o, 'profil'):
                try:
                    p = getattr(o, 'profil')
                    if p and hasattr(p, 'user') and p.user.email:
                        return p.user.email
                except Exception:
                    pass

            # Try __str__ or other fallbacks (no email)
            return None

        seen = set()
        for obj in queryset:
            email = find_email(obj)
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    missing_emails.append(obj)
                    continue

                if email.lower() in seen:
                    continue
                seen.add(email.lower())
                recipients.append((obj, email))
            else:
                missing_emails.append(obj)

        if request.method == 'POST':
            form = AdminMassEmailForm(request.POST)
            if form.is_valid():
                subject = form.cleaned_data['subject']
                message = form.cleaned_data['message']
                is_html = form.cleaned_data['is_html']

                sent = 0
                failed = 0
                errors = []

                for _obj, email in recipients:
                    try:
                        if is_html:
                            text_content = message
                            html_content = message
                            msg = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [email])
                            msg.attach_alternative(html_content, "text/html")
                            msg.send()
                        else:
                            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
                        sent += 1
                    except Exception as e:
                        failed += 1
                        errors.append(f"{email}: {e}")

                # Clear session for safety
                try:
                    del request.session['ozel_mail_data']
                except Exception:
                    pass

                return render(request, 'admin/rezervasyon/ozel_mail_result.html', {
                    'total': len(recipients), 'sent': sent, 'failed': failed,
                    'missing': missing_emails, 'errors': errors
                })
        else:
            form = AdminMassEmailForm()

        return render(request, 'admin/rezervasyon/ozel_mail_form.html', {
            'form': form, 'recipient_count': len(recipients), 'missing_count': len(missing_emails), 'repr': data.get('repr')
        })

@admin.action(description="🟢 Aktif yap")
def aktif_yap(modeladmin, request, queryset):
    queryset.update(is_active=True)

@admin.action(description="🔴 Pasif yap")
def pasif_yap(modeladmin, request, queryset):
    queryset.update(is_active=False)

# ============================================================
# LABORATUVAR & CİHAZ (GELİŞTİRİLMİŞ)
# ============================================================
# ============================================================
# LABORATUVAR & CİHAZ (HATASIZ VE ÇALIŞAN VERSİYON)
# ============================================================

@admin.register(Laboratuvar)
class LaboratuvarAdmin(admin.ModelAdmin):
    list_display = ("isim", "cihaz_durumu")
    
    def cihaz_durumu(self, obj):
        sayi = obj.cihaz_set.count()
        # success (yeşil) veya danger (kırmızı) badge gösterimi
        return format_html('<span class="badge badge-{}">{} cihaz</span>', "success" if sayi else "danger", sayi)

@admin.register(Cihaz)
class CihazAdmin(admin.ModelAdmin):
    # HATA VEREN 'is_active' FİLTRESİ KALDIRILDI
    list_display = ("isim", "lab", "durum")
    list_filter = ("lab",) # Sadece laboratuvara göre filtreleme yapar

    def durum(self, obj):
        # Arıza modelindeki aktif (çözülmemiş) kayıtları kontrol eder
        ariza_var = Ariza.objects.filter(cihaz=obj, cozuldu_mu=False).exists()
        
        if ariza_var:
            return mark_safe('''
                <span style="color:red; font-weight:bold; cursor:help;" class="animate-pulse">⚠️ ARIZALI</span>
                <style>@keyframes pulse { 0% { opacity:1; } 50% { opacity:0.5; } 100% { opacity:1; } } .animate-pulse { animation: pulse 1.5s infinite; }</style>
            ''')
        
        return mark_safe('<span style="color:green; font-weight:bold;">✅ ÇALIŞIYOR</span>')
    
    def get_model_perms(self, request):
        perms = super().get_model_perms(request)
        # Eğer çözülmemiş arıza varsa admin sayfasında uyarı gösterir
        if Ariza.objects.filter(cozuldu_mu=False).exists(): 
            perms["has_warning"] = True
        return perms
# ============================================================
# RANDEVU – HAREKETLİ ETİKETLER
# ============================================================

@admin.register(Randevu)
class RandevuAdmin(AdminMassMailMixin, admin.ModelAdmin):
    list_display = ("kullanici", "cihaz", "tarih", "durum_renkli", "butonlar")
    list_filter = ("durum", "tarih", "cihaz__lab")
    actions = [excel_indir, mail_gonder, ozel_mail_action]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by(models.Case(models.When(durum="onay_bekleniyor", then=0), default=1, output_field=models.IntegerField()), "-tarih")

    def durum_renkli(self, obj):
        renk_paleti = {"onay_bekleniyor": "#ffc107", "onaylandi": "#28a745", "geldi": "#17a2b8", "gelmedi": "#6c757d", "reddedildi": "#dc3545"}
        renk = renk_paleti.get(obj.durum, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:5px 12px; border-radius:20px; font-weight:bold; font-size:11px; display:inline-block; cursor:pointer; transition:all 0.3s ease;" '
            'onmouseover="this.style.transform=\'scale(1.1)\';" onmouseout="this.style.transform=\'scale(1)\';">{}</span>',
            renk, obj.get_durum_display()
        )

    def butonlar(self, obj):
        btn = []
        style = 'padding:4px 10px; border-radius:4px; color:white; font-size:11px; margin:2px; display:inline-block; cursor:pointer; transition:0.2s;'
        if obj.durum == "onay_bekleniyor":
            btn.append(format_html('<a class="button" style="background:#28a745; {}" href="onayla/{}/">Onayla</a>', style, obj.id))
            btn.append(format_html('<a class="button" style="background:#dc3545; {}" href="iptal/{}/">Reddet</a>', style, obj.id))
        elif obj.durum == "onaylandi":
            btn.append(format_html('<a class="button" style="background:#17a2b8; {}" href="geldi/{}/">Geldi</a>', style, obj.id))
            btn.append(format_html('<a class="button" style="background:#6c757d; {}" href="gelmedi/{}/">Gelmedi</a>', style, obj.id))
        return mark_safe(" ".join(btn))

    def get_urls(self):
        urls = super().get_urls()
        return [
            path("onayla/<int:pk>/", self.admin_site.admin_view(self.onayla)),
            path("iptal/<int:pk>/", self.admin_site.admin_view(self.iptal)),
            path("geldi/<int:pk>/", self.admin_site.admin_view(self.geldi)),
            path("gelmedi/<int:pk>/", self.admin_site.admin_view(self.gelmedi)),
        ] + urls

    def onayla(self, request, pk):
        r = get_object_or_404(Randevu, pk=pk); r.onayla(request.user); r.save()
        messages.success(request, "Randevu onaylandı."); return safe_redirect(request)

    def iptal(self, request, pk):
        r = get_object_or_404(Randevu, pk=pk); r.sonradan_iptal(); r.save()
        return safe_redirect(request)

    def geldi(self, request, pk):
        r = get_object_or_404(Randevu, pk=pk); r.geldi_isaretle(); r.save()
        return safe_redirect(request)

    def gelmedi(self, request, pk):
        r = get_object_or_404(Randevu, pk=pk); r.gelmedi_isaretle(); r.save()
        return safe_redirect(request)

# ============================================================
# ARIZA – HIZLI ÇÖZÜM
# ============================================================

@admin.register(Ariza)
class ArizaAdmin(admin.ModelAdmin):
    list_display = ("cihaz", "kullanici", "tarih", "buton")
    def buton(self, obj):
        if obj.cozuldu_mu:
            return format_html('<a class="button" href="geri/{}/">Geri Al</a>', obj.id)
        return format_html('<a class="button" style="background:#dc3545;color:white;cursor:pointer;" href="coz/{}/">Çöz</a>', obj.id)

    def get_urls(self):
        urls = super().get_urls()
        return [path("coz/<int:pk>/", self.admin_site.admin_view(self.coz)), path("geri/<int:pk>/", self.admin_site.admin_view(self.geri))] + urls

    def coz(self, request, pk):
        a = get_object_or_404(Ariza, pk=pk); a.cozuldu_mu = True; a.save()
        return safe_redirect(request)

    def geri(self, request, pk):
        a = get_object_or_404(Ariza, pk=pk); a.cozuldu_mu = False; a.save()
        return safe_redirect(request)

# ============================================================
# USER & PROXY MODELLER (HATASIZ VERSİYON)
# ============================================================

admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(AdminMassMailMixin, UserAdmin):
    actions = [aktif_yap, pasif_yap, mail_gonder, ozel_mail_action,super_kullanici_yap]

@admin.register(OnayBekleyenler)
class OnayBekleyenlerAdmin(AdminMassMailMixin, UserAdmin):
    actions = [aktif_yap, mail_gonder, ozel_mail_action]
    list_display = ("username", "email", "aktiflik_durumu", "tek_tik_aktif_et")
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_active=False)

    def aktiflik_durumu(self, obj):
        # format_html içine boş bir string ekleyerek hata giderildi
        return format_html('<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:10px;font-size:11px;cursor:pointer;">PASİF</span>', "")

    def tek_tik_aktif_et(self, obj):
        return format_html('<a class="button" style="background:#28a745;color:white;cursor:pointer;" href="aktif-et/{}/">Aktif Et</a>', obj.id)

    def get_urls(self):
        urls = super().get_urls()
        return [path("aktif-et/<int:pk>/", self.admin_site.admin_view(self.aktif_et))] + urls

    def aktif_et(self, request, pk):
        u = get_object_or_404(User, pk=pk); u.is_active = True; u.save()
        messages.success(request, f"{u.username} aktif edildi."); return safe_redirect(request)

@admin.register(AktifOgrenciler)
class AktifOgrencilerAdmin(AdminMassMailMixin, UserAdmin):
    actions = [pasif_yap, mail_gonder, ozel_mail_action]
    list_display = ("username", "email", "aktiflik_durumu", "tek_tik_pasif_et")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_active=True)

    def aktiflik_durumu(self, obj):
        # format_html içine boş bir string ekleyerek hata giderildi
        return format_html('<span style="background:#28a745;color:white;padding:3px 8px;border-radius:10px;font-size:11px;cursor:pointer;">AKTİF</span>', "")

    def tek_tik_pasif_et(self, obj):
        return format_html('<a class="button" style="background:#dc3545;color:white;cursor:pointer;" href="pasif-et/{}/">Pasif Et</a>', obj.id)

    def get_urls(self):
        urls = super().get_urls()
        return [path("pasif-et/<int:pk>/", self.admin_site.admin_view(self.pasif_et))] + urls

    def pasif_et(self, request, pk):
        u = get_object_or_404(User, pk=pk); u.is_active = False; u.save()
        messages.warning(request, f"{u.username} pasif yapıldı."); return safe_redirect(request)

# ============================================================
# PROFİL & DUYURU
# ============================================================
@admin.register(Profil)
class ProfilAdmin(AdminMassMailMixin, admin.ModelAdmin):
    list_display = ("user", "okul_numarasi", "telefon")
    actions = [ozel_mail_action]

@admin.register(Duyuru)
class DuyuruAdmin(admin.ModelAdmin):
    list_display = ('baslik', 'tarih', 'aktif_mi') # Listede tarihi ve durumunu gör
    list_filter = ('aktif_mi', 'tarih') # Tarihe göre filtreleme yap
    search_fields = ('baslik', 'icerik')