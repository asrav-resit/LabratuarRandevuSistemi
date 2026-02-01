from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count
import csv
from django.core.mail import send_mail
from django.conf import settings

"""rezervasyon.admin

Admin paneli için model kayıtları ve yönetim aksiyonları.
- Excel/CSV indirme, kullanıcı yetkilendirme, cihaz durumu gösterimleri gibi
  yardımcı fonksiyonlar burada tanımlıdır.
- Proxy modeller (OnayBekleyenler, AktifOgrenciler) admin görünümünü sadeleştirir.
"""

# Modelleri İçe Aktar
from .models import (
    Laboratuvar,
    Cihaz,
    Randevu,
    Profil,
    Ariza,
    Duyuru,
    OnayBekleyenler,
    AktifOgrenciler,
)

# ========================================================
# 1. ORTAK AKSİYONLAR VE FONKSİYONLAR
# ========================================================


def excel_indir(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="randevu_listesi.csv"'
    writer = csv.writer(response)
    writer.writerow(["Kullanıcı Adı", "Laboratuvar", "Cihaz", "Tarih", "Saat", "Durum"])
    for randevu in queryset:
        writer.writerow(
            [
                randevu.kullanici.username,
                randevu.cihaz.lab.isim,
                randevu.cihaz.isim,
                randevu.tarih,
                f"{randevu.baslangic_saati} - {randevu.bitis_saati}",
                randevu.get_durum_display(),
            ]
        )
    return response


excel_indir.short_description = "📥 Seçilenleri Excel (CSV) Olarak İndir"

# --- Kullanıcı Yetki Aksiyonları (Global Tanımlandı) ---


@admin.action(description="👑 Seçilenleri SÜPER KULLANICI Yap")
def super_yap(modeladmin, request, queryset):
    sayi = queryset.update(is_superuser=True, is_staff=True)
    modeladmin.message_user(
        request, f"{sayi} kullanıcı başarıyla SÜPER KULLANICI yapıldı!", level="SUCCESS"
    )


@admin.action(description="👤 Seçilenlerin Yetkilerini AL (Normal Yap)")
def normal_yap(modeladmin, request, queryset):
    sayi = queryset.update(is_superuser=False, is_staff=False)
    modeladmin.message_user(
        request,
        f"{sayi} kullanıcının yetkileri alındı, normal kullanıcı yapıldı.",
        level="WARNING",
    )


@admin.action(description="⛔ Seçilenleri PASİFE AL (Giriş Yetkisini Kapat)")
def kullanicilari_pasife_al(modeladmin, request, queryset):
    sayi = queryset.update(is_active=False)
    modeladmin.message_user(
        request,
        f"{sayi} kullanıcı pasife alındı ve giriş yetkisi kapatıldı.",
        level="ERROR",
    )


@admin.action(description="✅ Seçilen Kullanıcıları Onayla (Aktif Et)")
def kullanicilari_onayla(modeladmin, request, queryset):
    sayi = queryset.update(is_active=True)
    modeladmin.message_user(
        request, f"{sayi} kullanıcı başarıyla onaylandı ve aktif edildi."
    )


# ========================================================
# 2. ANA MODELLERİN ADMİN AYARLARI
# ========================================================


# --- LABORATUVAR ---
@admin.register(Laboratuvar)
class LaboratuvarAdmin(admin.ModelAdmin):
    list_display = ("isim", "cihaz_durumu_gorsel", "aciklama_kisalt")
    search_fields = ("isim",)

    def cihaz_durumu_gorsel(self, obj):
        from .models import Cihaz

        sayi = Cihaz.objects.filter(lab=obj).count()
        yuzde = (sayi / 20) * 100
        if yuzde > 100:
            yuzde = 100
        renk = "success" if sayi > 0 else "danger"
        return format_html(
            """<div style="min-width: 100px;">
                <small>{} Cihaz</small>
                <div class="progress progress-xs">
                    <div class="progress-bar bg-{}" style="width: {}%"></div>
                </div></div>""",
            sayi,
            renk,
            yuzde,
        )

    cihaz_durumu_gorsel.short_description = "Laboratuvar Kapasitesi"

    def aciklama_kisalt(self, obj):
        return obj.aciklama[:50] + "..." if obj.aciklama else "-"

    aciklama_kisalt.short_description = "Açıklama"


# --- CİHAZ ---
@admin.action(description="🔴 Seçilenleri BAKIMA AL (Pasif)")
def bakima_al(modeladmin, request, queryset):
    queryset.update(aktif_mi=False)


@admin.action(description="🟢 Seçilenleri HİZMETE AÇ (Aktif)")
def hizmete_ac(modeladmin, request, queryset):
    queryset.update(aktif_mi=True)


@admin.register(Cihaz)
class CihazAdmin(admin.ModelAdmin):
    list_display = ("isim", "lab", "durum_etiketi", "aktif_mi")
    list_filter = ("lab", "aktif_mi")
    search_fields = ("isim",)
    actions = [bakima_al, hizmete_ac]

    fieldsets = (
        ("Temel Bilgiler", {"fields": ("isim", "lab")}),
        ("Durum Ayarları", {"fields": ("aktif_mi",), "classes": ("collapse",)}),
    )

    def durum_etiketi(self, obj):
        if not obj.aktif_mi:
            return mark_safe('<span class="badge badge-danger">⛔ Bakımda</span>')

        try:
            ariza_var = Ariza.objects.filter(cihaz=obj, cozuldu_mu=False).exists()
        except Exception:
            ariza_var = False

        if ariza_var:
            return mark_safe('<span class="badge badge-warning">⚠️ Arızalı</span>')

        return mark_safe('<span class="badge badge-success">✅ Çalışıyor</span>')

    durum_etiketi.short_description = "Anlık Durum"


# --- RANDEVU ---
@admin.register(Randevu)
class RandevuAdmin(admin.ModelAdmin):
    # 'onaylayan_admin' alanını listeye ekledik (isteğe bağlı)
    list_display = (
        "kullanici_badge",
        "cihaz_bilgisi",
        "tarih_saat",
        "renkli_durum",
        "onaylayan_admin",
        "durum",
    )
    list_filter = ("durum", "tarih", "cihaz__lab", "onaylayan_admin")
    search_fields = ("kullanici__username", "cihaz__isim", "onaylayan_admin__username")
    date_hierarchy = "tarih"
    list_editable = ("durum",)
    readonly_fields = (
        "onaylayan_admin",
    )  # Manuel değiştirilmemesi için sadece okunur yaptık
    actions = [excel_indir]

    def save_model(self, request, obj, form, change):
        # Durum değiştiyse işlemi yapan admini kaydet
        if change and "durum" in form.changed_data:
            obj.onaylayan_admin = request.user  # Mevcut giriş yapan admini kaydeder

            durum_mesajı = ""
            konu = f"Laboratuvar Randevusu Hakkında - {obj.cihaz.isim}"
            gonderilecek_mi = True

            if obj.durum == "onaylandi":
                durum_mesajı = (
                    f"Tebrikler! {obj.tarih} tarihindeki randevunuz onaylanmıştır."
                )
            elif obj.durum == "reddedildi":
                durum_mesajı = f"Üzgünüz, {obj.tarih} tarihindeki randevu talebiniz reddedilmiştir."
            elif obj.durum == "iptal_edildi":
                durum_mesajı = f"{obj.tarih} tarihindeki randevunuz iptal edilmiştir."
            else:
                gonderilecek_mi = False

            if gonderilecek_mi:
                self.message_user(
                    request,
                    f"📧 {obj.kullanici.username} adlı kullanıcıya '{obj.get_durum_display()}' maili gönderildi (Admin: {request.user.username}).",
                    level="SUCCESS",
                )

                mesaj_icerigi = f"Merhaba {obj.kullanici.first_name if obj.kullanici.first_name else obj.kullanici.username},\n\n{durum_mesajı}\n\nDetaylar:\nCihaz: {obj.cihaz.isim}\nLaboratuvar: {obj.cihaz.lab.isim}\nSaat: {obj.baslangic_saati} - {obj.bitis_saati}\nİşlemi Gerçekleştiren: {request.user.get_full_name() or request.user.username}\n\nİyi çalışmalar dileriz."

                try:
                    send_mail(
                        subject=konu,
                        message=mesaj_icerigi,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[obj.kullanici.email],
                        fail_silently=True,
                    )
                except Exception as e:
                    self.message_user(request, f"Mail hatası: {e}", level="ERROR")

        super().save_model(request, obj, form, change)

    def renkli_durum(self, obj):
        renkler = {
            "onay_bekleniyor": ("#ffc107", "#000", "BEKLEMEDE"),
            "onaylandi": ("#28a745", "#fff", "ONAYLANDI"),
            "reddedildi": ("#dc3545", "#fff", "REDDEDİLDİ"),
            "geldi": ("#17a2b8", "#fff", "GELDİ"),
            "gelmedi": ("#6c757d", "#fff", "GELMEDİ"),
            "iptal_edildi": ("#343a40", "#fff", "İPTAL EDİLDİ"),
        }
        arka_plan, yazi, etiket = renkler.get(obj.durum, ("#e9ecef", "#000", obj.durum))
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 10px; '
            "border-radius: 12px; font-weight: bold; font-size: 10px; display: inline-block; "
            'min-width: 80px; text-align: center; border: 1px solid rgba(0,0,0,0.1);">'
            "{}</span>",
            arka_plan,
            yazi,
            etiket,
        )

    renkli_durum.short_description = "GÖRSEL DURUM"

    def kullanici_badge(self, obj):
        return format_html(
            '<span style="font-weight:bold; color:#555;"><i class="fas fa-user"></i> {}</span>',
            obj.kullanici.username,
        )

    kullanici_badge.short_description = "Kullanıcı"

    def cihaz_bilgisi(self, obj):
        return f"{obj.cihaz.isim} ({obj.cihaz.lab.isim})"

    cihaz_bilgisi.short_description = "Cihaz / Lab"

    def tarih_saat(self, obj):
        return f"{obj.tarih} | {obj.baslangic_saati}-{obj.bitis_saati}"

    tarih_saat.short_description = "Zaman"


