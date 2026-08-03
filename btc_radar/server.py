"""btc-radar FastMCP sunucu girişi.

CLAUDE.md gereği bu dosyada SADECE @app.tool tanımları, shape() ve classify_tool_error()
bulunur. Veri toplama/normalizasyon/skorlama core/ ve providers/ altındadır (Faz 1).
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from btc_radar import __version__
from btc_radar.core.config import load_signal_rules, load_weights, weights_hash

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
                f"{source}: rate limit (429). Önbellekteki son değeri kullan; "
                "yeniden denemeden önce kaynağın TTL süresi kadar bekle."
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


@app.tool(annotations={"readOnlyHint": True})
async def get_health() -> dict[str, Any]:
    """Sunucu, config ve kaynak sağlık durumu (SDET aracı; SPEC §4 araç 8).

    Faz 0 kapsamı: sunucu kimliği + config yükleme doğrulaması. Provider erişilebilirliği,
    önbellek yaşları, son hatalar ve rate-limit sayaçları Faz 1'de eklenecek.

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
            "providers": [],
            "cache": {"initialized": False},
            "phase": "0-iskelet",
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
