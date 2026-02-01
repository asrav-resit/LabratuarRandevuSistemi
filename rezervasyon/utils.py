import os
import logging
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

# reportlab imports are used at runtime to register fonts to avoid
# xhtml2pdf/tmp font extraction issues on Windows
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError

"""rezervasyon.utils

Bu modül PDF üretimi için yardımcı fonksiyonlar içerir.
- link_callback: xhtml2pdf tarafından çağrılan bir callback'tir; static/media yollarını
  gerçek dosya sistemindeki tam path'e dönüştürür.
- render_to_pdf: Verilen Django template'inden PDF üretir ve HttpResponse döner.

Not: Windows'ta geçici TTF açma hatalarına karşı DejaVuSans'ın programatik olarak
ReportLab'e kayıt edilmesi denenir; başarısız olursa fallback olarak CSS'de
"sans-serif" kullanılarak tekrar denenir.
"""

logger = logging.getLogger(__name__)


def link_callback(uri, rel):
    """XHTML2PDF link_callback helper.

    Açıklama:
    - Bu fonksiyon xhtml2pdf (pisa) tarafından statik/media URL'lerini fiziksel
      dosya yollarına çevirmek için çağrılır.
    - Eğer istenen dosya DejaVuSans.ttf ise doğrudan proje içindeki static/fonts
      klasörüne bakar (ReportLab için kullanılır).

    Kullanıldığı yer:
    - `render_to_pdf` içinde `pisa.CreatePDF(..., link_callback=link_callback)` olarak.

    Parametreler:
    - uri: HTML içinde geçen /static/... veya /media/... URL'i
    - rel: göreli yol (genelde kullanılmaz)

    Döndürür:
    - Dosyanın absolute path'i veya None (bulunamazsa)
    """
    # 1. Eğer istenen dosya bizim fontumuzsa, doğrudan fiziksel yola bak
    if "DejaVuSans.ttf" in uri:
        path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf")
        if os.path.exists(path):
            return path
        else:
            # Yedek: Eğer BASE_DIR/static içinde yoksa, belki collectstatic ile
            # STATIC_ROOT içine kopyalanmıştır; uyarı log'la kaydedilir
            logger.warning(f"UYARI: Font bu yolda bulunamadı: {path}")

    # 2. Standart Static/Media kontrolü
    sUrl = settings.STATIC_URL  # /static/
    sRoot = os.path.join(settings.BASE_DIR, "static")
    mUrl = settings.MEDIA_URL  # /media/
    mRoot = os.path.join(settings.BASE_DIR, "media")

    if uri.startswith(mUrl):
        path = os.path.join(mRoot, uri.replace(mUrl, ""))
    elif uri.startswith(sUrl):
        path = os.path.join(sRoot, uri.replace(sUrl, ""))
    else:
        # Eğer özel bir URL ise olduğu gibi döndür (xhtml2pdf bazen data: veya http: kullanır)
        return uri

    # Windows uyumluluğu için: path gerçekten dosya mı kontrol et
    if not os.path.isfile(path):
        # Bulamazsa, None döndür; pisa bu durumda hatayı log'lar
        logger.warning(f"Dosya bulunamadı: {path}")
        return None

    return path


def render_to_pdf(template_src, context_dict=None, filename="lab_randevu_fisi.pdf"):
    """Belirtilen template'ten PDF oluşturur ve HttpResponse döner.

    Kullanım:
    - `views.randevu_pdf_indir` gibi yerlerden çağrılır.

    Parametreler:
    - template_src: Template yolu (örn. 'randevu_pdf.html')
    - context_dict: Template render için bağlam sözlüğü
    - filename: Tarayıcıya gönderilecek varsayılan dosya adı (Content-Disposition)

    Davranış:
    - Programatik olarak DejaVuSans ttf kaydı denenir (ReportLab'e). Bu, Türkçe karakter
      içeren PDF'lerde doğru gösterim için önemlidir.
    - Windows'ta TTF açma hatası (TTFError) alınırsa, font-family'i 'sans-serif' ile
      değiştirip yeniden deneme yapılır (fallback).
    """
    if context_dict is None:
        context_dict = {}

    # Deneme: DejaVuSans varsa ReportLab'e kaydedelim (xhtml2pdf'nin tmp font açma hatalarını azaltmak için)
    try:
        font_path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf")
        if (
            os.path.exists(font_path)
            and "DejaVuSans" not in pdfmetrics.getRegisteredFontNames()
        ):
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
    except Exception as e:
        # Kayıt başarısız olursa uyarı log'la; yine de PDF üretimine devam etmeye çalışırız
        logger.warning(f"Font register failed: {e}")

    template = get_template(template_src)
    html = template.render(context_dict)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    try:
        pisa_status = pisa.CreatePDF(
            src=html, dest=response, link_callback=link_callback, encoding="UTF-8"
        )
    except TTFError as e:
        # TTF ile ilgili hata alırsak, UTF-8 ile yeniden deneyelim fakat font-family'i düzeltelim
        logger.warning(
            f"TTFError during PDF creation: {e} — retrying without custom font."
        )
        html_fallback = html.replace("DejaVuSans", "sans-serif")
        pisa_status = pisa.CreatePDF(
            src=html_fallback,
            dest=response,
            link_callback=link_callback,
            encoding="UTF-8",
        )

    if pisa_status.err:
        # Hata varsa, debug amaçlı oluşturulan HTML'i response'la gösteriyoruz (geliştirme ortamında yardımcı olur)
        logger.error(
            "PDF oluşturulurken hata: %s", getattr(pisa_status, "err", "unknown")
        )
        return HttpResponse("PDF Hatası: <pre>" + html + "</pre>")

    return response
