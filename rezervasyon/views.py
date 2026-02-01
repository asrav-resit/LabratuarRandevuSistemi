import json
import logging
import random
import string
from datetime import datetime, timedelta, date

from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse, HttpResponse
from django.db.models import Count
from django.views.decorators.http import require_GET

# Models ve Forms
from .models import Laboratuvar, Cihaz, Randevu, Profil, Duyuru, Ariza, OnayBekleyenler
from .forms import (
    KullaniciGuncellemeFormu,
    ProfilGuncellemeFormu,
    ArizaFormu,
    KayitFormu,
)

# PDF Utility (utils.py dosyanızda olduğundan emin olun)
from .utils import render_to_pdf

logger = logging.getLogger(__name__)

# ===============================
# AYARLAR VE SABİTLER
# ===============================
MAX_RANDEVU_SAATI = getattr(settings, "MAX_RANDEVU_SAATI", 3)
IPTAL_MIN_SURE_SAAT = getattr(settings, "IPTAL_MIN_SURE_SAAT", 1)
OKUL_MAIL_UZANTISI = getattr(settings, "OKUL_MAIL_UZANTISI", "@ogr.btu.edu.tr")

# ===============================
# YARDIMCI FONKSİYONLAR
# ===============================
def check_overlap(cihaz, tarih, baslangic, bitis, exclude_id=None):
    """
    Çakışma kontrolü. Reddedilen ve İptal edilenler çakışma sayılmaz.
    """
    qs = Randevu.objects.filter(
        cihaz=cihaz,
        tarih=tarih,
        # Sadece bu durumlar çakışma yaratır:
        durum__in=[Randevu.ONAY_BEKLENIYOR, Randevu.ONAYLANDI, Randevu.GELDI],
        baslangic_saati__lt=bitis,
        bitis_saati__gt=baslangic,
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


# ===============================
# 1. ANASAYFA
# ===============================
def anasayfa(request):
    labs = Laboratuvar.objects.all()
    duyurular = Duyuru.objects.filter(aktif_mi=True).order_by("-tarih")
    
    context = {"labs": labs, "duyurular": duyurular}

    if request.user.is_authenticated:
        # Sabit kullanımı (Randevu.ONAYLANDI vs) hata yapmayı engeller
        aktif_sorgu = Randevu.objects.filter(
            kullanici=request.user,
            tarih__gte=timezone.now().date(),
            durum__in=[Randevu.ONAYLANDI, Randevu.ONAY_BEKLENIYOR]
        )
        context["aktif_randevu_sayisi"] = aktif_sorgu.count()
        context["siradaki_randevu"] = aktif_sorgu.order_by("tarih", "baslangic_saati").first()

    return render(request, "index.html", context)


# ===============================
# 2. LAB DETAY
# ===============================
def lab_detay(request, lab_id):
    secilen_lab = get_object_or_404(Laboratuvar, id=lab_id)
    cihaz_listesi = Cihaz.objects.filter(lab=secilen_lab)
    return render(request, "lab_detay.html", {"lab": secilen_lab, "cihazlar": cihaz_listesi})


# ===============================
# ===============================
@login_required
def randevu_al(request, cihaz_id):
    secilen_cihaz = get_object_or_404(Cihaz, id=cihaz_id)

    if not secilen_cihaz.aktif_mi:
        messages.error(request, f"⛔ '{secilen_cihaz.isim}' bakımda olduğu için randevuya kapalı.")
        return redirect("lab_detay", lab_id=secilen_cihaz.lab.id)

    # URL'den tarih parametresi gelirse al, yoksa bugünü seç
    secilen_tarih_str = request.GET.get("tarih")
    try:
        if secilen_tarih_str:
            secilen_tarih = datetime.strptime(secilen_tarih_str, "%Y-%m-%d").date()
        else:
            secilen_tarih = datetime.now().date()
    except ValueError:
        secilen_tarih = datetime.now().date()

    # O günkü randevuları listele (Görsel takvim için)
    mevcut_randevular = Randevu.objects.filter(
        cihaz=secilen_cihaz, tarih=secilen_tarih
    ).exclude(durum__in=[Randevu.IPTAL, Randevu.REDDEDILDI]).order_by("baslangic_saati")

    if request.method == "POST":
        gelen_tarih = request.POST.get("tarih")
        gelen_baslangic = request.POST.get("baslangic")
        gelen_bitis = request.POST.get("bitis")

        try:
            t_obj = datetime.strptime(gelen_tarih, "%Y-%m-%d").date()
            b_obj = datetime.strptime(gelen_baslangic, "%H:%M").time()
            bit_obj = datetime.strptime(gelen_bitis, "%H:%M").time()
        except ValueError:
            messages.error(request, "Tarih veya saat formatı hatalı!")
            return redirect(request.path)

        # Validasyonlar
        simdi = datetime.now()
        if t_obj < simdi.date():
            messages.error(request, "⚠️ Geçmiş tarihe randevu alınamaz!")
            return redirect(f"{request.path}?tarih={gelen_tarih}")

        if t_obj == simdi.date() and b_obj < simdi.time():
            messages.error(request, "⚠️ Geçmiş saate randevu alınamaz!")
            return redirect(f"{request.path}?tarih={gelen_tarih}")

        if bit_obj <= b_obj:
            messages.error(request, "⚠️ Bitiş saati başlangıçtan önce olamaz!")
            return redirect(f"{request.path}?tarih={gelen_tarih}")
        
        # Süre Hesabı
        baslangic_tam = datetime.combine(t_obj, b_obj)
        bitis_tam = datetime.combine(t_obj, bit_obj)
        if (bitis_tam - baslangic_tam).total_seconds() > MAX_RANDEVU_SAATI * 3600:
             messages.error(request, f"⚠️ En fazla {MAX_RANDEVU_SAATI} saatlik randevu alabilirsiniz!")
             return redirect(f"{request.path}?tarih={gelen_tarih}")

        # ATOMIC TRANSACTION (Veritabanı Tutarlılığı İçin Şart)
        try:
            with transaction.atomic():
                if check_overlap(secilen_cihaz, t_obj, b_obj, bit_obj):
                    messages.error(request, "⚠️ Bu saat aralığı maalesef DOLU! Lütfen başka saat seçin.")
                    return redirect(f"{request.path}?tarih={gelen_tarih}")

                Randevu.objects.create(
                    kullanici=request.user,
                    cihaz=secilen_cihaz,
                    tarih=t_obj,
                    baslangic_saati=b_obj,
                    bitis_saati=bit_obj,
                    durum=Randevu.ONAY_BEKLENIYOR  # models.py'deki sabiti kullandık
                )
        except Exception as e:
            logger.error(f"Randevu Hatası: {e}")
            messages.error(request, "Sistem hatası oluştu.")
            return redirect(f"{request.path}?tarih={gelen_tarih}")

        # Mail Gönderimi
        try:
            send_mail(
                subject=f"Randevu Talebi: {secilen_cihaz.isim}",
                message=f"Tarih: {gelen_tarih}\nSaat: {gelen_baslangic} - {gelen_bitis}\nDurum: Onay Bekliyor",
                from_email="sistem@okullab.com",
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception:
            pass # Mail gitmezse de randevu oluşsun

        messages.success(request, "✅ Randevunuz başarıyla oluşturuldu, onay bekleniyor!")
        return redirect("randevularim")

    return render(request, "randevu_form.html", {
        "cihaz": secilen_cihaz,
        "mevcut_randevular": mevcut_randevular,
        "secilen_tarih": secilen_tarih.strftime("%Y-%m-%d"),
    })


# ===============================
# 4. RANDEVULARIM
# ===============================
@login_required
def randevularim(request):
    tum_randevular = Randevu.objects.filter(kullanici=request.user).order_by("tarih", "baslangic_saati")
    
    aktif_randevular = []
    gecmis_randevular = []
    simdi = datetime.now()

    for r in tum_randevular:
        try:
            r_zaman = datetime.combine(r.tarih, r.baslangic_saati)
            if r_zaman >= simdi:
                aktif_randevular.append(r)
            else:
                gecmis_randevular.append(r)
        except:
            continue

    return render(request, "randevularim.html", {
        "aktif_randevular": aktif_randevular,
        "gecmis_randevular": reversed(gecmis_randevular),
    })


# ===============================
# 5. İPTAL FONKSİYONU
# ===============================
@login_required
def randevu_iptal(request, randevu_id):
    randevu = get_object_or_404(Randevu, id=randevu_id)

    if randevu.kullanici != request.user:
        messages.error(request, "❌ Başkasının randevusunu silemezsiniz.")
        return redirect("randevularim")

    randevu_tam_zaman = datetime.combine(randevu.tarih, randevu.baslangic_saati)
    simdi = datetime.now()

    # İptal Süresi Kontrolü
    if (randevu_tam_zaman - simdi).total_seconds() < IPTAL_MIN_SURE_SAAT * 3600:
        messages.error(request, f"⚠️ Randevuya {IPTAL_MIN_SURE_SAAT} saatten az kaldığı için iptal edilemez.")
        return redirect("randevularim")

    # Tamamen silmek yerine IPTAL durumuna çekiyoruz (Log tutmak için daha iyidir)
    randevu.durum = Randevu.IPTAL
    randevu.save()
    
    # İstersen tamamen veritabanından silebilirsin: randevu.delete()

    messages.success(request, "✅ Randevu iptal edildi.")
    return redirect("randevularim")


# ===============================
# 6. KAYIT OL (STRICT PASSIVE MODE)
# ===============================
def kayit(request):
    """
    Kullanıcıyı kaydeder ancak HER ZAMAN pasif (is_active=False) yapar.
    Mail doğrulaması sadece kimlik teyidi içindir, hesabı açmaz.
    Son onayı Admin verir.
    """
    if request.method == "POST":
        form = KayitFormu(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # KESİN KURAL: Herkes pasif başlar
            user.is_active = False 
            user.set_password(form.cleaned_data["password"])
            user.save()

            # Profil Oluştur
            profil = user.profil
            profil.okul_numarasi = form.cleaned_data["okul_numarasi"]
            profil.telefon = form.cleaned_data["telefon"]
            
            # Doğrulama Kodu Üret
            kod = "".join(random.choices(string.digits, k=6))
            profil.dogrulama_kodu = kod
            profil.save()

            # Mail Gönder
            try:
                send_mail(
                    "Doğrulama Kodu",
                    f"Merhaba {user.first_name},\n\nKodunuz: {kod}\n\nLütfen doğrulama ekranına giriniz.",
                    "sistem@okullab.com",
                    [user.email],
                    fail_silently=True
                )
            except:
                pass

            request.session["dogrulama_user_id"] = user.id
            messages.info(request, "📧 E-posta adresinize gelen doğrulama kodunu giriniz.")
            return redirect("email_dogrulama")
    else:
        form = KayitFormu()

    return render(request, "kayit.html", {"form": form})


# ===============================
# 7. E-POSTA DOĞRULAMA (AUTO-APPROVE YOK)
# ===============================
def email_dogrulama(request):
    user_id = request.session.get("dogrulama_user_id")
    if not user_id:
        return redirect("giris")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        gelen_kod = request.POST.get("kod")

        if gelen_kod == user.profil.dogrulama_kodu:
            # Kod doğru olsa bile OTOMATİK ONAY YOK (İsteğin üzerine)
            # user.is_active = True  <-- BU SATIR İPTAL EDİLDİ
            
            # Kullanıcıya bilgi verip girişe atıyoruz
            messages.success(request, "✅ E-posta doğrulandı! Hesabınız YÖNETİCİ ONAYINDAN sonra açılacaktır.")
            del request.session["dogrulama_user_id"]
            return redirect("giris")
        else:
            messages.error(request, "❌ Hatalı kod.")

    return render(request, "email_dogrulama.html")


# ===============================
# 8. YÖNETİM PANELİ (STAFF ONLY)
# ===============================
@staff_member_required
def egitmen_paneli(request):
    context = {
        "toplam_randevu": Randevu.objects.count(),
        # Sabit kullanımı
        "bekleyen_onay": Randevu.objects.filter(durum=Randevu.ONAY_BEKLENIYOR).count(),
        "arizali_cihazlar": Cihaz.objects.filter(aktif_mi=False).count(),
        "toplam_kullanici": Profil.objects.filter(user__is_staff=False).count(),
        "bekleyen_randevular": Randevu.objects.filter(durum=Randevu.ONAY_BEKLENIYOR).order_by("tarih"),
        
        # Grafik verileri için
        "lab_verileri": Laboratuvar.objects.annotate(toplam=Count("cihaz__randevu")).order_by("-toplam")
    }
    return render(request, "yonetim_paneli.html", context)


@staff_member_required
def durum_guncelle(request, randevu_id, yeni_durum):
    randevu = get_object_or_404(Randevu, id=randevu_id)
    
    # Gelen durumun modelde tanımlı geçerli bir durum olup olmadığını kontrol et
    gecerli_durumlar = [secenek[0] for secenek in Randevu.DURUM_SECENEKLERI]
    
    if yeni_durum in gecerli_durumlar:
        randevu.durum = yeni_durum
        # Onaylayan admini kaydet
        randevu.onaylayan_admin = request.user
        randevu.save()
        messages.success(request, f"Randevu durumu güncellendi: {yeni_durum}")
    else:
        messages.error(request, "Geçersiz durum.")

    return redirect("egitmen_paneli")


# ===============================
# 9. PDF İNDİRME
# ===============================
@login_required
def randevu_pdf_indir(request):
    # Kullanıcının randevularını al
    randevular = Randevu.objects.filter(kullanici=request.user).order_by("-tarih")
    
    context = {
        "randevular": randevular,
        "user": request.user,
        "tarih": datetime.now()
    }
    # utils.py içindeki fonksiyonu kullan
    return render_to_pdf("randevu_pdf.html", context, filename="lab_randevularim.pdf")


# ===============================
# 10. GENEL TAKVİM & API
# ===============================
@login_required
def genel_takvim(request):
    bugun = date.today()
    baslangic = bugun - timedelta(days=bugun.weekday())
    gunler = [baslangic + timedelta(days=i) for i in range(7)]
    saat_araligi = range(9, 18)
    tum_cihazlar = Cihaz.objects.filter(aktif_mi=True)

    haftalik_veri = []
    for gun in gunler:
        gunluk_saatler = []
        for saat in saat_araligi:
            str_saat = f"{saat:02d}:00"
            cihaz_durumlari = []
            for cihaz in tum_cihazlar:
                # Constants kullanarak filtreleme
                randevu = Randevu.objects.filter(
                    cihaz=cihaz, 
                    tarih=gun, 
                    baslangic_saati__startswith=f"{saat:02d}",
                    durum__in=[Randevu.ONAYLANDI, Randevu.GELDI] # Sadece onaylıları göster
                ).first()
                cihaz_durumlari.append({"cihaz": cihaz, "randevu": randevu})

            gunluk_saatler.append({"saat_etiketi": str_saat, "cihaz_durumlari": cihaz_durumlari})
        haftalik_veri.append({"tarih_obj": gun, "saatler_listesi": gunluk_saatler})

    return render(request, "genel_takvim.html", {"haftalik_veri": haftalik_veri, "tum_cihazlar": tum_cihazlar})


@require_GET
def lab_events(request, lab_id):
    """FullCalendar API Endpoint"""
    lab = get_object_or_404(Laboratuvar, id=lab_id)
    randevular = Randevu.objects.filter(cihaz__lab=lab).exclude(durum=Randevu.IPTAL)

    events = []
    for r in randevular:
        color = "#3788d8" # Bekliyor (Mavi)
        if r.durum == Randevu.ONAYLANDI: color = "#007bff"
        elif r.durum == Randevu.GELDI: color = "#28a745"
        elif r.durum == Randevu.GELMEDI: color = "#dc3545"

        events.append({
            "id": r.id,
            "title": f"{r.cihaz.isim} - {r.kullanici.username}",
            "start": f"{r.tarih}T{r.baslangic_saati}",
            "end": f"{r.tarih}T{r.bitis_saati}",
            "color": color
        })
    return JsonResponse(events, safe=False)


# ===============================
# 11. PROFİL VE DİĞERLERİ
# ===============================
@login_required
def profil_duzenle(request):
    Profil.objects.get_or_create(user=request.user)
    if request.method == "POST":
        u_form = KullaniciGuncellemeFormu(request.POST, instance=request.user)
        p_form = ProfilGuncellemeFormu(request.POST, request.FILES, instance=request.user.profil)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, "✅ Profil güncellendi!")
            return redirect("randevularim")
    else:
        u_form = KullaniciGuncellemeFormu(instance=request.user)
        p_form = ProfilGuncellemeFormu(instance=request.user.profil)
    return render(request, "profil_duzenle.html", {"u_form": u_form, "p_form": p_form})

@login_required
def ariza_bildir(request, cihaz_id):
    cihaz = get_object_or_404(Cihaz, id=cihaz_id)
    if request.method == "POST":
        form = ArizaFormu(request.POST)
        if form.is_valid():
            ariza = form.save(commit=False)
            ariza.kullanici = request.user
            ariza.cihaz = cihaz
            ariza.save()
            messages.warning(request, f"⚠️ '{cihaz.isim}' için arıza bildirimi alındı.")
            return redirect("lab_detay", lab_id=cihaz.lab.id)
    else:
        form = ArizaFormu()
    return render(request, "ariza_bildir.html", {"form": form, "cihaz": cihaz})

@staff_member_required
def onay_bekleyen_sayisi(request):
    sayi = OnayBekleyenler.objects.filter(is_active=False).count()
    return JsonResponse({"sayi": sayi})
# ===============================
#YÖNETİM SAYFALARI
# ===============================

@staff_member_required
def tum_randevular(request):
    """Tüm randevuları listeler (Sadece Yönetici)"""
    randevular = Randevu.objects.all().order_by("-tarih", "-baslangic_saati")
    return render(request, "tum_randevular.html", {"randevular": randevular})


@login_required
def ogrenci_listesi(request):
    """Kayıtlı öğrencileri listeler"""
    if not request.user.is_staff:
        return redirect("anasayfa")
    
    # User modelinden staff olmayanları çekiyoruz (Öğrenciler)
    ogrenciler = Profil.objects.filter(user__is_staff=False)
    return render(request, "yonetim_ogrenciler.html", {"ogrenciler": ogrenciler})


@login_required
def arizali_cihaz_listesi(request):
    """Arızalı cihazları listeler"""
    if not request.user.is_staff:
        return redirect("anasayfa")
    
    cihazlar = Cihaz.objects.filter(aktif_mi=False)
    return render(request, "yonetim_arizali_cihazlar.html", {"cihazlar": cihazlar})


@login_required
def lab_takvim(request, lab_id):
    """Tekil Lab Takvimi Görünümü"""
    lab = get_object_or_404(Laboratuvar, id=lab_id)
    # Bu sayfada takvim verileri API'den (lab_events) çekileceği için 
    # context'e sadece lab bilgisini gönderiyoruz.
    return render(request, "lab_takvim.html", {"lab": lab})

@require_GET
def lab_resources(request, lab_id):
    """FullCalendar Resource View İçin Cihaz Listesi"""
    lab = get_object_or_404(Laboratuvar, id=lab_id)
    cihazlar = Cihaz.objects.filter(lab=lab)
    resources = [{"id": c.id, "title": c.isim} for c in cihazlar]
    return JsonResponse(resources, safe=False)