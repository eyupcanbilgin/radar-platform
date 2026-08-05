# ADR-0019 — Faz 2 İstatistik Kapıları: DSR, PBO/CSCV, Hassasiyet ve Ablation

- **Tarih:** 5 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** CR-001 CR-1/CR-3, CR-002 P0-2/P1-4, ADR-0014, ADR-0016,
  `SINYAL-SPEC.md`, Hedefe Geliştirme Planı Faz 2

## Bağlam

Purged walk-forward, embargo ve baseline ölçümü hazır olsa da üçüncü bir hipotezi denemeden
önce çoklu-deneme şansını ve seçim kaynaklı aşırı uyumu ayıracak kapılar eksikti. Mevcut
`dsr.py` matematik çekirdeği aile bazında eski Registry koşularını sayıyordu; yeni Faz 2
kanıt evrenini, duplicate geçersizleştirmelerini veya PBO/hassasiyet/ablation'ı uçtan uca
zorlamıyordu.

## Karar

1. `config/research_protocol.yaml` içindeki `statistical_gates/version: 1.0`; DSR güven
   seviyesi, PBO partition/bütçe/ret eşiği, hassasiyet deltası/koruma oranı, ablation katkı
   eşikleri ve zorunlu `realistic+taker_heavy` senaryolarının tek otoritesidir.
2. Global Faz 2 DSR deneme evreni, yapılandırılmış `result` gövdesi taşıyan, başarılı koşmuş,
   effective verdict'i `invalid` olmayan benzersiz
   `(hypothesis_id, strategy_version, dataset_snapshot)` kanıtlarıdır. Duplicate rerun ve
   eski protokol satırları sayılmaz. Getiri matrisi bu Registry evreniyle tam eşleşmelidir.
3. DSR, gözlenen serinin Sharpe/skew/kurtosis değerlerini ve denemeler arası Sharpe
   varyansını kullanır. Eksik/sabit/sonlu olmayan seri anlamlılık üretmez; fail-loud durur.
4. PBO/CSCV zaman sıralı getirileri config'deki çift sayıda eşit boyutlu contiguous
   partition'a böler ve `mean_net_return` performans ölçütünü kullanır;
   her yarı-kombinasyonda in-sample kazananın out-of-sample göreli rank logit'ini ölçer.
   `lambda <= 0` oranı PBO'dur. Kombinasyon sayısı bütçeyi aşarsa rastgele alt örnekleme
   yapılmaz.
5. Hassasiyet planı her ön-kayıtlı pozitif sayısal parametreyi tek-parametre-at-a-time
   config deltasıyla aşağı/yukarı oynatır. Bütün varyantlar ve iki maliyet senaryosu eksiksiz
   olmadan rapor üretmez; base performans pozitif değilse “dayanıklı” denemez.
6. Ablation tam model ile “bir veri ailesi çıkarılmış” modeli aynı fold sırası ve maliyet
   senaryosunda eşleştirir. Ortalama marjinal katkı ve pozitif fold oranı config kapılarını
   birlikte geçmelidir. Eksik/eşleşmeyen fold nötr/sıfır sayılmaz.
7. `scripts/statistical_gates_cli.py` yalnız Development kapsamlı hazırlanmış JSON bundle
   okur ve deterministik stdout raporu üretir. Locked OOS'a erişmez, Registry'ye veya kanıt
   dosyalarına yazmaz.
8. S-0003 ve S-0004 reddedildikten sonra bu kapılarla geriye dönük yeniden yorumlanmaz.
   ADR-0019 sonraki ön-kayıtlı hipotezlerden itibaren zorunludur.

## Sonuçlar

Yeni bir `p<0.05` bulgusu tek başına kabul gerekçesi olamaz; çoklu-deneme, seçim aşırı uyumu,
parametre kırılganlığı ve veri ailesinin marjinal katkısı aynı protokolde görünür. Bu paket
yeni hipotez, Registry deneyi, gerçek veri sonucu, yön veya emir üretmez. Test girdileri
tamamen sentetiktir ve mevcut iki tarihî reddi değiştirmez.
