"""
rezervasyon.forms

Bu modül, kullanıcı etkileşimi için gerekli formları içerir.
Bootstrap 5 uyumlu widget'lar ve özel validasyon kuralları eklenmiştir.
"""

from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from .models import Profil, Ariza

# --- ÖZEL VALİDATÖRLER ---
sadece_rakam_validator = RegexValidator(
    regex=r"^\d+$",
    message="Lütfen sadece rakam giriniz (Boşluk veya harf kullanmayınız).",
)

# --- TARİH VE SAAT SEÇİCİLER (HTML5) ---
class DateInput(forms.DateInput):
    input_type = 'date'

class TimeInput(forms.TimeInput):
    input_type = 'time'


# 1. KAYIT FORMU
class KayitFormu(forms.ModelForm):
    # Standart User alanlarına Bootstrap stili ve placeholder ekliyoruz
    username = forms.CharField(
        label="Kullanıcı Adı",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Kullanıcı adınızı seçin"})
    )
    email = forms.EmailField(
        label="E-Posta Adresi",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "ogrenci@okul.edu.tr"})
    )
    first_name = forms.CharField(
        label="Adınız", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Adınız"})
    )
    last_name = forms.CharField(
        label="Soyadınız", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Soyadınız"})
    )
    password = forms.CharField(
        label="Şifre",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "********"})
    )
    password_confirm = forms.CharField(
        label="Şifre Tekrar",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "********"})
    )

    # Profil Modeli için ekstra alanlar
    okul_numarasi = forms.CharField(
        label="Okul Numarası",
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Örn: 2025101"})
    )
    telefon = forms.CharField(
        label="Telefon Numarası",
        required=True,
        validators=[sadece_rakam_validator],
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "05551234567",
            "maxlength": "11",
            "oninput": "this.value = this.value.replace(/[^0-9]/g, '');" # Sadece rakama izin ver (JS)
        }),
        help_text="Başında 0 olacak şekilde yazınız."
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "password"]

    def clean_email(self):
        # E-posta benzersiz olmalı
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Bu e-posta adresi zaten kullanımda.")
        return email

    def clean(self):
        # Şifreler eşleşiyor mu kontrolü
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password_confirm")

        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Şifreler birbiriyle eşleşmiyor.")


# 2. KULLANICI BİLGİLERİ GÜNCELLEME
class KullaniciGuncellemeFormu(forms.ModelForm):
    first_name = forms.CharField(
        label="Adınız", widget=forms.TextInput(attrs={"class": "form-control"})
    )
    last_name = forms.CharField(
        label="Soyadınız", widget=forms.TextInput(attrs={"class": "form-control"})
    )
    email = forms.EmailField(
        label="E-Posta", widget=forms.EmailInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]


# 3. PROFİL (FOTO & TELEFON) GÜNCELLEME
class ProfilGuncellemeFormu(forms.ModelForm):
    telefon = forms.CharField(
        label="Telefon Numarası",
        required=True,
        validators=[sadece_rakam_validator],
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "05551234567",
            "maxlength": "11",
            "oninput": "this.value = this.value.replace(/[^0-9]/g, '');"
        })
    )
    okul_numarasi = forms.CharField(
        label="Okul Numarası",
        required=False, # Genelde okul no değişmez ama admin düzeltebilir
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    resim = forms.ImageField(
        label="Profil Resmi",
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = Profil
        fields = ["telefon", "okul_numarasi", "resim"]


# 4. ARIZA BİLDİRİM FORMU
class ArizaFormu(forms.ModelForm):
    aciklama = forms.CharField(
        label="Arıza Detayı",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Lütfen karşılaştığınız sorunu detaylıca anlatınız..."
        })
    )

    class Meta:
        model = Ariza
        fields = ["aciklama"]