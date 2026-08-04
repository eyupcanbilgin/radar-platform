# 0007 — Eleme İstatistiği v2 ve Eski Çıkarımların Geri Çekilmesi

* **Tarih:** 4 Ağustos 2026
* **Durum:** KABUL EDİLDİ
* **Kapsam:** `scripts/signal_pulse.py`, 126-test eleme raporu ve S-0002b kanıt durumu

## Bağlam

`feature/eleme-tezgahi` dalındaki bağımsız kod denetimi, 4 Ağustos tarihli eleme
raporunun çıkarımsal sonuçlarını etkileyen yöntem kusurları buldu:

1. +1/+2/+8/+16 bar testlerinde null dağılımı daima `fwd_4` üzerinden kuruluyordu.
2. IID yeniden örnekleme, örtüşen getirileri ve ardışık olay mumlarını bağımsız sayıyordu.
3. Yönsel test kuyruğu sonuç görüldükten sonra ortalamanın işaretine göre seçiliyordu.
4. Funding ve yüksek-vol rejimleri tek epizot olduğu hâlde her 15m mum yeni olay sayılıyordu.
5. Hafta sonu testi her hafta sonu mumunu ayrı olay kabul ediyordu.
6. Bir-bar volatilitesi örnek standart sapmayla tanımsız kalıyor, 10 test NaN üretiyordu.
7. Seans saatleri DST-aware değildi ve giriş karar mumunun kapanışında anlık kabul ediliyordu.

Ayrıca S-0002b kodunda `trade.stop_loss` mutlak fiyatı ile `self.stoploss` oranı
karşılaştırıldığı için 1 ATR stop callback'i etkinleşmiyordu. Funding kolonu bulunmadığında
filtre fail-open biçimde bütün satırları geçiriyordu. Bu nedenle S-0002b koşuları Kart A'nın
tam ve geçerli backtest'i değildir.

## Karar

1. `eleme-sonuclari.md/json` tarihî artefakt olarak korunur, fakat **çıkarımsal kanıt olarak
   geri çekilir**. Ham ortalamalar yalnız betimleyici kabul edilir.
2. Eski rapordaki E/I/J/K/L “kanıtlanmış filtre/risk adayı” kararları uygulanmaz.
3. S-0002b'nin üç `rejected` koşusu kanıt bakımından `INVALID` kabul edilir. Eski
   `experiments.jsonl` satırları değiştirilmez; etkin kararlar append-only
   `registry/verdict_events.jsonl` kayıtlarıyla düzeltilir.
4. `pulse-v2.0` yöntemi aşağıdaki zorunlu davranışlarla uygulanır:
   - ufukla eşleşen null dağılımı;
   - circular moving-block bootstrap;
   - örtüşmeyen efektif olay seçimi;
   - önceden belirlenmiş `greater/less/two-sided` alternatifi;
   - yalnız geçerli p-değerleri içeren BH evreni;
   - epizot başlangıcıyla funding/hafta sonu/yüksek-vol tekilleştirme;
   - DST-aware seanslar;
   - kapanmış karar mumundan sonraki mum açılışında referans giriş;
   - bir-bar ufkunda tanımlı RMS realized volatility.
5. v2 sonucu dirty çalışma ağacında “final” olamaz. Önce temiz signal commit'i bağımsız
   incelenir; onay kaydı incelenen 12 karakterli SHA'ya bağlanıp ayrı commit'lenir. Yalnız
   temiz repo, doğrulanmış veri manifesti ve geçerli onay kaydıyla Development reanalysis
   üretilir. Locked OOS penceresine dokunulmaz.

## Sonuç

Kart A'ya parametre ayarıyla devam edilmeme kararı korunur; gerekçe artık hatalı p-değerleri
değil, bu dönemde gözlenen düşük/negatif ekonomik büyüklük ve geçerli uygulama eksikliğidir.
Kart A'nın veya E/I/J/K/L filtrelerinin istatistiksel durumu v2 temiz koşu ve daha sonra
forward doğrulama olmadan “kanıtlandı” diye raporlanamaz.
