"""SPEC §2'deki ⚠️ işaretli endpoint'lerin canlı doğrulaması (Faz 0; `make smoke` temeli).

Yalnızca public, salt-okunur GET istekleri atar; hiçbir borsa hesabına bağlanmaz.

Kullanım:
    uv run python scripts/verify_endpoints.py
    uv run python scripts/verify_endpoints.py --skip-bitcoin-data
    uv run python scripts/verify_endpoints.py --json-out sonuc.json
    uv run python scripts/verify_endpoints.py --fail-on-blocked
    make smoke-evidence   # engellenmemiş ağdan: doğrula + kanıt kütüğüne ekle

bitcoin-data.com bütçesi: script başına en fazla 5 istek (API limiti 8/saat, 15/gün —
CLAUDE.md kural 8). Önce OpenAPI dokümanı üzerinden metrik adları keşfedilir; veri
endpoint'lerine en fazla 3 çağrı yapılır.

Çıkış kodları: 0 = zorunlu sözleşme kırılması yok; 1 = en az bir zorunlu kontrol düştü;
2 = yalnızca ortam engeli var ve `--fail-on-blocked` verildi (bkz. ADR-0009).
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

TIMEOUT = 20.0
HEADERS = {"User-Agent": "btc-radar-verify/0.1 (Faz 0 smoke; read-only)"}

# ── Ortam engeli (coğrafi kısıt) sözleşme ihlali DEĞİLDİR.
# Bir uç, sözleşmesi değiştiği için değil, isteğin geldiği ülke yüzünden de reddedilebilir.
# GitHub-hosted runner bölgeleri Binance/CloudFront tarafında engellidir (koşu 30894903581).
# İki durum aynı kovaya konursa günlük smoke kalıcı kırmızıya döner ve gerçek bir sözleşme
# kırılması bu gürültünün içinde kaybolur.
# Ayrıntı: docs/adr/0009-cografi-engel-siniflandirmasi.md
GEO_BLOCK_STATUSES = frozenset({403, 451})
GEO_BLOCK_MARKERS = (
    # CloudFront'un ülke engeli sayfası (HTML gövde)
    "cloudfront distribution is configured to block access from your country",
    # Binance'in kendi kısıtlı-bölge yanıtı (HTTP 451, JSON gövde)
    "service unavailable from a restricted location",
)


def geo_block_reason(status_code: int, body: str) -> str | None:
    """Ortam engelini sözleşme ihlalinden ayırır; engel değilse None.

    Hem statü hem gövde işareti eşleşmelidir. Tek başına 403, kaldırılmış bir uç veya
    değişmiş bir imza da olabilir — onları "engellendi" diye yutmak, tam olarak
    kaçırmak istemediğimiz sözleşme kırılmasını gizler.
    """
    if status_code not in GEO_BLOCK_STATUSES:
        return None
    lowered = body.lower()
    for marker in GEO_BLOCK_MARKERS:
        if marker in lowered:
            return f"HTTP {status_code}, gövde işareti: '{marker}'"
    return None


@dataclass
class Check:
    check_id: str
    layer: str
    spec_ref: str  # SPEC.md satır/bölüm referansı
    url: str
    params: dict[str, str] | None = None
    validate: Callable[[Any], str | None] | None = None  # None → OK, str → sorun açıklaması
    expect_failure: bool = False  # kaldırıldığı DOĞRULANAN endpoint'ler için tersine kontrol
    html_ok: bool = False  # JSON değil, HTML sayfa erişilebilirliği yeterli
    required: bool = True  # False: bilgilendirme amaçlı (ör. FX adayları tek tek)
    notes: str = ""


@dataclass
class Result:
    check_id: str
    layer: str
    spec_ref: str
    url: str
    ok: bool
    required: bool
    blocked: bool = False  # ortam engeli: sözleşme ne doğrulandı ne de ihlal edildi
    status: int | None = None
    latency_ms: int | None = None
    detail: str = ""
    sample: Any = field(default=None)

    @property
    def state(self) -> str:
        """Üç değil dört durum: ok / fail (zorunlu) / warn (bilgilendirici) / blocked."""
        if self.blocked:
            return "blocked"
        if self.ok:
            return "ok"
        return "fail" if self.required else "warn"


STATE_MARKS = {"ok": "OK", "fail": "FAIL", "warn": "warn", "blocked": "BLOCKED"}


def _need(data: Any, *keys: str) -> str | None:
    """Düz sözlükte anahtar varlığı kontrolü."""
    if not isinstance(data, dict):
        return f"dict bekleniyordu, {type(data).__name__} geldi"
    missing = [k for k in keys if k not in data]
    return f"eksik alan(lar): {missing}" if missing else None


def _need_list_item(data: Any, *keys: str) -> str | None:
    """Boş olmayan liste + ilk elemanda anahtar varlığı kontrolü."""
    if not isinstance(data, list) or not data:
        return f"boş olmayan liste bekleniyordu, {type(data).__name__} geldi"
    return _need(data[0], *keys)


def _klines_ok(data: Any) -> str | None:
    """Kline satırı dict değil: [openTime, o, h, l, c, v, closeTime, ...] sabit-pozisyonlu liste."""
    if not isinstance(data, list) or not data:
        return f"boş olmayan liste bekleniyordu, {type(data).__name__} geldi"
    row = data[0]
    if not isinstance(row, list) or len(row) < 7:
        return f"kline satırı en az 7 alanlı liste olmalı: {row!r}"
    return None


def _bybit_ok(data: Any) -> str | None:
    if not isinstance(data, dict) or data.get("retCode") != 0:
        return f"retCode != 0: {str(data)[:200]}"
    lst = (data.get("result") or {}).get("list")
    if not lst:
        return "result.list boş"
    return None


def _fx_krw(path: list[str]):
    def check(data: Any) -> str | None:
        cur = data
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return f"'{'.'.join(path)}' bulunamadı"
            cur = cur[p]
        try:
            rate = float(cur)
        except (TypeError, ValueError):
            return f"KRW kuru sayı değil: {cur!r}"
        return None if rate > 100 else f"KRW kuru şüpheli: {rate}"

    return check


def _cbbi_ok(data: Any) -> str | None:
    if not isinstance(data, dict) or not data:
        return "boş yanıt"
    if "Confidence" not in data:
        return f"'Confidence' anahtarı yok; mevcut anahtarlar: {sorted(data)[:15]}"
    series = data["Confidence"]
    if not isinstance(series, dict) or not series:
        return "Confidence serisi boş"
    return None


def _fng_ok(data: Any) -> str | None:
    if err := _need(data, "data"):
        return err
    return _need_list_item(data["data"], "value", "value_classification", "timestamp")


def _cg_global_ok(data: Any) -> str | None:
    if err := _need(data, "data"):
        return err
    d = data["data"]
    if err := _need(d, "market_cap_percentage", "total_market_cap"):
        return err
    if "btc" not in d["market_cap_percentage"]:
        return "market_cap_percentage.btc yok"
    return None


CHECKS: list[Check] = [
    # ── §2.1 Türevler (SPEC satır 41-48; tablo başlığı gereği TÜM satırlar canlı doğrulanır)
    Check(
        "binance_oi",
        "derivatives",
        "SPEC:43",
        "https://fapi.binance.com/fapi/v1/openInterest",
        {"symbol": "BTCUSDT"},
        lambda d: _need(d, "openInterest", "symbol", "time"),
    ),
    Check(
        "binance_oi_hist",
        "derivatives",
        "SPEC:43",
        "https://fapi.binance.com/futures/data/openInterestHist",
        {"symbol": "BTCUSDT", "period": "1h", "limit": "2"},
        lambda d: _need_list_item(d, "sumOpenInterest", "sumOpenInterestValue", "timestamp"),
    ),
    Check(
        "binance_premium_index",
        "derivatives",
        "SPEC:44",
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        {"symbol": "BTCUSDT"},
        lambda d: _need(d, "markPrice", "lastFundingRate", "nextFundingTime"),
    ),
    Check(
        "binance_funding_hist",
        "derivatives",
        "SPEC:44",
        "https://fapi.binance.com/fapi/v1/fundingRate",
        {"symbol": "BTCUSDT", "limit": "2"},
        lambda d: _need_list_item(d, "fundingRate", "fundingTime"),
    ),
    Check(
        "binance_global_ls_ratio",
        "derivatives",
        "SPEC:45",
        "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
        {"symbol": "BTCUSDT", "period": "1h", "limit": "2"},
        lambda d: _need_list_item(d, "longShortRatio", "longAccount", "shortAccount"),
    ),
    Check(
        "binance_top_ls_position",
        "derivatives",
        "SPEC:45",
        "https://fapi.binance.com/futures/data/topLongShortPositionRatio",
        {"symbol": "BTCUSDT", "period": "1h", "limit": "2"},
        lambda d: _need_list_item(d, "longShortRatio"),
    ),
    Check(
        "binance_taker_ratio",
        "derivatives",
        "SPEC:46",
        "https://fapi.binance.com/futures/data/takerlongshortRatio",
        {"symbol": "BTCUSDT", "period": "1h", "limit": "2"},
        lambda d: _need_list_item(d, "buySellRatio", "buyVol", "sellVol"),
    ),
    Check(
        "binance_forceorders_removed",
        "derivatives",
        "SPEC:47",
        "https://fapi.binance.com/fapi/v1/allForceOrders",
        {"symbol": "BTCUSDT", "limit": "5"},
        expect_failure=True,
        notes="SPEC varsayımı: REST likidasyon endpoint'i kaldırıldı; hata dönmesi BEKLENİR.",
    ),
    Check(
        "bybit_oi",
        "derivatives",
        "SPEC:48",
        "https://api.bybit.com/v5/market/open-interest",
        {"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1h", "limit": "2"},
        _bybit_ok,
    ),
    Check(
        "bybit_funding_hist",
        "derivatives",
        "SPEC:48",
        "https://api.bybit.com/v5/market/funding/history",
        {"category": "linear", "symbol": "BTCUSDT", "limit": "2"},
        _bybit_ok,
    ),
    Check(
        "binance_futures_depth",
        "derivatives",
        "SPEC:80",
        "https://fapi.binance.com/fapi/v1/depth",
        {"symbol": "BTCUSDT", "limit": "20"},
        lambda d: _need(d, "bids", "asks", "E"),
        notes="ADR-0007 order_book metriği; yanıtta symbol alanı YOK (istek zaten sabit BTCUSDT).",
    ),
    # ── §2.2 On-chain: bitcoin-data.com ayrı, bütçeli akışta; ChainExposed sadece erişim
    Check(
        "chainexposed_html",
        "onchain",
        "SPEC:57",
        "https://chainexposed.com/",
        None,
        html_ok=True,
        required=False,
        notes="API yok; Faz 2 scrape fizibilitesi için sayfanın ayakta olduğunu doğrula.",
    ),
    # ── §2.3 Spot ve premium (SPEC satır 63-64)
    Check(
        "coinbase_ticker",
        "spot_regional",
        "SPEC:63",
        "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        None,
        lambda d: _need(d, "price", "time"),
    ),
    Check(
        "binance_spot_price",
        "spot_regional",
        "SPEC:63",
        "https://api.binance.com/api/v3/ticker/price",
        {"symbol": "BTCUSDT"},
        lambda d: _need(d, "price", "symbol"),
    ),
    Check(
        "binance_spot_klines",
        "spot_regional",
        "SPEC:97",
        "https://api.binance.com/api/v3/klines",
        {"symbol": "BTCUSDT", "interval": "1h", "limit": "2"},
        _klines_ok,
        notes="ADR-0007 ohlcv_1h metriği; satırlar dict değil sabit-pozisyonlu liste.",
    ),
    Check(
        "upbit_ticker",
        "spot_regional",
        "SPEC:64",
        "https://api.upbit.com/v1/ticker",
        {"markets": "KRW-BTC"},
        lambda d: _need_list_item(d, "trade_price", "timestamp"),
    ),
    # USDKRW adayları (SPEC satır 64 ⚠️: kaynak implementasyonda seçilecek) — en az biri yeterli
    Check(
        "fx_erapi",
        "spot_regional",
        "SPEC:64",
        "https://open.er-api.com/v6/latest/USD",
        None,
        _fx_krw(["rates", "KRW"]),
        required=False,
        notes="Aday A: open.er-api.com (anahtarsız, günlük güncelleme).",
    ),
    Check(
        "fx_frankfurter",
        "spot_regional",
        "SPEC:64",
        "https://api.frankfurter.dev/v1/latest",
        {"base": "USD", "symbols": "KRW"},
        _fx_krw(["rates", "KRW"]),
        required=False,
        notes="Aday B: frankfurter.dev (ECB referans kurları, anahtarsız).",
    ),
    Check(
        "fx_fawazahmed",
        "spot_regional",
        "SPEC:64",
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
        None,
        _fx_krw(["usd", "krw"]),
        required=False,
        notes="Aday C: fawazahmed0/currency-api (jsDelivr CDN, anahtarsız, günlük).",
    ),
    # ── §2.4 Genişlik (SPEC satır 70-72)
    Check(
        "coingecko_global",
        "breadth_rotation",
        "SPEC:70",
        "https://api.coingecko.com/api/v3/global",
        None,
        _cg_global_ok,
        notes="Anahtarsız deneme; 429 görülürse demo key notu SPEC'e işlenecek.",
    ),
    Check(
        "coingecko_markets",
        "breadth_rotation",
        "SPEC:71",
        "https://api.coingecko.com/api/v3/coins/markets",
        {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": "10",
            "page": "1",
            "price_change_percentage": "24h",
        },
        lambda d: _need_list_item(d, "price_change_percentage_24h", "market_cap"),
    ),
    Check(
        "binance_ethbtc",
        "breadth_rotation",
        "SPEC:72",
        "https://api.binance.com/api/v3/ticker/price",
        {"symbol": "ETHBTC"},
        lambda d: _need(d, "price"),
    ),
    # ── §2.5 Döngü ve duyarlılık (SPEC satır 77-78)
    Check(
        "alternative_me_fng",
        "cycle_sentiment",
        "SPEC:77",
        "https://api.alternative.me/fng/",
        {"limit": "2"},
        _fng_ok,
    ),
    Check(
        "cbbi_latest",
        "cycle_sentiment",
        "SPEC:78",
        "https://colintalkscrypto.com/cbbi/data/latest.json",
        None,
        _cbbi_ok,
    ),
]

# bitcoin-data.com keşfi (SPEC satır 47, 54-56): önce OpenAPI dokümanından metrik adları.
# OpenAPI tanımı docs host'undadır (Faz 0 keşfi, 2026-08-03); production server'ı
# api.bitcoin-data.com olarak ilan eder. Veri çağrıları bitcoin-data.com üzerinden de çalışır.
BD_HOST = "https://bitcoin-data.com"
BD_DOC_CANDIDATES = [
    "https://api.bgeometrics.com/v3/api-docs",
    BD_HOST + "/v3/api-docs",
]
BD_KEYWORDS = (
    "sopr",
    "cdd",
    "mvrv",
    "nupl",
    "netflow",
    "reserve",
    "balance",
    "address",
    "liquidation",
)
BD_REQUEST_BUDGET = 5  # host başına toplam; CLAUDE.md kural 8


async def run_check(client: httpx.AsyncClient, chk: Check) -> Result:
    t0 = time.perf_counter()
    try:
        resp = await client.get(chk.url, params=chk.params)
    except httpx.HTTPError as exc:
        if chk.expect_failure:
            return Result(
                chk.check_id,
                chk.layer,
                chk.spec_ref,
                chk.url,
                ok=True,
                required=chk.required,
                detail=f"erişilemedi ({type(exc).__name__}) — 'kaldırıldı' varsayımıyla uyumlu",
            )
        return Result(
            chk.check_id,
            chk.layer,
            chk.spec_ref,
            chk.url,
            ok=False,
            required=chk.required,
            detail=f"istek hatası: {type(exc).__name__}: {exc}",
        )
    ms = int((time.perf_counter() - t0) * 1000)

    # Engel kontrolü expect_failure'dan ÖNCE gelir: aksi hâlde coğrafi 403, "bu uç
    # kaldırılmış" varsayımını doğrulamış gibi görünür ve yanlış sebeple yeşil yanar.
    if reason := geo_block_reason(resp.status_code, resp.text):
        return Result(
            chk.check_id,
            chk.layer,
            chk.spec_ref,
            chk.url,
            ok=False,
            required=chk.required,
            blocked=True,
            status=resp.status_code,
            latency_ms=ms,
            detail=(
                f"ortam engeli ({reason}) — bu koşu sözleşmeyi doğrulamadı; "
                "ihlal edildiğini de göstermiyor"
            ),
        )

    if chk.expect_failure:
        ok = resp.status_code >= 400
        detail = (
            f"HTTP {resp.status_code} — beklendiği gibi hata (endpoint kaldırılmış): "
            f"{resp.text[:120]}"
            if ok
            else f"BEKLENMEDİK: HTTP {resp.status_code} — endpoint hâlâ yanıt veriyor, SPEC yanlış!"
        )
        return Result(
            chk.check_id,
            chk.layer,
            chk.spec_ref,
            chk.url,
            ok=ok,
            required=chk.required,
            status=resp.status_code,
            latency_ms=ms,
            detail=detail,
        )

    if resp.status_code != 200:
        return Result(
            chk.check_id,
            chk.layer,
            chk.spec_ref,
            chk.url,
            ok=False,
            required=chk.required,
            status=resp.status_code,
            latency_ms=ms,
            detail=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    if chk.html_ok:
        ctype = resp.headers.get("content-type", "")
        ok = "html" in ctype
        return Result(
            chk.check_id,
            chk.layer,
            chk.spec_ref,
            chk.url,
            ok=ok,
            required=chk.required,
            status=200,
            latency_ms=ms,
            detail=f"content-type={ctype}, {len(resp.content)} bayt",
        )

    try:
        data = resp.json()
    except ValueError:
        return Result(
            chk.check_id,
            chk.layer,
            chk.spec_ref,
            chk.url,
            ok=False,
            required=chk.required,
            status=200,
            latency_ms=ms,
            detail=f"JSON parse edilemedi: {resp.text[:120]}",
        )

    problem = chk.validate(data) if chk.validate else None
    sample = data[0] if isinstance(data, list) and data else data
    return Result(
        chk.check_id,
        chk.layer,
        chk.spec_ref,
        chk.url,
        ok=problem is None,
        required=chk.required,
        status=200,
        latency_ms=ms,
        detail=problem or ("alanlar doğrulandı" + (f" — {chk.notes}" if chk.notes else "")),
        sample=str(sample)[:200],
    )


async def verify_bitcoin_data(client: httpx.AsyncClient) -> list[Result]:
    """OpenAPI keşfi + en fazla 3 veri çağrısı. Toplam host bütçesi: BD_REQUEST_BUDGET."""
    results: list[Result] = []
    budget = BD_REQUEST_BUDGET
    paths: list[str] = []

    for doc_url in BD_DOC_CANDIDATES:
        if budget <= 0:
            break
        budget -= 1
        try:
            resp = await client.get(doc_url)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        try:
            doc = resp.json()
        except ValueError:
            continue
        if isinstance(doc, dict) and "paths" in doc:
            paths = sorted(doc["paths"])
            interesting = [p for p in paths if any(k in p.lower() for k in BD_KEYWORDS)]
            results.append(
                Result(
                    "bitcoin_data_openapi",
                    "onchain",
                    "SPEC:54-56",
                    doc_url,
                    ok=True,
                    required=True,
                    status=200,
                    detail=(
                        f"OpenAPI bulundu: {len(paths)} path. "
                        f"İlgili metrik path'leri ({len(interesting)}): {interesting[:40]}"
                    ),
                )
            )
            break

    if not paths:
        results.append(
            Result(
                "bitcoin_data_openapi",
                "onchain",
                "SPEC:54-56",
                BD_HOST,
                ok=False,
                required=True,
                detail=(
                    "OpenAPI dokümanı bulunamadı; metrik adları elle doğrulanmalı "
                    f"(denenen: {BD_DOC_CANDIDATES})"
                ),
            )
        )

    # Veri çağrıları: tam seriyi çekmemek için "/{last}" varyantı tercih edilir
    # (API deseni: /v1/sth-sopr/{last} → /v1/sth-sopr/last son gözlemi döndürür)
    probe_targets: list[tuple[str, str]] = []
    if paths:

        def pick(*keys: str) -> str | None:
            for p in paths:
                lp = p.lower()
                if p.endswith("/{last}") and all(k in lp for k in keys):
                    return p.replace("{last}", "last")
            return None

        for label, keys in [
            ("sth_sopr", ("sth", "sopr")),
            ("whale_balance", ("balance", "1k")),
            ("liquidation", ("liquidation", "1d")),
        ]:
            p = pick(*keys)
            if p and not any(lbl == label for lbl, _ in probe_targets):
                probe_targets.append((label, p))
    else:
        probe_targets = [("sth_sopr", "/v1/sth-sopr/last")]  # dokümansız tek tahmin

    for label, path in probe_targets[:3]:
        if budget <= 0:
            break
        budget -= 1
        url = BD_HOST + path
        t0 = time.perf_counter()
        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            results.append(
                Result(
                    f"bitcoin_data_{label}",
                    "onchain",
                    "SPEC:54-56",
                    url,
                    ok=False,
                    required=False,
                    detail=f"istek hatası: {type(exc).__name__}",
                )
            )
            continue
        ms = int((time.perf_counter() - t0) * 1000)
        blocked_reason = geo_block_reason(resp.status_code, resp.text)
        ok = resp.status_code == 200
        detail = f"HTTP {resp.status_code}"
        sample = None
        if blocked_reason:
            detail = f"ortam engeli ({blocked_reason}) — doğrulanmadı"
        elif ok:
            try:
                data = resp.json()
                sample = str(data[0] if isinstance(data, list) and data else data)[:200]
                detail = "veri döndü"
            except ValueError:
                ok, detail = False, f"JSON parse edilemedi: {resp.text[:120]}"
        else:
            detail = f"HTTP {resp.status_code}: {resp.text[:160]}"
        results.append(
            Result(
                f"bitcoin_data_{label}",
                "onchain",
                "SPEC:54-56",
                url,
                ok=ok,
                required=False,
                blocked=blocked_reason is not None,
                status=resp.status_code,
                latency_ms=ms,
                detail=detail,
                sample=sample,
            )
        )
        await asyncio.sleep(1.0)  # aynı hosta nazik davran

    return results


async def main_async(skip_bitcoin_data: bool) -> list[Result]:
    limits = httpx.Limits(max_connections=5)
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers=HEADERS, limits=limits, follow_redirects=True
    ) as client:
        sem = asyncio.Semaphore(5)

        async def guarded(chk: Check) -> Result:
            async with sem:
                return await run_check(client, chk)

        results = list(await asyncio.gather(*(guarded(c) for c in CHECKS)))
        if not skip_bitcoin_data:
            results.extend(await verify_bitcoin_data(client))
    return results


def render(results: list[Result]) -> tuple[str, int, int]:
    """Rapor metni + (zorunlu FAIL sayısı, ortam engeli sayısı)."""
    lines = ["| durum | check | HTTP | ms | SPEC | detay |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {STATE_MARKS[r.state]} | {r.check_id} | {r.status or '-'} | {r.latency_ms or '-'} "
            f"| {r.spec_ref} | {r.detail[:220]} |"
        )
    ok_count = sum(1 for r in results if r.state == "ok")
    fails_required = sum(1 for r in results if r.state == "fail")
    blocked = [r for r in results if r.state == "blocked"]
    lines.append(
        f"\nToplam: {len(results)} kontrol, {ok_count} OK, {fails_required} zorunlu FAIL, "
        f"{len(blocked)} blocked_in_environment"
    )
    if blocked:
        # Engeli sessizce yutmak "hepsini doğruladık" gibi okunur; ne doğrulanmadığını yaz.
        lines.append(
            "\nblocked_in_environment — bu koşuda DOĞRULANMAYAN kontroller: "
            + ", ".join(f"{r.check_id} ({r.status})" for r in blocked)
            + "\nBu uçlar isteğin geldiği ülke/ağ nedeniyle reddedildi. Sözleşmeleri kırık "
            "değil, yalnızca doğrulanmamıştır — bu koşu onlar için kanıt üretmemiştir. "
            "Kanıt gerekiyorsa script'i engellenmemiş bir ağdan (yerel makine veya "
            "self-hosted runner) --fail-on-blocked ile çalıştırın."
        )
    return "\n".join(lines), fails_required, len(blocked)


EVIDENCE_HEADER = """# Endpoint doğrulama kanıt kütüğü

