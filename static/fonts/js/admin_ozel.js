/* admin_ozel.js
   - Amaç: Admin panelinde 'Onay Bekleyenler' linkinin yanına kırmızı badge (sayı)
     ekler. Bu script jazzmin'in `custom_js` ayarı ile yüklendi.
   - Güvenlik: Sadece geliştirme/isteme özel küçük bir fetch çağrısı yapar, DOM
     yüklendikten sonra ilgili link bulunana kadar arama yapar.
*/
document.addEventListener("DOMContentLoaded", function () {
    const checkMenu = setInterval(() => {
        const onayLink = document.querySelector('a[href*="onaybekleyenler"]');
        if (onayLink) {
            clearInterval(checkMenu);
            fetch('/api/onay-bekleyen-sayisi/')
                .then(res => {
                    if (!res.ok) throw new Error('Network response not ok');
                    const contentType = res.headers.get('content-type') || '';
                    if (!contentType.includes('application/json')) throw new Error('Expected JSON response');
                    return res.json();
                })
                .then(data => {
                    if (data.sayi > 0) {
                        const pTag = onayLink.querySelector('p');
                        const targetEl = pTag || onayLink;
                        const badgeHTML = `
                            <span class="badge" 
                                  style="background-color: #ff0000 !important; 
                                         color: #000000 !important; 
                                         font-weight: bold;
                                         margin-left: 10px;
                                         padding: 2px 8px;
                                         border-radius: 10px;
                                         display: inline-block;">
                                  ${data.sayi}
                            </span>`;
                        targetEl.insertAdjacentHTML('beforeend', badgeHTML);
                    }
                })
                .catch(err => console.warn('Onay bekleyen sayısı alınamadı:', err));
        }
    }, 500);
});