# --- PROFİL (Hatasız) ---
@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = (
        "resim_yuvarlak",
        "kullanici_adi",
        "okul_numarasi",
        "dogrulama_kodu",
        "iletisim_ikonlari",
    )
    search_fields = ("user__username", "okul_numarasi")

    def kullanici_adi(self, obj):
        return obj.user.username

    def resim_yuvarlak(self, obj):
        if obj.resim:
            return format_html(
                '<img src="{}" style="width: 40px; height:40px; border-radius:50%; object-fit:cover; box-shadow: 0 2px 5px rgba(0,0,0,0.2);" />',
                obj.resim.url,
            )
        # Resim yoksa hata vermemesi için mark_safe kullanıyoruz
        return mark_safe('<span style="color:#ccc; font-style:italic;">Yok</span>')

    resim_yuvarlak.short_description = "Fotoğraf"

    def iletisim_ikonlari(self, obj):
        if obj.telefon:
            return format_html(
                '<a href="tel:{}"><i class="fas fa-phone"></i> {}</a>',
                obj.telefon,
                obj.telefon,
            )
        return "-"

    iletisim_ikonlari.short_description = "İletişim"


# --- ARIZA ---
@admin.action(description="🛠️ İlgili cihazları KAPAT")
def cihazlari_kapat(modeladmin, request, queryset):
    sayac = 0
    for ariza in queryset:
        if ariza.cihaz.aktif_mi:
            ariza.cihaz.aktif_mi = False
            ariza.cihaz.save()
            sayac += 1
    modeladmin.message_user(
        request, f"{sayac} cihaz arıza nedeniyle kapatıldı.", level="WARNING"
    )


