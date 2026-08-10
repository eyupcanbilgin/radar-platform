# ADR-0006 — Yönsel araştırmanın yeniden açılması ve ürün hedefinin geri alınması

- **Tarih:** 10 Ağustos 2026
- **Durum:** Kabul edildi
- **İlgili:** ADR-0004 (kapsamı daraltılır, geçersiz kılınmaz), Signal ADR-0014/0016–0020
- **Karar mercii:** Ürün sahibi (Eyüpcan)

## Bağlam

ADR-0004 (5 Ağustos 2026), S-0003 ve S-0004 yönsel ailelerinin Development düzeyinde
reddedilmesinin ardından ürün v1'in birincil çıktısını yön tahmininden **kırılganlık uyarısına**
daralttı ve Kuzey Yıldızı metnini buna göre değiştirdi.

10 Ağustos 2026'da ürün sahibi bu daralmanın kendi ürün hedefini karşılamadığını bildirdi:
ürün baştan beri **`LONG` gir / `WAIT` bekle / `SHORT` gir** kararı üretmek için başlatılmıştı.
İnceleme, ADR-0004'ün hedefi gerçekten değiştirdiğini doğruladı; daralma iki başarısız
ölçümün ardından yapılmıştı.

İki gözlem bu kararı gerekli kıldı:

1. **İki ret, ürün hedefini değiştirmek için küçük bir örneklemdir.** Registry'de bugüne kadar
   yalnız iki yönsel aile ölçülmüştür (S-0003, S-0004). Ciddi bir kantitatif araştırma programı
   onlarca aile eler; ikide durup ürünü yeniden tanımlamak erkendir.
2. **ADR-0004 yönü yasaklamamış, şarta bağlamıştı.** Aynı ADR'nin 4. maddesi açık bir
   yeniden-açma kapısı tanımlar. Bu ADR o kapıyı kullanır, ihlal etmez.

## Kararlar

### 1. Kuzey Yıldızı yönsel hedefe geri döner

Ürünün hedef çıktısı yeniden açıklanabilir `LONG`/`SHORT`/`WAIT` kararıdır. Kırılganlık,
volatilite riski, veri güveni ve blocker uyarısı **ürünün terk edilen yönü değil, ölçülmüş bir
yönsel kurulum oluşana kadarki dürüst ara çıktısı ve kalıcı risk katmanıdır**.

### 2. ADR-0004 geçersiz kılınmaz, kapsamı daraltılır

ADR-0004 tarihî bir karar kaydıdır ve yeniden yazılmaz. Bu ADR onun yalnız **1. ve 5.
maddelerinin ürün hedefi kapsamını** günceller. ADR-0004'ün şu maddeleri **aynen yürürlüktedir**:

- madde 2: ölçülmüş setup yokken runtime `direction=null`, `directional_decision_allowed=false`,
  `WAIT` kalır. `WAIT` nötr yön iddiası değildir;
- madde 3: `decision-context/v1` şeması değişmez;
- madde 4: yeniden-açma kapısının şartları;
- madde 6: yeni veri ailesi yalnız ablation ile marjinal katkı gösterirse eklenir;
- madde 7: gerçek emir, private API anahtarı, kişiselleştirilmiş tavsiye ve LLM'in canlı karar
  yetkisi kapsam dışıdır.

**Hedefin geri alınması, korumaların gevşetilmesi değildir.** Yön yalnız ölçüldüğünde açılır.

### 3. Tarihî retler korunur

S-0003 ve S-0004 reddedilmiş olarak kalır. Bu aileler yeni eşiklerle yeniden denenmez, sonuçları
yeniden yorumlanmaz, Registry satırları değiştirilmez. ADR-0004'ün "sonucu görülmüş aileyi yeni
hipotez gibi ön-kayıt etmek araştırma disiplinini ihlal eder" tespiti aynen geçerlidir.

### 4. Yeniden-açma kapısı S-0005 ile karşılanır

ADR-0004 madde 4'ün beş şartı, ön-kaydı bu ADR ile aynı dalda fakat **ayrı commit'te** yapılan
S-0005 (Coinbase premium / bölgesel spot talep) hipotezinde şöyle karşılanır:

| ADR-0004 §4 şartı | S-0005'te karşılığı |
|---|---|
| Sonuçları görülmemiş hipotez | Bu aile hiç ölçülmedi; hiçbir sonucu görülmedi |
| Mekanizması önceki ailelerden bağımsız | Bölgesel/kurumsal **spot talep dengesizliği**; S-0003 türev kaldıraç konumlanması, S-0004 fiyat momentumu + volatilite rejimi |
| Ölçümden önce ayrı commit'li ön-kayıt | Kart ayrı commit; ölçüm ayrı ve **sonraki** PR'da |
| Development protokolü | Purged walk-forward + embargo (Signal ADR-0014), locked OOS kapalı |
| İki maliyet senaryosu | `realistic` ve `taker_heavy` birlikte raporlanır |
| Bağımsız venue kanıtı | Hipotez zaten iki venue'yu (Coinbase spot + Binance spot) yapısal olarak kullanır |

### 5. S-0005 tam istatistik kapı setinden geçer

S-0004'ün geçtiği kapılara ek olarak, ADR-0019/0020 ile hazırlanan fakat henüz hiçbir hipoteze
uygulanmamış kapılar S-0005'te **ön-kayıtla** zorunlu kılınır: DSR, PBO/CSCV, ±%20 parametre
hassasiyeti ve dönem/venue kırılganlığı. Böylece Faz 2'nin bu üç açık kutusu ölçümle birlikte
kapanır ve "p<0.05 çıktı" sonucunun şansa mı gerçeğe mi denk geldiği ayırt edilebilir.

### 6. Kırılganlık kolu durmaz

F-0001 forward kanıt toplama ve kırılganlık kalibrasyonu **paralel devam eder**. 10 Ağustos'ta
MCP geçmiş backfill'iyle açılan 30 günlük `available` gözlem sayacı boşa gitmez. İki kol
birbirinin önkoşulu değildir.

### 7. Çok-deneme cezası büyür ve açıkça sayılır

S-0005, DSR çoklu-deneme evreninde **üçüncü** yönsel denemedir. Bu ADR'nin kendisi de bir seçim
olayıdır: aile, önceki iki ailenin başarısız olduğu **bilinerek** seçilmiştir. Bu seçim yanlılığı
S-0005 kartında beyan edilir ve deneme sayacına dahil edilir. Her yeni aile cezayı büyütür;
sınırsız deneme hakkı yoktur.

## Sonuçlar ve sınırlar

Ürün hedefi yönsel karara döner; korumalar dönmez — hepsi yürürlükte kalır. Bu ADR bir avantaj
(alpha) iddiası **değildir** ve S-0005'in kabul edileceğini **ima etmez**; önceki iki aile gibi
reddedilebilir. Yön, ancak S-0005 ön-kayıtlı kabul kriterlerinin tamamını geçerse açılır ve o
noktada bile Faz 3 forward karantinası (≥4 hafta **ve** ≥100 bağımsız karar **ve** 2 rejim)
gerekir.

Bu ADR yürürlüğe girdiği anda runtime davranışı **değişmez**: `direction` null, `WAIT` ve
`directional_decision_allowed=false` kalır.