Günlük `MCP Smoke` iş akışı GitHub-hosted runner'dan koşar ve o bölge Binance/Bybit
tarafında coğrafi olarak engellidir (ADR-0009). O koşu **yeşil** görünür ama Binance
zinciri için **kanıt üretmez** — engellenen kontroller `blocked_in_environment` sayılır.

Bu kütük, o boşluğun tek kapatıcısıdır: **engellenmemiş bir ağdan** koşulmuş, hiçbir
kontrolü engelli olmayan doğrulamaların tarihli kaydı. Yalnız `--record` bayrağı yazar ve
kapı kapalıdır — engelli ya da kırık bir koşu buraya giremez (ADR-0013).

Kütük **append-only**dir: geçmiş girdi düzeltilmez, yeni koşu sona eklenir. Ham piyasa
verisi (yanıt gövdeleri) buraya girmez; yalnız kontrol kimliği, HTTP durumu ve SPEC
referansı tutulur (platform CLAUDE.md kural 2).
"""


class EvidenceRefused(Exception):
    """Bu koşu kanıt değildir; kütüğe yazılmaz."""


def _git_commit() -> str:
    """Kanıtın hangi kod sürümünde üretildiği. Belirlenemezse uydurulmaz."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
    except (OSError, subprocess.SubprocessError):
        return "bilinmiyor"
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else "bilinmiyor"


