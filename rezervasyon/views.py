import json
import logging
import random
import string
from datetime import datetime, timedelta

# --- DJANGO IMPORTS ---
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail, EmailMultiAlternatives # EmailMultiAlternatives buraya taşındı
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count
from django.db import transaction
from django.urls import reverse # 🟢 URL tersine çözümleme için eklendi

# --- ŞİFRE SIFIRLAMA İÇİN GEREKLİLER ---
from django.contrib.auth.tokens import default_token_generator # 🟢 NameError hatasını çözen kritik satır
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags # 🟢 Mail gövdesindeki HTML'i temizlemek için

# --- MODELS & FORMS ---
from .models import Laboratuvar, Cihaz, Randevu, Profil, Duyuru, Ariza
from .forms import (
    KullaniciGuncellemeFormu,
    ProfilGuncellemeFormu,
    ArizaFormu,
    KayitFormu,
    EmailOrUsernameAuthenticationForm,
)

# --- UTILS ---
from .utils import render_to_pdf # 🟢 PDF çıktısı almak için eklendi

logger = logging.getLogger(__name__)

class CustomLoginView(auth_views.LoginView):
    template_name = "giris.html"
    form_class = EmailOrUsernameAuthenticationForm

    def form_invalid(self, form):
        # If authentication failed, check whether an account exists but is inactive
        identifier = self.request.POST.get("username", "").strip()
        pasif_mesaj = None
        if identifier:
            # Look up by username or email
            user_qs = User.objects.filter(username__iexact=identifier) | User.objects.filter(email__iexact=identifier)
            user = user_qs.first()
            if user and not user.is_active:
                pasif_mesaj = (
                    "Hesabınız henüz aktif değil veya onay bekliyor. "
                    "Lütfen yöneticinizle iletişime geçin veya kayıt e-postanızı kontrol edin."
                )

        context = self.get_context_data(form=form)
        if pasif_mesaj:
            context["pasif_mesaj"] = pasif_mesaj
        return self.render_to_response(context)

# ============================================================
# 1️⃣ AYARLAR & YARDIMCI FONKSİYONLAR
# ============================================================
MAX_RANDEVU_SAATI = getattr(settings, "MAX_RANDEVU_SAATI", 3)
IPTAL_MIN_SURE_SAAT = getattr(settings, "IPTAL_MIN_SURE_SAAT", 1)

