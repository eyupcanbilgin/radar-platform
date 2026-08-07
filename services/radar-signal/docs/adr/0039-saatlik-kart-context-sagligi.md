# ADR-0039 — Saatlik Kartta Context Sağlığını Açık Gösterme

- **Tarih:** 7 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0011, ADR-0032, ADR-0038

## Bağlam

İlk sürekli macOS runtime saatinde karar ve forward gözlem başarıyla yazıldı. Context
`unavailable` ve karar altı context blocker'ı taşırken teslim edilen kart yalnız teknik
feature snapshot'a baktığı için `Veri sağlığı: hazır · eksikler: yok` diyordu. Blocker'lar
ayrı satırda görünse de bu ifade operatöre çelişkili sağlık bilgisi veriyordu.

## Karar

1. Saatlik mesaj formatter'ı ledger'daki immutable feature ve context payload'larını birlikte
   doğrular. Feature sağlığı ile context `healthy|degraded|unavailable|eksik` durumu ayrı
   etiketler olarak gösterilir.
2. Context yoksa `eksik`, unavailable ise aynen `unavailable` yazılır; feature hazır olması
   genel context sağlığına dönüştürülemez. Karar blocker'ları ayrıca tam listelenmeye devam eder.
3. Geçmiş SENT outbox satırları değiştirilmez veya yeniden kuyruğa alınmaz. İdempotent
   teslimat ve append-only karar geçmişi korunur; düzeltme sonraki kartlardan itibaren geçerlidir.
4. WAIT/direction-null, outcome, forward gözlem, Registry ve emir davranışı değişmez.

## Sonuç

Operatör teknik mum feature'larının hazır olmasıyla karar context'inin kullanılabilirliğini
karıştırmaz. Eksik/yetersiz veri kartta nötr veya hazır görünmez.