@admin.register(Ariza)
class ArizaAdmin(admin.ModelAdmin):
    list_display = ("cihaz", "kullanici", "aciklama_goster", "tarih", "cozuldu_mu")
    list_filter = ("cozuldu_mu", "tarih")
    list_editable = ("cozuldu_mu",)
    actions = [cihazlari_kapat]

    def aciklama_goster(self, obj):
        return obj.aciklama[:40] + "..." if obj.aciklama else "-"

    aciklama_goster.short_description = "Sorun"


# --- DUYURU ---
@admin.register(Duyuru)
class DuyuruAdmin(admin.ModelAdmin):
    list_display = ("baslik", "tarih", "aktif_mi")
    list_editable = ("aktif_mi",)


# ========================================================
# 3. KULLANICI YÖNETİMİ (USER & PROXY)
# ========================================================

# 1. Varsayılan User panelini kaldır
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


# 2. Ana User Modeli (Tüm Kullanıcılar)
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Tüm aksiyonları buraya ekliyoruz
    actions = [super_yap, normal_yap, kullanicilari_pasife_al]
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_superuser",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")


# 3. Proxy Model: Onay Bekleyenler (Pasif)
@admin.register(OnayBekleyenler)
class OnayBekleyenlerAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "date_joined",
        "is_active",
    )
    list_display_links = ("username",)

    # Sadece Pasifleri Getir
    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_active=False)

    # Sadece Onaylama butonu olsun
    actions = [kullanicilari_onayla]


# 4. Proxy Model: Aktif Öğrenciler
@admin.register(AktifOgrenciler)
class AktifOgrencilerAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "last_login")
    list_display_links = ("username",)

    # Sadece Aktifleri Getir
    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_active=True)

    # Sadece Pasife Alma butonu olsun
    actions = [kullanicilari_pasife_al]
