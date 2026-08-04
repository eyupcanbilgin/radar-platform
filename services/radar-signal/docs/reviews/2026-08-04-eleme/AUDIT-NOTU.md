# Eleme Tezgâhı Bağımsız Denetim Notu

**Tarih:** 4 Ağustos 2026
**Durum:** Eski çıkarımsal sonuçlar geri çekildi
**Karar kaydı:** `docs/adr/0007-eleme-istatistigi-v2-ve-kanit-geri-cekimi.md`

Bu klasördeki `PRE-REGISTRATION.md`, `eleme-sonuclari.json` ve
`eleme-sonuclari.md` tarihî kanıt zincirinin parçası olarak değiştirilmeden/silinmeden
korunur. Ancak eski p-değerleri, FDR kararları ve E/I/J/K/L sınıflandırmaları ürün kuralına
dönüştürülemez.

## Geri çekme nedenleri

- Her ufukta dört-bar null dağılımı kullanılması
- IID örnekleme ve örtüşen forward getiriler
- Sonuç görüldükten sonra tek yönlü test kuyruğu seçimi
- Funding/yüksek-vol/hafta sonu epizotlarında örneklem şişmesi
- 10 adet `n=0/NaN` testin 126 tamamlanmış teste dahil edilmesi
- Volatilite daralmasında yanlış test yönü
- DST ve sonraki-mum giriş modelinin uygulanmaması

## Kullanılabilecek kısım

Eski JSON'daki ham ortalamalar yalnız betimleyicidir. Hiçbir yönsel adayın rapordaki
17/20 bps maliyet eşiğini aşmaması yeni araştırma için uyarı sinyalidir; fakat evrensel ret,
istatistiksel anlamlılık veya rejim filtresi kabulü değildir.

## Yeniden analiz koşulu

`pulse-v2.0` kodu bağımsız incelendikten sonra temiz commit, temiz çalışma ağacı ve
doğrulanmış dataset manifestiyle yeni bir klasöre Development reanalysis üretilecektir.
Yeni çıktı bu tarihî dosyaların üzerine yazılmaz ve temiz OOS kullanılmaz.
