"""btc-radar FastMCP sunucu girişi.

CLAUDE.md gereği bu dosyada SADECE @app.tool tanımları, shape() ve classify_tool_error()
bulunur. Veri toplama/normalizasyon/skorlama core/ ve providers/ altındadır (Faz 1).
"""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from btc_radar import __version__
from btc_radar.core.config import load_signal_rules, load_weights, weights_hash
from btc_radar.core.coverage import collection_coverage
from btc_radar.core.heartbeat import HeartbeatStore
from btc_radar.core.scheduler import TASK_COLLECT, TASK_PUBLISH
from btc_radar.core.snapshot import FEATURE_VERSION, SCORING_VERSION
from btc_radar.core.store import SCHEMA_VERSION as STORE_SCHEMA_VERSION
from btc_radar.core.store import PointInTimeStore
from btc_radar.models.config import SignalRulesConfig
from btc_radar.providers.binance_futures import BinanceFuturesProvider
from btc_radar.providers.binance_futures_history import BinanceFuturesHistoryProvider
from btc_radar.providers.binance_spot import BinanceSpotProvider
from btc_radar.providers.binance_spot_history import BinanceSpotHistoryProvider

logger = logging.getLogger(__name__)

app = FastMCP(
    name="btc-radar",
    version=__version__,
    instructions=(
        "Bitcoin merkezli, salt-okunur piyasa analiz araçları. "
        "Skorlar deterministiktir; yorum ve raporlama LLM'e aittir. "
        "Hiçbir çıktı yatırım tavsiyesi değildir; emir gönderilmez, hesaba bağlanılmaz."
    ),
)


def shape(
    payload: dict[str, Any], *, truncated: bool = False, guidance: str | None = None
) -> dict[str, Any]:
    """Her araç yanıtının zorunlu son adımı (CLAUDE.md kural 5).

    Faz 0: null/None temizliği + kırpma metası. Kompakt markdown/TSV render'ı Faz 1'de
    araç bazında eklenecek.
    """
    cleaned = _strip_nulls(payload)
    if truncated:
        meta = cleaned.setdefault("meta", {})
        meta["truncated"] = True
        meta["guidance"] = guidance or (
            "Yanıt kırpıldı; daha dar bir parametreyle (ör. daha kısa window/lookback) "
            "tekrar çağır."
        )
    return cleaned


def _strip_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nulls(v) for v in value if v is not None]
    return value


def classify_tool_error(exc: Exception, source: str) -> ToolError:
    """Her exception'ı LLM'e 'sonraki adımda ne dene' söyleyen ToolError'a çevirir (kural 6).

    Ham stack trace LLM'e sızmaz; detay logger.exception ile stderr'e yazılır.
    """
    logger.exception("%s kaynağında hata", source)
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return ToolError(
                f"{source}: rate limit (429). Hızlı retry yapma; Retry-After süresini "
                "bekle veya süre verilmediyse çağrıyı daha sonra yeniden dene."
            )
        if code in (401, 403):
            return ToolError(
                f"{source}: erişim reddedildi ({code}). Anahtar/kayıt gerekiyor olabilir; "
                "get_health ile kaynak durumunu kontrol et."
            )
        if code == 404:
            return ToolError(
                f"{source}: endpoint bulunamadı (404). Endpoint sözleşmesi değişmiş olabilir; "
                "bu metriği atla ve sorunu kullanıcıya raporla."
            )
        if code >= 500:
            return ToolError(
                f"{source}: kaynak tarafında hata ({code}). Kısa süre sonra tekrar dene; "
                "sürerse varsa alternatif venue parametresini kullan."
            )
        return ToolError(
            f"{source}: HTTP {code}. Parametreleri şemadaki Literal değerleriyle sınırla "
            "ve tekrar dene."
        )
    if isinstance(exc, httpx.TimeoutException):
        return ToolError(
            f"{source}: zaman aşımı. Bir kez tekrar dene; sürerse get_health ile "
            "kaynak erişilebilirliğini kontrol et."
        )
    if isinstance(exc, httpx.TransportError):
        return ToolError(f"{source}: ağ hatası. Bağlantıyı kontrol edip tekrar dene.")
    if isinstance(exc, ValueError):
        return ToolError(
            f"{source}: veri sözleşmesi ihlali — {exc}. Bu veri noktasını kullanma; "
            "sorunu kullanıcıya raporla."
        )
    return ToolError(
        f"{source}: beklenmeyen hata ({type(exc).__name__}). get_health çağır ve "
        "sorunu kullanıcıya raporla."
    )


