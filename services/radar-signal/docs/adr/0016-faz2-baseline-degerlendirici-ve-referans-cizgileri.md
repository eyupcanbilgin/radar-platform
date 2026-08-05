# 0016 — Faz 2 Referans Taban Çizgileri (Baselines) Değerlendiricisi

- **Tarih:** 5 Ağustos 2026
- **Durum:** KABUL EDİLDİ
- **İlgili:** Hedefe Geliştirme Planı Faz 2, `SINYAL-SPEC.md`, ADR-0010, ADR-0014

## Bağlam

Faz 2 yönsel araştırma ve kabul kapısının temel gereksinimi: geliştirilecek hipotez ailelerinin
"gerçek bir yönsel avantaj (alpha) sunup sunmadığını" ölçecek referans taban çizgilerinin (baselines)
varlığıdır. Kontrol ve taban çizgilerini aşamayan aday stratejiler tartışılamaz.

Bu referans çizgilerinin maliyetsiz olmaması (signal `CLAUDE.md` Kural 6), koda sabit sayı
gömülmeden konfigürasyondan beslenmesi, locked OOS engelini koruması ve eksik/bozuk verilerde
hayalî sıfır getiri uydurmaması gerekmektedir.

## Karar

1. **Üç Bağımsız Referans Taban Çizgisi:**
   - **`cash` (Nakit / İşlem Yok):** Sıfır pozisyon. Net getiri $= 0.0$. Piyasa hareketi açık
     `opportunity_return` $= (P_{end} - P_{ref}) / P_{ref}$ gözlemi olarak kaydedilir.
   - **`buy_and_hold` (Al ve Tut):** Test penceresi başında ($P_{ref}$) alınıp sonunda ($P_{end}$)
     satılır. Giriş ve çıkış komisyonları + kayma `config/costs.yaml` dosyasından düşülür.
   - **`simple_trend` (Basit Trend Kontrolü):** `config/research_protocol.yaml` içindeki `fast_period`
     (20) ve `slow_period` (50) parametreleriyle çalışan basit hareketli ortalama kesişimi (MA crossover)
     tabanıdır. Her pozisyon değişiminde `costslib.effective_fee` maliyeti düşülür.

2. **Maliyet Sonrası Hesaplama İlkesi (Pazarlıksız):**
   Tüm taban çizgileri `config/costs.yaml` senaryoları (`realistic`, `taker_heavy` vb.) kullanılarak
   komisyon ve kayma düşülmüş **maliyet sonrası net getiri** olarak hesaplanır. Maliyetsiz sonuç
   raporlanmaz.

3. **Veri Eksikliği ve Kalite Semantiği:**
   Veri bulunmaması, boş pencere veya mum açığı durumunda sıfır veya nötr getiri atanmaz.
   İlgili fold durumu açıkça `unavailable` veya `invalid` olarak işaretlenir ve metrikler `None` döner.

4. **Locked OOS Koruması Mirası:**
   ADR-0014 davranışını miras alarak; Locked OOS (`2026-08-04T00:00:00Z`) tarihini kapsayan veya aşan
   fold değerlendirmeleri varsayılan olarak `LockedOOSAccessError` fırlatır.

5. **Determinizm ve Tekrarlanabilirlik:**
   Aynı fold planı ve mum verisi kullanıldığında çıktı %100 deterministiktir ve 100 kez tekrarlandığında
   bit-bit özdeş JSON çıktısı verir.

6. **Alpha İddiası Taşımama:**
   Bu hesaplayıcı yeni strateji, yön veya emir üretmez; yalnızca gelecek hipotezlerin kıyaslanacağı
   referans çizgisini sunar.

## Sonuçlar

Gelecekte yazılacak tüm yönsel hipotez ailelerinin maliyet sonrası net getirileri bu üç referans taban
çizgisi (`cash`, `buy_and_hold`, `simple_trend`) ile pencere bazında dürüstçe karşılaştırılabilecektir.
