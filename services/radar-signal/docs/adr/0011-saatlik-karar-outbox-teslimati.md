# ADR-0011 — Saatlik DecisionCard Teslimatı ve Sınırlı Outbox Uzlaştırması

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** Signal ADR-0008, ADR-0009, ADR-0010, `SINYAL-SPEC.md`

## Bağlam

Saatlik runtime, değişmez `DecisionCardV1` kartlarını ledger'a yazıyor; ancak bu kartlar
insan-okur bildirime ve mevcut güvenilir outbox pompasına bağlanmıyordu. Telegram'a runtime
içinden doğrudan gönderim yapılması kesintide kayıp ve tekrar çalıştırmada çift teslim riski
doğurur. Ledger ve outbox ayrı SQLite dosyalarında olduğundan iki yazım arasında atomik bir
transaction da kurulamaz.

## Karar

1. Saatlik kart mesajı yalnız doğrulanmış, değişmez ledger feature/decision payload'larından
   deterministik üretilir. Geçici ağ veya runtime durumları mesaj gövdesine katılmaz.
2. Mesaj ortak outbox'a `(decision_id, "hourly_decision")` idempotency anahtarıyla eklenir.
   Aynı gövdeli tekrar `False` döner; aynı anahtarın farklı gövdeyle kullanımı fail-loud
   `ValueError` üretir.
3. Canlı tek-sefer ve daemon runtime, karar `created` veya `already_recorded` olsa da ledger
   yazımından sonra enqueue dener. Böylece ledger commit'inden sonraki süreç çökmesi aynı saat
   yeniden işlendiğinde onarılır.
4. Operasyonel onarım için `scripts/reconcile_hourly_delivery.py` yalnız açık `--limit` ile
   en yeni kararları tarar. Doğrulanmamış veya sınırsız geçmiş taraması yapılmaz.
5. Teslimat mevcut `scripts/pump.py` sürecine bırakılır. Telegram kesintisinde satır PENDING
   kalır, backoff ile tekrar denenir ve SENT satırı yeniden gönderilmez.
6. Açık `--as-of` replay outbox'a yazmaz; tarihsel bildirim selini önlemek için `--outbox` ile
   birlikte reddedilir.
7. Mesaj `WAIT`i birinci sınıf sonuç olarak gösterir ve bunun yön/nötr getiri ölçümü olmadığını
   açıkça söyler. Katman yön üretmez, gerçek emir göndermez ve blocker'ı skora dönüştürmez.

## Sonuçlar

Saatlik paper karar zinciri ledger'dan insan-okur bildirime kayıpsız ve idempotent biçimde
bağlanmıştır. İki veritabanı arasındaki crash boşluğu atomik transaction yerine deterministik
tekrar ve sınırlı uzlaştırmayla kapatılır. Ayrı outbox pompası sayesinde Telegram arızası karar
üretimini durdurmaz veya mesajı kaybettirmez.