DerivativeMetric = Literal["mark_price", "funding_rate", "open_interest", "all"]

#: get_health kapsama penceresi: son 7 gün, operatörün "toplayıcı bu hafta delik verdi mi"
#: sorusunun karşılığı. Feature'ların kendi lookback'i bundan bağımsızdır.
HEALTH_COVERAGE_WINDOW_SECONDS = 7 * 86400.0


@app.tool(annotations={"readOnlyHint": True})
async def get_derivatives(
    metric: Annotated[
        DerivativeMetric,
        Field(
            description="BTCUSDT USD-M public türev metriği veya üçlü paket",
            examples=["all", "funding_rate"],
        ),
    ] = "all",
) -> dict[str, Any]:
    """Gerçek Binance BTCUSDT mark fiyatı, funding ve açık pozisyon gözlemleri.

    Örnekler:
        get_derivatives(metric="all")
        get_derivatives(metric="open_interest")

    Ham gözlemler PIT-uyumlu zaman alanlarıyla döner. Bu araç anlık gözlem aracıdır:
    kırılganlık skoru geçmiş seri gerektirir ve saatlik ``decision-context/v1`` üzerinden
    yayınlanır (ADR-0005). Yön skoru hiçbir yüzeyde üretilmez — kabul edilmiş yönsel kural
    yoktur.
    """
    logger.info("get_derivatives çağrıldı: metric=%s", metric)
    try:
        async with BinanceFuturesProvider() as provider:
            observations = await provider.fetch(metric, symbol="BTCUSDT")
        rows = []
        for observation in observations:
            row = observation.model_dump(mode="json")
            row["available_at_utc"] = observation.effective_available_at.isoformat()
            rows.append(row)
        return shape(
            {
                "instrument": {
                    "asset": "BTC",
                    "symbol": "BTCUSDT",
                    "market": "USDT_PERPETUAL",
                    "venue": "binance_futures",
                },
                "observations": rows,
                "meta": {
                    "provider": provider.name,
                    "observation_count": len(rows),
                    "scoring_available": False,
                    "scoring_blocker": "tool_returns_raw_observations_only",
                },
            }
        )
    except Exception as exc:
        raise classify_tool_error(exc, BinanceFuturesProvider.name) from exc


def _store_path(env_name: str) -> Path | None:
    value = os.environ.get(env_name)
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None


