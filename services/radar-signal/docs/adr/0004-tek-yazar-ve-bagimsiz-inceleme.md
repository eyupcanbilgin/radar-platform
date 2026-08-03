# 0004 — Görev Başına Tek Yazar ve Bağımsız İnceleme İlkesi

* **Tarih:** 3 Ağustos 2026 (Revize: 4 Ağustos 2026)
* **Durum:** KABUL EDİLDİ
* **Karar Vericiler:** Eyüpcan, Claude Code, Antigravity

## Bağlam ve Problem
`CLAUDE.md` "Oturum akışı" Bölümü Kural 3'te *"Bu repo tek yazarlıdır (Claude Code)."* ifadesi mevcuttu. Ancak yapay zeka modelleriyle yürütülen geliştirmelerde doğrulama yanlılığı (confirmation bias) ve kendi ürettiği koda tarafsız bakamama riski bulunmaktadır.

## Karar
`CLAUDE.md` "Oturum akışı" Bölümü Kural 3 şu şekilde güncellenmiştir:
> **"Görev başına tek yazar; yazar ≠ incelemeci."**

Her geliştirme görevi tek bir yazar rolü tarafından yürütülür. Kod geliştirmesini yapan oturum veya model, kendi kodunun nihai kabul denetçisi olamaz. İnceleme; bağımsız bir AI oturumu, farklı bir model veya insan denetçi tarafından yürütülen inceleme ve kabul kapıları ile tamamlanır.

## Sonuçlar ve Ek Kabul Kapıları

1. **Feature Branch & Main Koruması:** Doğrudan `main` dalına commit atılması YASAKTIR. Tüm geliştirmeler `feature/<görev-adı>` dalında yürütülür (CLAUDE.md Değiştirilemez Kurallara eklendi).
2. **Kart ↔ Kod Uyum Denetimi:** İncelemeci, hipotez kartındaki metinsel kurallar ile koddaki matematiksel gösterim ve mantığın (örn. stop loss türü, rolling pencere türü, filtre varlığı) %100 örtüştüğünü denetlemek zorundadır.
3. **Registry Verdict Kaydı:** Deneme tamamlandıktan sonra koşu sonucu `registry/experiments.jsonl` üzerinde `verdict` (`accepted`, `rejected`, `invalid`) olarak güncellenmelidir.
4. **Temiz Çalışma Ağacı (Clean Working Tree) Zorunluluğu:** Locked Out-of-Sample (OOS) ve final backtest koşuları yalnızca git commit'i atılmış, temiz çalışma ağacında (`git_dirty: False`) çalıştırılabilir.
5. **Sermaye Tükenmesi (Underwater / Bankruptcy) Kontrolü:** Backtest süresince bakiye tükenmesi (sabit notional nedeniyle işlemlerin durması) gerçekleşirse koşu otomatik olarak `INVALID` kabul edilir ve terminal getiri olarak raporlanamaz.
