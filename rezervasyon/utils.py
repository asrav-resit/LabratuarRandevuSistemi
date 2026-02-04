import os
import logging
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# ÖNEMLİ: Fontu sunucu başladığında bir kez kaydetmek Windows hatalarını önler
def register_font():
    try:
        # Görseldeki klasör yapına göre yol: rezervasyon/static/fonts/
        font_path = os.path.join(
            settings.BASE_DIR,
            "rezervasyon",
            "static"
            "fonts",
            "DejaVuSans.ttf"
        )

        if not os.path.exists(font_path):
            font_path = os.path.join(
                settings.BASE_DIR,
                "static",
                "fonts",
                "DejaVuSans.ttf"
            )

        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            return True

    except Exception as e:
        logger.error(f"Font Kayıt Hatası: {e}")

    return False


def link_callback(uri, rel):
    sUrl = settings.STATIC_URL
    sRoot = os.path.join(settings.BASE_DIR, "static")
    mUrl = settings.MEDIA_URL
    mRoot = os.path.join(settings.BASE_DIR, "media")

    if uri.startswith(mUrl):
        path = os.path.join(mRoot, uri.replace(mUrl, ""))

    elif uri.startswith(sUrl):
        path = os.path.join(
            settings.BASE_DIR,
            "rezervasyon",
            "static",
            uri.replace(sUrl, "")
        )
        if not os.path.exists(path):
            path = os.path.join(sRoot, uri.replace(sUrl, ""))

    else:
        return uri

    return path if os.path.isfile(path) else None


def render_to_pdf(template_src="randevu_pdf.html", context_dict=None, filename="btu_rapor.pdf"):
    if context_dict is None:
        context_dict = {}

    # Her üretim öncesi fontun kayıtlı olduğundan emin ol (Windows Fix)
    register_font()

    template = get_template(template_src)
    html = template.render(context_dict)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    pisa_status = pisa.CreatePDF(
        src=html,
        dest=response,
        link_callback=link_callback,
        encoding="UTF-8"
    )

    if pisa_status.err:
        return HttpResponse("PDF Üretilemedi, teknik bir hata oluştu.")

    return response
