/* admin_ozel.js
   - Amaç: Menüdeki her sekmenin (Öğrenci, Randevu, Arıza) yanına kendi bağımsız sayısını ekler.
   - API: views.py içindeki ayrıştırılmış verileri kullanır.
*/
document.addEventListener("DOMContentLoaded", function () {
    const checkMenu = setInterval(() => {
        // İlgili menü linklerini bul
        const ogrenciLink = document.querySelector('a[href*="onaybekleyenler"]');
        const randevuLink = document.querySelector('a[href*="randevu"]');
        const arizaLink = document.querySelector('a[href*="ariza"]');

        // Linkler yüklendiyse işlemi başlat
        if (ogrenciLink || randevuLink || arizaLink) {
            clearInterval(checkMenu);

            fetch('/api/onay-bekleyen-sayisi/')
                .then(res => res.json())
                .then(data => {
                    // 1. Onay Bekleyen Pasif Öğrenciler (image_1c8dc0.png'deki kırmızı balon)
                    if (ogrenciLink && data.pasif_ogrenci > 0) {
                        addBadge(ogrenciLink, data.pasif_ogrenci, "#ff0000"); // Kırmızı
                    }

                    // 2. Bekleyen Randevular (image_792300.png'deki bağımsız sayaç)
                    if (randevuLink && data.bekleyen_randevu > 0) {
                        addBadge(randevuLink, data.bekleyen_randevu, "#ffc107", "#000"); // Sarı
                    }

                    // 3. Açık Arıza Bildirimleri
                    if (arizaLink && data.acik_ariza > 0) {
                        addBadge(arizaLink, data.acik_ariza, "#dc3545"); // Kırmızı/Bordo
                    }
                })
                .catch(err => console.warn('Bildirim verileri alınamadı:', err));
        }
    }, 500);

    // Badge ekleme yardımcı fonksiyonu
    function addBadge(linkElement, count, bgColor, textColor = "#fff") {
        const pTag = linkElement.querySelector('p');
        const targetEl = pTag || linkElement;
        
        // Varsa eski badge'i temizle (çift ikon hatasını önlemek için)
        const oldBadge = targetEl.querySelector('.custom-menu-badge');
        if (oldBadge) oldBadge.remove();

        const badgeHTML = `
            <span class="badge custom-menu-badge" 
                  style="background-color: ${bgColor} !important; 
                         color: ${textColor} !important; 
                         font-weight: bold;
                         margin-left: 10px;
                         padding: 2px 8px;
                         border-radius: 10px;
                         display: inline-block;">
                  ${count}
            </span>`;
        targetEl.insertAdjacentHTML('beforeend', badgeHTML);
    }
});