def evidence_entry(results: list[Result], *, run_at: str, commit: str, full_scope: bool) -> str:
    """Tek koşunun kanıt girdisi. Yalnız engelsiz ve kırıksız koşu için üretilir.

    Kapı bilinçli olarak kapalıdır. Engelli bir koşuyu kaydetmek, kütüğün tek işlevini —
    "bu uçlar gerçekten doğrulandı" demeyi — ortadan kaldırırdı; kısmi kayıt, okuyucuya
    doğrulanmamış bir zinciri doğrulanmış gibi gösterirdi.
    """
    blocked = [r for r in results if r.state == "blocked"]
    if blocked:
        raise EvidenceRefused(
            "engelli koşu kanıt değildir; kaydedilmedi. Engellenen kontroller: "
            + ", ".join(r.check_id for r in blocked)
        )
    failed = [r for r in results if r.state == "fail"]
    if failed:
        raise EvidenceRefused(
            "zorunlu kontrol düşmüş bir koşu kanıt değildir; kaydedilmedi. Düşenler: "
            + ", ".join(r.check_id for r in failed)
        )

    warns = [r for r in results if r.state == "warn"]
    scope = "tam (bitcoin-data dâhil)" if full_scope else "bitcoin-data hariç"
    lines = [
        f"\n## {run_at} — commit `{commit}`",
        "",
        "- **Ağ:** engelli değil — hiçbir kontrol `blocked_in_environment` dönmedi.",
        f"- **Kapsam:** {len(results)} kontrol, {scope}.",
        f"- **Sonuç:** {len(results) - len(warns)} OK, 0 zorunlu FAIL, {len(warns)} warn.",
    ]
    if warns:
        # Bilgilendirici kontrol düşmesi kaydı engellemez ama kütükte GÖRÜNÜR kalır;
        # aksi hâlde girdi "her şey doğrulandı" diye okunurdu.
        lines.append(
            "- **warn (bilgilendirici, doğrulanmadı):** "
            + ", ".join(f"{r.check_id} ({r.status})" for r in warns)
        )
    lines += ["", "| check | HTTP | SPEC |", "|---|---|---|"]
    lines += [f"| {r.check_id} | {r.status or '-'} | {r.spec_ref} |" for r in results]
    return "\n".join(lines) + "\n"