def check_overlap(cihaz, tarih, baslangic, bitis, exclude_id=None):
    """Çakışma kontrolü: Aynı saatte başka randevu var mı?"""
    qs = Randevu.objects.filter(
        cihaz=cihaz,
        tarih=tarih,
        durum__in=[Randevu.ONAY_BEKLENIYOR, Randevu.ONAYLANDI, Randevu.GELDI],
        baslangic_saati__lt=bitis,
        bitis_saati__gt=baslangic,
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()

# ============================================================
# 2️⃣ ANA SAYFA & LABORATUVAR GÖRÜNÜMLERİ
# ============================================================
def anasayfa(request):
    labs = Laboratuvar.objects.all()
    duyurular = Duyuru.objects.filter(aktif_mi=True).order_by("-tarih")
    context = {"labs": labs, "duyurular": duyurular}

    if request.user.is_authenticated:
        aktif_sorgu = Randevu.objects.filter(
            kullanici=request.user,
            tarih__gte=timezone.now().date(),
            durum__in=[Randevu.ONAYLANDI, Randevu.ONAY_BEKLENIYOR]
        )
        context["aktif_randevu_sayisi"] = aktif_sorgu.count()
        context["siradaki_randevu"] = aktif_sorgu.order_by("tarih", "baslangic_saati").first()

    return render(request, "index.html", context)

def lab_detay(request, lab_id):
    secilen_lab = get_object_or_404(Laboratuvar, id=lab_id)
    cihaz_listesi = Cihaz.objects.filter(lab=secilen_lab)
    return render(request, "lab_detay.html", {"lab": secilen_lab, "cihazlar": cihaz_listesi})

# ============================================================
# 3️⃣ TAKVİM SİSTEMİ (FULLCALENDAR API)
# ============================================================
@login_required
def genel_takvim(request):
    """Tüm laboratuvarların ortak takvimi"""
    cihazlar_sorgu = Cihaz.objects.filter(aktif_mi=True).values('id', 'isim', 'lab__isim')
    cihazlar = [{'id': c['id'], 'isim': f"{c['lab__isim']} ➝ {c['isim']}"} for c in cihazlar_sorgu]
    cihazlar_json = json.dumps(cihazlar, cls=DjangoJSONEncoder)
    return render(request, "genel_takvim.html", {"cihazlar_json": cihazlar_json})

@login_required
def tum_events_api(request):
    """
    Genel Takvim API: Geçmiş sonuçlananlar ve Gelecek planlılar.
    Çift ikon ve taşma sorununu önlemek için sadeleştirilmiştir.
    """
    bugun = timezone.now().date()
    randevular = Randevu.objects.all()
    events = []

    color_map = {
        Randevu.ONAYLANDI: "#28a745", Randevu.ONAY_BEKLENIYOR: "#ffc107",
        Randevu.GELDI: "#0d6efd", Randevu.GELMEDI: "#6c757d", Randevu.REDDEDILDI: "#dc3545",
    }

    for r in randevular:
        goster = (r.tarih >= bugun and r.durum in [Randevu.ONAY_BEKLENIYOR, Randevu.ONAYLANDI]) or \
                 (r.tarih < bugun and r.durum in [Randevu.GELDI, Randevu.GELMEDI])

        if goster:
            events.append({
                'title': f"{r.cihaz.isim} • {r.baslangic_saati.strftime('%H:%M')}-{r.bitis_saati.strftime('%H:%M')}",
                'start': f"{r.tarih.isoformat()}T{r.baslangic_saati.strftime('%H:%M:%S')}",
                'end': f"{r.tarih.isoformat()}T{r.bitis_saati.strftime('%H:%M:%S')}",
                'color': color_map.get(r.durum, "#3788d8"),
                'extendedProps': {
                    'lab_adi': r.cihaz.lab.isim,
                    'kullanici': r.kullanici.username,
                    'durum': r.get_durum_display()
                }
            })
    return JsonResponse(events, safe=False)

@login_required
def lab_takvim(request, lab_id):
    lab = get_object_or_404(Laboratuvar, id=lab_id)
    cihazlar = list(Cihaz.objects.filter(lab=lab, aktif_mi=True).values('id', 'isim'))
    return render(request, "lab_takvim.html", {"lab": lab, "cihazlar_json": json.dumps(cihazlar, cls=DjangoJSONEncoder)})

@login_required
def lab_events_api(request, lab_id):
    bugun = timezone.now().date()
    randevular = Randevu.objects.filter(cihaz__lab_id=lab_id)
    events = []
    for r in randevular:
        if (r.tarih >= bugun and r.durum in [Randevu.ONAY_BEKLENIYOR, Randevu.ONAYLANDI]) or \
           (r.tarih < bugun and r.durum in [Randevu.GELDI, Randevu.GELMEDI]):
            events.append({
                'title': f"{r.cihaz.isim} • {r.baslangic_saati.strftime('%H:%M')}-{r.bitis_saati.strftime('%H:%M')}",
                'start': f"{r.tarih.isoformat()}T{r.baslangic_saati.strftime('%H:%M:%S')}",
                'end': f"{r.tarih.isoformat()}T{r.bitis_saati.strftime('%H:%M:%S')}",
                'color': "#28a745" if r.durum == Randevu.ONAYLANDI else "#ffc107",
                'extendedProps': {'kullanici': r.kullanici.username, 'durum': r.get_durum_display()}
            })
    return JsonResponse(events, safe=False)

# ============================================================
# 4️⃣ KULLANICI İŞLEMLERİ (RANDEVU ALMA & PROFİL)
# ============================================================
@login_required
def randevu_al(request, cihaz_id):
    secilen_cihaz = get_object_or_404(Cihaz, id=cihaz_id)
    if not secilen_cihaz.aktif_mi:
        messages.error(request, f"⛔ '{secilen_cihaz.isim}' bakımda.")
        return redirect("lab_detay", lab_id=secilen_cihaz.lab.id)

    secilen_tarih_str = request.GET.get("tarih")
    secilen_tarih = datetime.strptime(secilen_tarih_str, "%Y-%m-%d").date() if secilen_tarih_str else datetime.now().date()

    if request.method == "POST":
        try:
            t_obj = datetime.strptime(request.POST.get("tarih"), "%Y-%m-%d").date()
            b_obj = datetime.strptime(request.POST.get("baslangic"), "%H:%M").time()
            bit_obj = datetime.strptime(request.POST.get("bitis"), "%H:%M").time()
        except Exception:
            messages.error(request, "⚠️ Geçersiz tarih/saati formatı gönderildi.")
            return redirect("randevu_al", cihaz_id=cihaz_id)

        # Transaction içinde tekrar kontrol ederek race condition riskini azalt
        with transaction.atomic():
            if check_overlap(secilen_cihaz, t_obj, b_obj, bit_obj):
                messages.error(request, "⚠️ Bu saat aralığı DOLU!")
            else:
                Randevu.objects.create(kullanici=request.user, cihaz=secilen_cihaz, tarih=t_obj, baslangic_saati=b_obj, bitis_saati=bit_obj)
                messages.success(request, "✅ Randevu oluşturuldu, onay bekleniyor.")
                return redirect("randevularim")

        # Eğer POST ile gelindiyse, template'de seçilen tarihi POST verisinden göster
        secilen_tarih = t_obj

    # Mevcut randevuları sağ tarafta listelemek için template'in beklediği
    # context anahtarını sağlayalım.
    mevcut_randevular = Randevu.objects.filter(cihaz=secilen_cihaz, tarih=secilen_tarih).order_by("baslangic_saati")
    return render(request, "randevu_form.html", {"cihaz": secilen_cihaz, "secilen_tarih": secilen_tarih.strftime("%Y-%m-%d"), "mevcut_randevular": mevcut_randevular})

@login_required
def randevularim(request):
    # Tüm randevuları çekiyoruz
    tum = Randevu.objects.filter(kullanici=request.user).order_by("tarih", "baslangic_saati")
    simdi = datetime.now()

    # AKTİF RANDEVULAR:
    # 1. Zamanı henüz geçmemiş olmalı
    # 2. Durumu 'Onay Bekliyor' veya 'Onaylandı' olmalı (Reddedilenler veya iptaller burada görünmemeli)
    aktif = [
        r for r in tum 
        if datetime.combine(r.tarih, r.baslangic_saati) >= simdi 
        and r.durum in ['onay_bekleniyor', 'onaylandi']
    ]

    # GEÇMİŞ / PASİF RANDEVULAR:
    # 1. Zamanı geçmiş olanlar VEYA 
    # 2. Reddedilmiş/İptal edilmiş olanlar (Zamanı gelecek olsa bile pasif sayılırlar)
    gecmis = [
        r for r in tum 
        if datetime.combine(r.tarih, r.baslangic_saati) < simdi 
        or r.durum in ['reddedildi', 'iptal_edildi']
    ]

    return render(request, "randevularim.html", {
        "aktif_randevular": aktif, 
        "gecmis_randevular": reversed(gecmis)
    })
@login_required
def profil_duzenle(request):
    if request.method == "POST":
        u_form = KullaniciGuncellemeFormu(request.POST, instance=request.user)
        p_form = ProfilGuncellemeFormu(request.POST, request.FILES, instance=request.user.profil)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save(); p_form.save()
            messages.success(request, "✅ Profil güncellendi!")
            return redirect("randevularim")
    else:
        u_form = KullaniciGuncellemeFormu(instance=request.user)
        p_form = ProfilGuncellemeFormu(instance=request.user.profil)
    return render(request, "profil_duzenle.html", {"u_form": u_form, "p_form": p_form})

# ============================================================
# 5️⃣ YÖNETİM & BİLDİRİM API 
# ============================================================
@staff_member_required
def onay_bekleyen_sayisi(request):
    """
    Sol menüdeki bildirimleri (badge) ait oldukları sekmelere dağıtır.
    Pasif öğrenciler ve Bekleyen randevular artık ayrı sayılır.
    """
    # 1. Onay Bekleyen Pasif Öğrenciler (image_1c8dc0.png'deki kırmızı balon için)
    pasif_ogrenci = User.objects.filter(is_active=False).count()
    
    # 2. Onay Bekleyen Randevular (image_792300.png'de menünün yanındaki sayaç için)
    bekleyen_randevu = Randevu.objects.filter(durum='onay_bekleniyor').count()
    
    # 3. Çözülmemiş Arıza Bildirimleri
    acik_ariza = Ariza.objects.filter(cozuldu_mu=False).count()
    
    return JsonResponse({
        "pasif_ogrenci": pasif_ogrenci,
        "bekleyen_randevu": bekleyen_randevu,
        "acik_ariza": acik_ariza
    })

@staff_member_required
def egitmen_paneli(request):
    context = {
        "toplam_randevu": Randevu.objects.count(),
        "bekleyen_onay": Randevu.objects.filter(durum=Randevu.ONAY_BEKLENIYOR).count(),
        "bekleyen_randevular": Randevu.objects.filter(durum=Randevu.ONAY_BEKLENIYOR).order_by("tarih"),
    }
    return render(request, "yonetim_paneli.html", context)

@staff_member_required
def durum_guncelle(request, randevu_id, yeni_durum):
    r = get_object_or_404(Randevu, id=randevu_id)
    r.durum = yeni_durum; r.onaylayan_admin = request.user; r.save()
    return redirect("egitmen_paneli")

@login_required
def ariza_bildir(request, cihaz_id):
    """Arıza bildirildiğinde ilgili sayaç otomatik güncellenir."""
    cihaz = get_object_or_404(Cihaz, id=cihaz_id)
    if request.method == "POST":
        form = ArizaFormu(request.POST)
        if form.is_valid():
            ariza = form.save(commit=False); ariza.kullanici = request.user; ariza.cihaz = cihaz; ariza.save()
            messages.warning(request, "⚠️ Arıza bildirimi alındı."); return redirect("lab_detay", lab_id=cihaz.lab.id)
    return render(request, "ariza_bildir.html", {"form": ArizaFormu(), "cihaz": cihaz})

# Boş kalan fonksiyonlar (URL uyumu için)# rezervasyon/views.py
import random
from django.core.mail import send_mail

def kayit(request):
    if request.method == "POST":
        form = KayitFormu(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # 🔴 Burası kritik: Kullanıcıyı PASİF yapar
            user.save() 
            
            # Doğrulama kodu üret ve session'a at
            dogrulama_kodu = str(random.randint(100000, 999999))
            request.session['dogrulama_kodu'] = dogrulama_kodu
            request.session['dogrulama_user_id'] = user.id

            # Mail gönderimi
            try:
                send_mail(
                    "BTÜ Lab Kayıt Doğrulama",
                    f"Doğrulama kodunuz: {dogrulama_kodu}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False
                )
            except Exception as e:
                print(f"Mail Hatası: {e}") # Hatayı sunucu logunda görebilirsin

            messages.success(request, "Kayıt başarılı! Lütfen mailine gelen kodu gir.")
            return redirect("email_dogrulama")
    else:
        form = KayitFormu()
    return render(request, "kayit.html", {"form": form})

def email_dogrulama(request):
    user_id = request.session.get('dogrulama_user_id')
    dogrulama_kodu = request.session.get('dogrulama_kodu')
    
    if not user_id or not dogrulama_kodu:
        return redirect("kayit")

    if request.method == "POST":
        girilen_kod = request.POST.get("kod")
        
        # Sabit '123456' yerine session'daki rastgele kodu kontrol ediyoruz
        if girilen_kod == dogrulama_kodu: 
            from django.contrib.auth.models import User
            user = get_object_or_404(User, id=user_id)
            user.is_active = True # 🟢 Şimdi aktif ediyoruz
            user.save()
            
            del request.session['dogrulama_user_id']
            del request.session['dogrulama_kodu']
            
            messages.success(request, "🎉 Hesabınız doğrulandı! Giriş yapabilirsiniz.")
            return redirect("giris")
        else:
            messages.error(request, "❌ Hatalı doğrulama kodu.")

    return render(request, "email_dogrulama.html")
@login_required
def randevu_pdf_indir(request):
    randevular = (
        Randevu.objects
        .filter(kullanici=request.user)
        .order_by("tarih", "baslangic_saati")
    )

    context = {
        "user": request.user,
        "randevular": randevular,
    }

    filename = f"randevular_{request.user.username}.pdf"

    return render_to_pdf(
        "randevu_pdf.html", 
        context, 
        filename
    )
@staff_member_required
def ogrenci_listesi(request): return render(request, "yonetim_ogrenciler.html", {"ogrenciler": Profil.objects.all()})
@staff_member_required
def arizali_cihaz_listesi(request): return render(request, "yonetim_arizali_cihazlar.html", {"cihazlar": Cihaz.objects.filter(aktif_mi=False)})
@staff_member_required
def tum_randevular(request): return render(request, "tum_randevular.html", {"randevular": Randevu.objects.all()})
@login_required
def randevu_iptal(request, randevu_id):
    # Randevuyu bul, eğer kullanıcıya ait değilse 404 döndür (Güvenlik için)
    randevu = get_object_or_404(Randevu, id=randevu_id, kullanici=request.user)
    
    # Sadece 'Onay Bekliyor' veya 'Onaylandı' durumundaki randevular iptal edilebilir
    if randevu.durum in ['onay_bekleniyor', 'onaylandi']:
        randevu.durum = 'iptal_edildi'  # Durumu güncelle
        randevu.save()
        messages.success(request, "Randevunuz başarıyla iptal edildi.")
    else:
        messages.error(request, "Bu randevu şu anki durumu nedeniyle iptal edilemez.")
        
    return redirect("randevularim")
@login_required
def ariza_bildir_genel(request):
    if request.method == 'POST':
        aciklama = request.POST.get('aciklama')
        # Sistemde bildirim atanacak bir cihaz bulalım
        cihaz = Cihaz.objects.first() 
        
        if cihaz:
            Ariza.objects.create(
                cihaz=cihaz,
                kullanici=request.user,
                aciklama=f"[GENEL SİSTEM SORUNU]: {aciklama}",
                cozuldu_mu=False
            )
            messages.success(request, "Sorun bildiriminiz yöneticiye iletildi.")
        else:
            messages.error(request, "Sistemde kayıtlı cihaz bulunamadığı için bildirim yapılamadı.")
            
    return redirect(request.META.get('HTTP_REFERER', 'anasayfa'))
# ============================================================
#ŞİFRE SIFIRLAMA GÖRÜNÜMLERİ
# ============================================================# 
def sifre_sifirla_talep(request):
    if request.method == "POST":
        email = request.POST.get('email')
        user = User.objects.filter(email=email).first()
        
        if user:
            # Token ve ID oluşturma
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            protocol = 'https' if request.is_secure() else 'http'
            domain = request.get_host()
            
            # --- BURADAN İTİBAREN SENİN KODUN BAŞLIYOR ---
            
            # 1. HTML İçeriği Hazırla
            html_content = render_to_string(
                "password_reset_email.html", 
                {
                    'user': user,
                    'reset_link': f"{protocol}://{domain}{reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})}"
                }
            )

            # 2. Düz Metin Halini Oluştur
            text_content = strip_tags(html_content)

            # 3. Çok Alternatifli E-posta Nesnesini Oluştur
            email_obj = EmailMultiAlternatives(
                subject="BTÜ Lab Sistemi | Şifre Sıfırlama",
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )

            # 4. HTML Versiyonunu Ekle ve Gönder
            email_obj.attach_alternative(html_content, "text/html")
            email_obj.send()
            
            # --- KODUN BURADA BİTİYOR ---

            messages.success(request, "✅ Şifre sıfırlama bağlantısı e-posta adresinize gönderildi.")
            return render(request, "password_reset_flow.html", {"stage": "done"})
        else:
            messages.error(request, "❌ Bu e-posta adresiyle kayıtlı bir kullanıcı bulunamadı.")
            
    return render(request, "password_reset_flow.html", {"stage": "form"})

# ============================================================
#yeni doğrulama kodu gonderme
# ============================================================
def kod_tekrar_gonder(request):
    user_id = request.session.get('dogrulama_user_id')
    
    if not user_id:
        messages.error(request, "Oturum süresi dolmuş, lütfen tekrar kayıt olun.")
        return redirect('kayit')

    from django.contrib.auth.models import User
    user = User.objects.get(id=user_id)
    
    # Yeni kod üret ve session'ı güncelle
    yeni_kod = str(random.randint(100000, 999999))
    request.session['dogrulama_kodu'] = yeni_kod
    
    try:
        send_mail(
            "BTÜ Lab Sistemi | Yeni Doğrulama Kodu",
            f"Merhaba {user.username}, yeni doğrulama kodunuz: {yeni_kod}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        messages.success(request, "✅ Yeni doğrulama kodu e-posta adresinize gönderildi.")
    except Exception as e:
        messages.error(request, "❌ Kod gönderilirken bir hata oluştu.")

    return redirect('email_dogrulama')