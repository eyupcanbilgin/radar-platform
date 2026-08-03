# Telegram Kurulumu — 5 Adım (token'ı SEN koyacaksın)

> **Kural:** Bot token'ı ve chat id repoya, config dosyasına veya sohbete **yazılmaz**.
> Yalnız `.env` dosyasına, kendi elinle. `.env` git dışıdır (`.gitignore`).

## 1. Botu oluştur

Telegram'da **@BotFather** ile konuş:

- `/newbot` yaz
- Bot adı sor: istediğin ad (ör. `Radar Signal`)
- Kullanıcı adı sor: `_bot` ile bitmeli (ör. `eyupcan_radar_signal_bot`)
- BotFather bir **token** verir: `1234567890:AAH...` biçiminde. Bu satırı kimseyle paylaşma.

## 2. Kendi chat id'ni öğren

- Oluşturduğun bota Telegram'dan **herhangi bir mesaj** gönder (ör. "merhaba"). Bu şart:
  bot, kendisine hiç yazmamış bir kullanıcıya mesaj gönderemez.
- Tarayıcıda şu adresi aç (`<TOKEN>` yerine kendi token'ın):
  `https://api.telegram.org/bot<TOKEN>/getUpdates`
- Dönen JSON'da `"chat":{"id":123456789,...}` kısmındaki sayı senin **chat id**'in.

## 3. `.env` dosyasını oluştur

Repo kökünde `.env` adında bir dosya aç ve iki satır yaz:

```
TELEGRAM_BOT_TOKEN=buraya_botfather_token
TELEGRAM_CHAT_ID=buraya_chat_id
```

`.env.example` dosyası şablon olarak repoda vardır; onu kopyalayıp doldurabilirsin.

## 4. Doğrula

```bash
.venv/Scripts/python scripts/telegram_check.py
```

Telegram'ına tek bir test mesajı düşerse kurulum tamamdır. Mesaj gelmezse script
nedenini söyler (token yanlış, chat id yanlış, ya da bota hiç yazılmamış).

## 5. Pompayı çalıştır

```bash
.venv/Scripts/python scripts/pump.py
```

Token tanımlı değilse sistem çökmez: bildirimler konsola yazılır ve uyarı verir.
Kuyruk kaybolmaz — token'ı sonradan tanımlayıp pompayı yeniden başlattığında
bekleyen bildirimler "[GEÇ TESLİM]" notuyla iletilir.

## Sık sorulanlar

**Token'ı yanlışlıkla paylaşırsam?** BotFather'da `/revoke` ile iptal et, yeni token al,
`.env`'i güncelle.

**Bot benim adıma işlem yapabilir mi?** Hayır. Bu bot yalnız mesaj gönderir; borsa
bağlantısı yoktur ve bu projede hiçbir yerde trade yetkili anahtar kullanılmaz
(CLAUDE.md kural 1).
