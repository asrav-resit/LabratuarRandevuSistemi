"""
Uygulama URL Konfigürasyonu - Güncellenmiş & Entegre
"""
from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.conf import settings
from django.conf.urls.static import static

# Views modülünü bütün olarak çekiyoruz
from rezervasyon import views

urlpatterns = [
    # ========================================================
    # 1. YÖNETİM VE API (SİSTEM)
    # ========================================================
    path("admin/", admin.site.urls),
    
    # --- API ENDPOINTS ---
    # Sol menü bildirimi için
    path("api/onay-bekleyen-sayisi/", views.onay_bekleyen_sayisi, name="onay_bekleyen_sayisi"),
    
    # GENEL TAKVİM API (Loglardaki 404 hatasını bu satır çözer)
    path("api/tum-randevular/", views.tum_events_api, name="tum_events_api"),
    
    # LAB TAKVİM API'Sİ
    path('api/lab/<int:lab_id>/events/', views.lab_events_api, name='lab_events_api'),

    # ========================================================
    # 2. ANA SAYFA VE GENEL
    # ========================================================
    path("", views.anasayfa, name="anasayfa"),

    # ========================================================
    # 3. KİMLİK DOĞRULAMA (AUTH)
    # ========================================================
    path("giris/", views.CustomLoginView.as_view(), name="giris"),
    path("cikis/", auth_views.LogoutView.as_view(next_page="anasayfa"), name="cikis"),
    
    # AttributeError hatasını önlemek için views.py'da bu fonksiyonların olduğundan emin olun
    path("kayit/", views.kayit, name="kayit"),
    path("email-dogrulama/", views.email_dogrulama, name="email_dogrulama"),

    # Şifre Değiştirme
    path("sifre-degistir/", auth_views.PasswordChangeView.as_view(template_name="sifre_degistir.html"), name="password_change"),
    path("sifre-degistir/tamam/", auth_views.PasswordChangeDoneView.as_view(template_name="sifre_basarili.html"), name="password_change_done"),

    # Password reset (token-based email flow)
    # Consolidated password-reset flow: all stages use a single template and a
    # stage flag is passed to differentiate behavior. Keeps templates DRY.
    path(
        "sifre-sifirla/",
        auth_views.PasswordResetView.as_view(
            template_name="password_reset_flow.html",
            email_template_name="password_reset_email.html",
            extra_context={"stage": "form"},
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "sifre-sifirla/tamam/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="password_reset_flow.html",
            extra_context={"stage": "done"},
        ),
        name="password_reset_done",
    ),
    path(
        "sifre-sifirla/confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="password_reset_flow.html",
            extra_context={"stage": "confirm"},
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "sifre-sifirla/tamamlandi/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="password_reset_flow.html",
            extra_context={"stage": "complete"},
        ),
        name="password_reset_complete",
    ),

    # ========================================================
    # 4. TAKVİM GÖRÜNÜMLERİ
    # ========================================================
    path("takvim/", views.genel_takvim, name="genel_takvim"),

    # ========================================================
    # 5. LABORATUVAR VE CİHAZ İŞLEMLERİ
    # ========================================================
    path("lab/<int:lab_id>/", views.lab_detay, name="lab_detay"),
    path("cihaz/<int:cihaz_id>/", views.randevu_al, name="randevu_al"),
    path("ariza-bildir/<int:cihaz_id>/", views.ariza_bildir, name="ariza_bildir"),
    path("sorun-bildir/", views.ariza_bildir_genel, name="ariza_bildir_genel"),
    path('lab/<int:lab_id>/takvim/', views.lab_takvim, name='lab_takvim'),

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

    # Randevu Durum Güncelleme
    path("durum-degis/<int:randevu_id>/<str:yeni_durum>/", views.durum_guncelle, name="durum_guncelle"),

]

# --- MEDYA DOSYALARI ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)