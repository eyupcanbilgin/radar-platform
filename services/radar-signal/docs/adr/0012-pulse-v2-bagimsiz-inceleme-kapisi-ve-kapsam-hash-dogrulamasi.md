# 0012 — Pulse-v2 Bağımsız İnceleme Kapısı ve Kapsam Hash Doğrulaması

* **Tarih:** 5 Ağustos 2026
* **Durum:** KABUL EDİLDİ
* **Kapsam:** `scripts/run_pulse_reanalysis.py`, `tests/test_run_pulse_reanalysis.py` ve `SINYAL-SPEC.md`

## Bağlam

ADR-0007 ile tanımlanan `pulse-v2.0` araştırma kapısı, resmî Development yeniden analizi yapılmadan önce kodun bağımsız bir oturum/kişi tarafından incelenmesini ve onay kaydının (`pulse-v2-review.json`) repository'ye eklenmesini zorunlu kılıyordu.

Ancak v1 şeması `reviewed_commit == current_commit` (HEAD) şartı arıyordu. Bu durum bir **bootstrap paradoksu** oluşturuyordu:
1. İncelemeci araştırma kodunu inceleyip $C_1$ commit'i için onay belgesi oluşturur (`reviewed_commit: C1`).
2. Onay belgesi repository'ye eklenip commit edildiğinde HEAD $C_2$'ye ilerler.
3. $C_2$'de `run_pulse_reanalysis.py` çalıştırıldığında $C_1 \neq C_2$ olduğu için kapı reddeder.
4. Onay belgesi untracked bırakılırsa `repository_is_dirty()` kapısı reddeder.

Böylece temiz çalışma ağacı, commit edilmiş onay belgesi ve tam HEAD eşitliği aynı anda sağlanamıyordu.

## Karar

1. **Schema v2 Geçişi:** `pulse-v2-review.json` formatı `"schema_version": "2"` sürümüne yükseltildi. v1 şeması güvenli biçimde reddedilir.
2. **Git Atası Doğrulaması (Git Ancestor Check):** `reviewed_commit` değerinin tam HEAD ile birebir aynı olması şartı yerine, `reviewed_commit`'in mevcut commit'in git geçmişinde atası (`git merge-base --is-ancestor <reviewed_commit> <current_commit>`) olduğu doğrulanır.
3. **Kapsam ve SHA-256 Hash Doğrulaması (`reviewed_files`):** Onay kaydı `review_scope` (incelenen dosya yolları listesi) ve `reviewed_files` (`{dosya_yolu: sha256_hash}` eşleşmesi) nesnelerini taşır.
4. **Çalışma Zamanı Bütünlük Kontrolü:** `run_pulse_reanalysis.py` çalıştığında kapsama giren her bir dosyanın disktedki SHA-256 hash'ini hesaplar. İncelenen dosyalardan herhangi biri silinmiş, değiştirilmiş veya eksikse onay kaydı derhal geçersiz sayılır.
5. **Çalışma Ağacı ve OOS Koruması:** `repository_is_dirty()` ve `LOCKED_OOS_START` (`2026-08-04`) kuralları aynen korunur. Kirli ağaçta resmî koşu yapılamaz. `--allow-dirty-smoke` seçeneği yalnız `services/radar-signal/var/` dizini altında deneysel çalışabilir ve resmî kanıt üretmez.

## Sonuç

Onay belgesinin bağımsız inceleme sonrası ayrı bir commit olarak repository'ye eklenmesi kapıyı kilitlemez. İnceleme tamamlandıktan sonra yeni commit atılsa bile incelenmiş araştırma dosyaları değişmediği sürece onay geçerliliğini korur; ancak araştırma kodunda tek bir karakter bile değişirse kapı otomatik olarak kapanır ve yeni bağımsız inceleme gerektirir.
