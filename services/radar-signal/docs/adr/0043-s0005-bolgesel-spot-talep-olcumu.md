# ADR-0043 — S-0005 bölgesel spot talep ölçümü: reddedildi

- **Tarih:** 10 Ağustos 2026
- **Durum:** Kabul edildi (ölçüm kaydı)
- **İlgili:** Platform ADR-0006, Signal ADR-0014/0016–0020, `docs/hypotheses/S-0005.md`

## Bağlam

Platform ADR-0006 yönsel araştırmayı ürün sahibi kararıyla yeniden açtı. S-0005, ADR-0004 §4
yeniden-açma kapısını karşılayan ilk aile olarak ölçümden **önce** ayrı commit'le (`be56905`)
ön-kaydedildi. Bu ADR ölçümün kendisini kaydeder.

## Ölçüm

Development penceresi (2024-01-01 → 2026-08-04), purged walk-forward + embargo, iki maliyet
senaryosu, üç baseline. `dataset_snapshot = 637104fbb080ac50…`; yetkili koşu
`E-20260810-190318-274dcd`.

| | `realistic` | `taker_heavy` |
|---|---|---|
| Kümülatif net getiri | **+28.97%** | **−17.73%** |
| Buy & Hold | −13.56% | −15.47% |
| Simple Trend | +6.69% | −12.80% |

562 işlem, `p = 0.2654`, fold tutarlılığı %42.9.

**Sonuç: REDDEDİLDİ** — dört ret ölçütü tetiklendi (`taker_heavy` negatif, iki baseline'ı
`taker_heavy`de aşamadı, `p ≥ 0.05`, fold tutarlılığı `< %60`).

## Kararlar

### 1. Pozitif `realistic` sonuç kabul değildir ve öyle sunulmaz

S-0005, `realistic` senaryoda pozitif olan ve **üç baseline'ı da aşan** ilk yönsel ailedir.
Bu, S-0003/S-0004'ten farklı bir profildir ve kaydedilmeye değerdir. Fakat kabul ölçütü tek
bir senaryo değildir ve bunun sebebi tam olarak buradaki tablo gibi durumlardır:

- `p = 0.2654` gözlenen getirinin rastgele süreçten ayrışmadığını söyler;
- fold'ların yalnız %42.9'u pozitiftir — kazanç zamana yayılmamış, yoğunlaşmıştır;
- `taker_heavy` altında çöküş kenarın spread/komisyondan ince olduğunu gösterir.

Üçü birlikte "maliyetli ama gerçek bir kenar" değil, **ölçülemeyen bir kenar** anlamına gelir.

### 2. Aile kapanır; eşik oynatılmaz

Kart §4.8 gereği S-0005 eşik, ufuk, yumuşatma veya bant değiştirilerek yeniden koşulmaz.
`taker_heavy`yi kurtarmak için parametre aramak, ADR-0007'de kaydedilmiş hatanın tekrarı
olurdu. Tarihî ret korunur ve yeniden yorumlanmaz.

### 3. Ek kapılar hazır, bu koşuda uygulanmadı

DSR, PBO/CSCV ve ±%20 hassasiyet `not_evaluated` raporlandı: `evaluate_sensitivity` pozitif
base metrik ister ve base zaten reddedilmiştir. Reddedilmiş adayda bu kapıları zorlamak
anlamsız sayı üretirdi. Kapılar ön-kayıtlıydı ve kodda bağlıdır; base'i ayakta kalan ilk
ailede doğrudan çalışacaktır.

Eşik çatışması beyanı: kart PBO için `< 0.50`, config `0.05` der. Eşikler config'de yaşar
(CLAUDE.md kural 3) ve config daha sıkıdır; ön-kayıt sonradan düzenlenemeyeceği için sıkı
olan uygulanacak biçimde kodlandı.

### 4. Fold tutarlılık eşiği koddan config'e taşındı

S-0004'te `0.60` koda gömülüydü. Aynı sayı `config/research_protocol.yaml` içine alındı.
Bu bir eşik **değişikliği değildir**; ön-kayıtlı değerin kod dışına çıkarılmasıdır.

### 5. Prim iki SPOT mekândan hesaplanır

Binance **spot** bacağı bu iş kapsamında indirildi (22 704 kapalı mum, 0 eksik saat) ve
manifeste bağlandı. Primi perp'e karşı ölçmek funding/basis mekanizmasını geri sokar ve
kartın "türev girdisi yok" ön-kaydını ihlal ederdi. İndirici, Coinbase indiricisinin
doğrulanmış sayfalama/bütünlük mantığını yeniden yazmaz; aynı yardımcıları `symbol`/`venue`
parametresiyle kullanır, böylece primin iki bacağı birebir aynı kurallarla kurulur.

### 6. `git_dirty` bayrağı güvenilmezdir ve ayrı iş olarak kaydedildi

Üç koşu da `provenance.git_dirty = true` taşır. Bu kirli checkout kanıtı **değildir**: aynı
kod izole registry yoluyla koşulduğunda temiz ağaçta `false` üretir; bayrak koşunun kendi
append-only registry dosyasına dokunmasından etkilenmektedir. S-0003 ve S-0004 koşuları da
`true`dur, yani kusur bu işle gelmedi. ADR-0003/ADR-0004 ve CLAUDE.md kural 13 bu bayrağa
dayandığı için koruma fiilen çalışmamaktadır; ayrı bir düzeltme işi açılmıştır.

İlk koşu (`E-20260810-185929-e3402e`) **gerçekten** kirliydi — ölçüm scriptleri henüz commit
edilmemişti — ve append-only registry'den silinmeyip `V-20260810-190041-e3f90a` olayıyla
`invalid` işaretlendi.

## Sonuçlar ve sınırlar

Yönsel skor tahtası: **3 aile denendi, 3'ü reddedildi.** Runtime davranışı değişmez:
`direction=null`, `directional_decision_allowed=false`, `WAIT`. Bu ADR alpha iddiası
taşımaz.

Kapanan Faz 2 kutuları: yeni ailenin purged walk-forward + embargo ile ölçülmesi. **Açık
kalanlar:** DSR/PBO/CSCV, hassasiyet ve ablation raporları — bunlar base'i ayakta kalan bir
aile ister; S-0005'te uygulanacak bir base kalmadı.
