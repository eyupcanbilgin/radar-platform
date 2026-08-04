"""Generate an evidence-neutral Markdown summary from a pulse-v2 JSON artifact."""

import argparse
import json
import math
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    SERVICE_ROOT / "docs" / "reviews" / "2026-08-04-eleme-v2-draft" / "pulse-v2-results.json"
)


def _number(value: float | None, digits: int = 4) -> str:
    if value is None or not math.isfinite(value):
        return "NaN"
    return f"{value:.{digits}f}"


def build_report(data: dict) -> str:
    tests = data["tests"]
    dirty = bool(data.get("provenance", {}).get("git_dirty", True))
    evidence_status = "DRAFT — dirty çalışma ağacı" if dirty else "DEVELOPMENT REANALYSIS"
    directional_candidates = [
        test
        for test in tests
        if test["valid"]
        and test["mode"] == "directional"
        and test["alternative"] == "greater"
        and test["beats_cost"]
        and test["sig_fdr_05"]
    ]
    volatility_candidates = [
        test
        for test in tests
        if test["valid"]
        and test["mode"] == "volatility_ratio"
        and test["economic_magnitude"]
        and test["sig_fdr_05"]
    ]

    lines = [
        "# Hipotez Eleme Tezgâhı — pulse-v2 Development Reanalysis",
        "",
        f"**Kanıt durumu:** {evidence_status}  ",
        f"**Yöntem:** `{data['method_version']}`  ",
        f"**Dönem:** {data['start']} → {data['end']}  ",
        f"**Kayıtlı/geçerli/geçersiz:** {data['total_registered_tests']} / "
        f"{data['valid_tests']} / {data['invalid_tests']}  ",
        "**Locked OOS:** Kullanılmadı; bu çıktı yalnız Development reanalysis'tir.",
        "",
        "> Bu rapor bağımsız inceleme ve temiz commit olmadan final kanıt değildir. Eski",
        "> 126-test raporunun üzerine yazmaz ve onun geri çekilmiş p-değerlerini kullanmaz.",
        "",
        "## Aday özeti",
        "",
        f"- Maliyet eşiğini aşan ve FDR %5 yönsel aday: {len(directional_candidates)}",
        f"- Önceden tanımlı yönde ve FDR %5 volatilite adayı: {len(volatility_candidates)}",
        "",
        "## Test matrisi",
        "",
        "| Kart | Varlık | Varyant | Ufuk | Mod/alternatif | Ham n | Efektif n | "
        "Etki | p | FDR p | Geçerli |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for test in tests:
        unit = "bps" if test["mode"] == "directional" else "% vol"
        lines.append(
            f"| {test['card']} | {test['symbol']} | {test['variant']} | "
            f"{test['horizon']} | {test['mode']}/{test['alternative']} | "
            f"{test['raw_n_signals']} | {test['n_signals']} | "
            f"{_number(test['mean_bps'], 2)} {unit} | {_number(test['p_raw'])} | "
            f"{_number(test['p_fdr'])} | {'EVET' if test['valid'] else 'HAYIR'} |"
        )

    lines.extend(
        [
            "",
            "## Yöntem notu",
            "",
            "- Her test kendi ufkundaki forward dağılımla karşılaştırıldı.",
            "- Circular moving-block bootstrap kullanıldı.",
            "- Örtüşen forward pencereler efektif olay örnekleminden çıkarıldı.",
            "- Test alternatifi sonuç görülmeden yöntem içinde sabitlendi.",
            "- BH düzeltmesi yalnız geçerli p-değerleri üzerinde uygulandı.",
            "- Referans giriş kapanmış karar mumundan sonraki mum açılışıdır.",
            "",
            "Hiçbir volatilite bulgusu tek başına yönsel strateji veya pozisyon boyutu kuralı",
            "sayılmaz. Önce ayrı hipotez kartı ve forward A/B karşılaştırması gerekir.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".md")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(data), encoding="utf-8")
    print(f"Rapor yazıldı: {output}")


if __name__ == "__main__":
    main()
