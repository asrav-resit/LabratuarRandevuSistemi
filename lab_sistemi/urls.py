"""
Uygulama URL Konfigürasyonu

Bu modül, uygulamanın tüm yönlendirme (routing) işlemlerini yönetir.
Yapı: Admin > API > Kimlik > Genel > Laboratuvar > Yönetim şeklinde gruplanmıştır.
"""

from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

# Views modülünü bütün olarak çekiyoruz (Daha temiz kod yapısı)
from rezervasyon import views

urlpatterns = [
    # ========================================================
    # 1. YÖNETİM VE API (SİSTEM)
    # ========================================================
    path("admin/", admin.site.urls),
    
    # --- API ENDPOINTS (AJAX ve JavaScript için) ---
    # Sol menüdeki kırmızı bildirim sayısı
    path("api/onay-bekleyen-sayisi/", views.onay_bekleyen_sayisi, name="onay_bekleyen_sayisi"),
    # FullCalendar için Randevu Verileri (JSON)
    path("api/events/<int:lab_id>/", views.lab_events, name="lab_events"),
    # FullCalendar için Cihaz Listesi (JSON)
    path("api/resources/<int:lab_id>/", views.lab_resources, name="lab_resources"),

    # ========================================================
    # 2. ANA SAYFA VE GENEL
    # ========================================================
    path("", views.anasayfa, name="anasayfa"),

    # ========================================================
    # 3. KİMLİK DOĞRULAMA (AUTH)
    # ========================================================
    path("giris/", auth_views.LoginView.as_view(template_name="giris.html"), name="giris"),
    path("cikis/", auth_views.LogoutView.as_view(next_page="anasayfa"), name="cikis"),
    path("kayit/", views.kayit, name="kayit"),
    path("email-dogrulama/", views.email_dogrulama, name="email_dogrulama"),

    # Şifre Değiştirme
    path("sifre-degistir/", 
         auth_views.PasswordChangeView.as_view(template_name="sifre_degistir.html"), 
         name="password_change"),
    path("sifre-degistir/tamam/", 
         auth_views.PasswordChangeDoneView.as_view(template_name="sifre_basarili.html"), 
         name="password_change_done"),

    # ========================================================
    # 4. TAKVİM GÖRÜNÜMLERİ
    # ========================================================
    path("takvim/", views.genel_takvim, name="genel_takvim"),
    path("takvim/lab/<int:lab_id>/", views.lab_takvim, name="lab_takvim"),

    # ========================================================
    # 5. LABORATUVAR VE CİHAZ İŞLEMLERİ
    # ========================================================
    path("lab/<int:lab_id>/", views.lab_detay, name="lab_detay"),
    path("cihaz/<int:cihaz_id>/", views.randevu_al, name="randevu_al"),
    path("ariza-bildir/<int:cihaz_id>/", views.ariza_bildir, name="ariza_bildir"),

    # ========================================================
    # 6. KULLANICI PROFİLİ VE RANDEVULARIM
    # ========================================================
    path("randevularim/", views.randevularim, name="randevularim"),
    path("randevularim/pdf-indir/", views.randevu_pdf_indir, name="randevu_pdf_indir"),
    path("iptal/<int:randevu_id>/", views.randevu_iptal, name="randevu_iptal"),
    path("profil-duzenle/", views.profil_duzenle, name="profil_duzenle"),

    # ========================================================
    # 7. EĞİTMEN / PERSONEL PANELİ (YÖNETİM)
    # ========================================================
    path("yonetim/", views.egitmen_paneli, name="egitmen_paneli"),
    path("yonetim/ogrenciler/", views.ogrenci_listesi, name="ogrenci_listesi"),
    path("yonetim/arizali-cihazlar/", views.arizali_cihaz_listesi, name="arizali_cihaz_listesi"),
    path("yonetim/tum-randevular/", views.tum_randevular, name="tum_randevular"),

    # Randevu Durum Güncelleme (Onay/Red/Geldi)
    path("durum-degis/<int:randevu_id>/<str:yeni_durum>/", 
         views.durum_guncelle, 
         name="durum_guncelle"),
]

# --- MEDYA DOSYALARI (SADECE DEBUG MODUNDA) ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)