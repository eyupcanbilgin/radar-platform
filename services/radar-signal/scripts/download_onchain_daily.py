"""Download a public bitcoin-data.com daily on-chain series into the ignored user_data tree.

Neden bu kaynak: dört yönsel aile de reddedildi (S-0003, S-0004, S-0005, S-0006) ve elimizdeki
**uzun geçmişli** yüzey — perp funding ile üç mekânın OHLCV'si — bu dört mekanizmayla tükendi.
On-chain sahip davranışı (kâr realizasyonu / kapitülasyon) o dördünün hiçbiriyle akraba
değildir: ne türev konumlanması, ne fiyat/volatilite rejimi, ne mekânlar arası fiyat farkı, ne
de hacmin finansman biçimi. Beşinci ailenin ölçülebilmesi için gereken yüzey budur.

Uç sözleşmesi (11 Ağu 2026 canlı doğrulandı):

    GET https://bitcoin-data.com/v1/sth-sopr
    → [{"d": "2022-08-11", "unixTs": 1660176000, "sthSopr": 1.0055}, ...]

Tek istekte 1461 günlük satır (2022-08-11 → 2026-08-10), anahtarsız. bitcoin-data.com bütçesi
8/saat ve 15/gün'dür (MCP CLAUDE.md kural 8): tam seri **tek** çağrıyla iner, sayfalama yok.

## Look-ahead: bu dosyanın asıl işi

Günlük bir metrik, gün kapanmadan var olamaz. `d = D` satırı D gününü özetler ve en erken
D+1 00:00Z'de doğabilir; üstüne indeksleme/yayın gecikmesi biner. Ölçüm bu satırı D günü
içinde kullanırsa sonuç **gelecekten bilgi taşır** ve hipotez ölçülmemiş olur.

Bu yüzden her satır iki ayrı zaman taşır:

- `event_time_utc` = D+1 00:00Z — günün kapandığı, yani değerin özetlediği dönemin sonu.
- `available_at_utc` = event_time + PUBLICATION_LAG_HOURS — değerin **kullanılabildiği** an.

Gecikme bilinçli olarak cömerttir (aşağıya bkz.) ve ölçüm sonucuna göre **daraltılamaz**:
daraltmak, sonucu gördükten sonra kuralı gevşetmek olurdu. Yalnız yayın gecikmesini ayrıca
ön-kaydedilmiş bir ölçümle karakterize ederek değiştirilebilir.
"""

import argparse
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datapaths import market_data_root  # noqa: E402

HOST = "https://bitcoin-data.com"
TIMEOUT = 30.0
HEADERS = {"User-Agent": "btc-radar-research/0.1 (read-only; public series)"}

#: Gün kapandıktan sonra değerin kullanılabilir sayıldığı gecikme.
#:
#: 11 Ağu 2026 11:47Z'de `d = 2026-08-10` satırı mevcuttu; yani gerçek yayın gecikmesi o gün
#: için ≤ 11s47dk idi. Tek gözlem bir dağılım değildir, bu yüzden onun iki katından fazlası
#: seçildi: 24 saat. Hata payı bilinçli olarak **sinyali zayıflatan** yöne bırakıldı — ters
#: yön look-ahead olurdu ve ölçümü geçersiz kılardı.
PUBLICATION_LAG_HOURS = 24

DAY = timedelta(days=1)


def _parse_day(raw: object) -> datetime:
    """`YYYY-MM-DD` → gün başlangıcı (UTC). Fail-loud: tahmin yok."""
    if not isinstance(raw, str):
        raise ValueError(f"gün alanı metin olmalı, {type(raw).__name__} geldi: {raw!r}")
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"gün alanı YYYY-MM-DD değil: {raw!r}") from exc
    return parsed.replace(tzinfo=UTC)


def _parse_value(raw: object, *, day: str) -> float:
    """Sayı parse edilemiyorsa yükselir; asla 0/None'a düşmez (eksik veri sıfır değildir)."""
    if raw is None or isinstance(raw, bool):
        raise ValueError(f"{day}: değer sayı değil: {raw!r}")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{day}: değer sayıya çevrilemedi: {raw!r}") from exc


