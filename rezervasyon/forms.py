from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator
from .models import Profil, Ariza

# --- CUSTOM LOGIN FORMU (EMAIL + USERNAME DESTEĞİ) ---
class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form that accepts either username or email.
    Uses the custom backend EmailOrUsernameModelBackend.
    """
    username = forms.CharField(
        max_length=254,
        widget=forms.TextInput(attrs={
            'autofocus': True,
            'class': 'form-control',
            'placeholder': 'Kullanıcı adı veya e-posta'
        })
    )
    password = forms.CharField(
        label="Şifre",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'class': 'form-control',
            'placeholder': '******'
        }),
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        # Form labels'i Türkçe yap
        self.fields['username'].label = "Kullanıcı Adı veya E-Posta"

# --- ÖZEL VALİDATÖRLER ---
sadece_rakam_validator = RegexValidator(
    regex=r"^\d+$",
    message="Lütfen sadece rakam giriniz (Boşluk veya harf kullanmayınız).",
)

# --- KAYIT FORMU (GÜNCELLENDİ) ---
class KayitFormu(forms.ModelForm):
    username = forms.CharField(
        label="Kullanıcı Adı",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Kullanıcı adınızı seçin"})
    )
    first_name = forms.CharField(
        label="Adınız", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Adınız"})
    )
    last_name = forms.CharField(
        label="Soyadınız", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Soyadınız"})
    )
    email = forms.EmailField(
        label="E-Posta Adresi",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "ogrenci@okul.edu.tr"})
    )
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
            "oninput": "this.value = this.value.replace(/[^0-9]/g, '');"
        }),
        help_text="Başında 0 olacak şekilde yazınız."
    )
    password = forms.CharField(
        label="Şifre",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "********"})
    )
    password_confirm = forms.CharField(
        label="Şifre Tekrar",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "********"})
    )

    class Meta:
        model = User
        # USER modeline ait alanlar. Profil alanları (okul_numarasi, telefon)
        # form üzerinde tutuluyor ancak ModelForm.Meta.fields sadece model
        # alanlarını içermelidir.
        fields = ["username", "first_name", "last_name", "email", "password"]

    def save(self, commit=True):
        """Create User with hashed password and populate/create Profil.

        Notes:
        - `okul_numarasi` and `telefon` are stored on `Profil` model.
        - post_save signal may create a Profil; ensure profil exists and set fields.
        """
        user = super().save(commit=False)
        pwd = self.cleaned_data.get("password")
        if pwd:
            user.set_password(pwd)
        if commit:
            user.save()
            # Ensure profile exists and save profile fields
            try:
                profil = user.profil
            except Profil.DoesNotExist:
                profil = Profil.objects.create(user=user)

            okul = self.cleaned_data.get("okul_numarasi")
            telefon = self.cleaned_data.get("telefon")
            if okul:
                profil.okul_numarasi = okul
            if telefon:
                profil.telefon = telefon
            profil.save()

        return user

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Bu e-posta adresi zaten kullanımda.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Şifreler birbiriyle eşleşmiyor.")
        return cleaned_data

# --- DİĞER FORMLAR AYNI KALIYOR ---
class KullaniciGuncellemeFormu(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }

class AdminMassEmailForm(forms.Form):
    subject = forms.CharField(max_length=200, label="Konu", widget=forms.TextInput(attrs={'class': 'vTextField'}))
    message = forms.CharField(label="Mesaj", widget=forms.Textarea(attrs={'rows': 8, 'class': 'vLargeTextField'}))
    is_html = forms.BooleanField(required=False, initial=False, label="HTML olarak gönder")

class ProfilGuncellemeFormu(forms.ModelForm):
    class Meta:
        model = Profil
        fields = ["telefon", "okul_numarasi", "resim"]
        widgets = {
            "telefon": forms.TextInput(attrs={"class": "form-control", "maxlength": "11"}),
            "okul_numarasi": forms.TextInput(attrs={"class": "form-control"}),
            "resim": forms.FileInput(attrs={"class": "form-control"}),
        }

class ArizaFormu(forms.ModelForm):
    class Meta:
        model = Ariza
        fields = ["aciklama"]
        widgets = {
            "aciklama": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Arıza detayını yazınız..."})
        }