def _collection_health(rules: SignalRulesConfig) -> dict[str, Any]:
    """Toplayıcının gerçekten koştuğuna ve serinin tam olduğuna dair yerel kanıt.

    Ağ çağrısı yapılmaz; yalnız yerel PIT ve heartbeat depoları okunur. Depolar
    tanımlı değilse bu açıkça söylenir — sessizce "sağlıklı" dönmek, health aracının
    yapabileceği en kötü şey olurdu.
    """
    pit_path = _store_path("BTC_RADAR_DB_PATH")
    heartbeat_path = _store_path("BTC_RADAR_HEARTBEAT_DB_PATH")
    if pit_path is None and heartbeat_path is None:
        return {
            "status": "not_configured",
            "detail": "BTC_RADAR_DB_PATH / BTC_RADAR_HEARTBEAT_DB_PATH tanımlı değil",
        }

    now = datetime.now(UTC)
    report: dict[str, Any] = {"status": "ok"}
    try:
        if heartbeat_path is not None:
            with HeartbeatStore(heartbeat_path) as heartbeat:
                report["tasks"] = heartbeat.summary(now=now, tasks=(TASK_COLLECT, TASK_PUBLISH))
        if pit_path is not None:
            with PointInTimeStore(pit_path) as pit:
                coverage = collection_coverage(
                    pit, rules=rules, as_of=now, window_seconds=HEALTH_COVERAGE_WINDOW_SECONDS
                )
            report["coverage"] = [item.as_payload() for item in coverage]
            report["healthy"] = bool(coverage) and all(item.meets_expectation for item in coverage)
    except Exception as error:  # sağlık aracı patlamaz, arızayı raporlar
        logger.exception("toplama sağlığı okunamadı")
        return {
            "status": "unreadable",
            "error_type": type(error).__name__,
            "detail": " ".join(str(error).split())[:300],
        }
    return report


@app.tool(annotations={"readOnlyHint": True})
async def get_health() -> dict[str, Any]:
    """Sunucu, config ve kaynak sağlık durumu (SDET aracı; SPEC §4 araç 8).

    Mevcut kapsam: sunucu/config kimliği ve uygulanmış provider yetenekleri. Health çağrısı
    dış ağa çıkmaz; gerçek erişilebilirlik, cache yaşları ve rate-limit sayaçları sonraki
    operasyon diliminde eklenecek.

    Örnek çağrılar:
        get_health()
            → {"status": "ok", "server": {"name": "btc-radar", ...}, "config": {...}}
        get_health()  # weights.yaml bozuksa
            → ToolError: "config: veri sözleşmesi ihlali — katman ağırlıkları toplamı ..."
    """
    logger.info("get_health çağrıldı (parametre yok)")
    try:
        weights = load_weights()
        rules = load_signal_rules()
        payload = {
            "status": "ok",
            "server": {"name": "btc-radar", "version": __version__, "transport": "stdio"},
            "config": {
                "weights_version": weights.version,
                "weights_hash": weights_hash(),
                "layers": weights.layers,
                "confidence_insufficient_below": weights.confidence.insufficient_below,
                "signal_rules_version": rules.version,
                "signal_rule_count": len(rules.rules),
            },
            "providers": [
                {
                    "name": BinanceFuturesProvider.name,
                    "mode": "public_current_snapshot",
                    "metrics": sorted(BinanceFuturesProvider.supported_metrics - {"all"}),
                    "health": "not_polled",
                },
                {
                    "name": BinanceFuturesHistoryProvider.name,
                    "mode": "public_history_backfill",
                    "metrics": sorted(BinanceFuturesHistoryProvider.supported_metrics),
                    "health": "not_polled",
                },
                {
                    "name": BinanceSpotProvider.name,
                    "mode": "public_current_snapshot",
                    "metrics": sorted(BinanceSpotProvider.supported_metrics - {"all"}),
                    "health": "not_polled",
                },
                {
                    "name": BinanceSpotHistoryProvider.name,
                    "mode": "public_history_backfill",
                    "metrics": sorted(BinanceSpotHistoryProvider.supported_metrics),
                    "health": "not_polled",
                },
            ],
            "cache": {"initialized": False},
            "store": {
                "pit_schema_version": STORE_SCHEMA_VERSION,
                "feature_version": FEATURE_VERSION,
                "scoring_version": SCORING_VERSION,
            },
            "collection": _collection_health(rules),
            "phase": "1e-spot-history + collection coverage (direction unavailable)",
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
        }
        return shape(payload)
    except Exception as exc:
        raise classify_tool_error(exc, "config") from exc


def main() -> None:
    # stdio transport stdout'u kullanır; log her zaman stderr'e gider.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app.run()


if __name__ == "__main__":
    main()