def available_at(day_start: datetime) -> datetime:
    """D gününün değeri ne zaman kullanılabilir: gün kapanışı + yayın gecikmesi."""
    return day_start + DAY + timedelta(hours=PUBLICATION_LAG_HOURS)


def to_frame(rows: list[dict], *, value_key: str, until_utc: datetime) -> pd.DataFrame:
    """Ham günlük satırları PIT-güvenli çerçeveye çevirir.

    ``until_utc`` **`available_at_utc` üzerine** ve dışlayıcı uygulanır; kesim gün üzerinden
    yapılsaydı, sınırdan hemen önceki güne ait ama sınırdan sonra doğan bir satır dosyaya
    girer ve Locked OOS sınırını içeriden delerdi.
    """
    if until_utc.tzinfo is None:
        raise ValueError("until_utc timezone-aware olmalı")
    if not rows:
        raise ValueError("seri boş döndü; sessizce boş dosya yazılmaz")

    records = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"satır dict olmalı, {type(row).__name__} geldi: {row!r}")
        if "d" not in row:
            raise ValueError(f"satırda 'd' alanı yok: {row!r}")
        if value_key not in row:
            raise ValueError(f"satırda '{value_key}' alanı yok: {row!r}")
        day_start = _parse_day(row["d"])
        records.append(
            {
                "day": row["d"],
                "event_time_utc": day_start + DAY,
                "available_at_utc": available_at(day_start),
                value_key: _parse_value(row[value_key], day=row["d"]),
            }
        )

    frame = pd.DataFrame.from_records(records).sort_values("event_time_utc")
    duplicated = frame["day"][frame["day"].duplicated()].tolist()
    if duplicated:
        raise ValueError(f"aynı gün birden çok satırla geldi: {sorted(set(duplicated))[:10]}")

    frame = frame[frame["available_at_utc"] < until_utc].reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"{until_utc.isoformat()} öncesinde kullanılabilir satır yok")

    frame.attrs["coverage"] = {
        "rows": int(len(frame)),
        "first_day": frame["day"].iloc[0],
        "last_day": frame["day"].iloc[-1],
        "publication_lag_hours": PUBLICATION_LAG_HOURS,
        "gaps": daily_gaps(frame),
    }
    return frame


def daily_gaps(frame: pd.DataFrame) -> list[dict]:
    """Takvimde atlanan günler. Boşluk sessizce doldurulmaz; raporlanır."""
    gaps = []
    times = list(frame["event_time_utc"])
    for left, right in zip(times, times[1:], strict=False):
        missing = (right - left).days - 1
        if missing > 0:
            gaps.append(
                {
                    "after_utc": left.isoformat(),
                    "before_utc": right.isoformat(),
                    "missing_days": int(missing),
                }
            )
    return gaps


def fetch_series(path: str) -> list[dict]:
    """Tam seriyi tek çağrıyla indirir (bütçe: bkz. modül başlığı)."""
    url = HOST + path
    response = httpx.get(url, timeout=TIMEOUT, headers=HEADERS, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"{url}: liste bekleniyordu, {type(payload).__name__} geldi")
    return payload


def write_atomic(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".feather")
    os.close(handle)
    frame.to_feather(temporary)
    os.replace(temporary, destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="/v1/sth-sopr", help="bitcoin-data.com seri yolu")
    parser.add_argument("--value-key", default="sthSopr", help="satırdaki değer alanı")
    parser.add_argument("--out-name", default="STH_SOPR-1d.feather")
    parser.add_argument(
        "--end",
        required=True,
        help=(
            "dışlayıcı UTC sınırı, available_at üzerine uygulanır; "
            "Locked OOS için 2026-08-04T00:00:00Z"
        ),
    )
    args = parser.parse_args(argv)

    until = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    frame = to_frame(fetch_series(args.path), value_key=args.value_key, until_utc=until)
    destination = market_data_root() / "onchain" / "bitcoin-data" / args.out_name
    write_atomic(frame, destination)
    coverage = frame.attrs["coverage"]
    print(
        f"OK: {destination} · {coverage['rows']} gün "
        f"({coverage['first_day']} → {coverage['last_day']}) · "
        f"{len(coverage['gaps'])} boşluk · yayın gecikmesi "
        f"{coverage['publication_lag_hours']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