def record_evidence(
    results: list[Result], path: str, *, run_at: str, commit: str, full_scope: bool
) -> str:
    """Girdiyi kütüğün SONUNA ekler; var olan içeriğe dokunmaz."""
    entry = evidence_entry(results, run_at=run_at, commit=commit, full_scope=full_scope)
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8") as handle:
        if not exists:
            handle.write(EVIDENCE_HEADER)
        handle.write(entry)
    return path


def exit_code(fails_required: int, blocked: int, fail_on_blocked: bool) -> int:
    """0 = engellenmiş-ama-erişilebilir dâhil temiz; 1 = sözleşme kırılması; 2 = engel.

    Sözleşme kırılması engeli ezer: her ikisi de varsa çıkış kodu 1'dir, çünkü asıl
    haber sözleşmenin kırılmış olmasıdır.
    """
    if fails_required:
        return 1
    return 2 if (blocked and fail_on_blocked) else 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--skip-bitcoin-data",
        action="store_true",
        help="bitcoin-data.com bütçesini koru (CI cron için önerilir)",
    )
    ap.add_argument("--json-out", type=str, default=None)
    ap.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help=(
            "ortam engelini de başarısızlık say (çıkış kodu 2). Engellenmemiş bir ağdan "
            "koşarken kullanın; GitHub-hosted runner'da engel beklenen durumdur."
        ),
    )
    ap.add_argument(
        "--record",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "engelsiz ve kırıksız koşuyu kanıt kütüğüne EKLE (append-only). Engelli ya da "
            "zorunlu kontrolü düşmüş koşu reddedilir; bkz. ADR-0013."
        ),
    )
    args = ap.parse_args()

    results = asyncio.run(main_async(args.skip_bitcoin_data))
    report, fails, blocked = render(results)
    print(report)
    if args.record:
        try:
            path = record_evidence(
                results,
                args.record,
                run_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
                commit=_git_commit(),
                full_scope=not args.skip_bitcoin_data,
            )
        except EvidenceRefused as exc:
            print(f"\nKANIT KAYDEDİLMEDİ: {exc}")
        else:
            print(f"\nKanıt kütüğüne eklendi: {path}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            payload = [{**asdict(r), "state": r.state} for r in results]
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\nJSON: {args.json_out}")
    sys.exit(exit_code(fails, blocked, args.fail_on_blocked))


if __name__ == "__main__":
    main()
