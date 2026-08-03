"""Point-in-time (PIT) ham veri deposu — CR-002 P0-1.

Neden var: backtest ve replay yalnız "karar anında GERÇEKTEN bilinebilen" veriyi
görmelidir. Bir metriğin `event_time`'ı (ait olduğu an) ile `available_at`'i (sistemce
ilk bilinebildiği an) farklıdır; saat sonu verisiyle saat başında karar vermek
look-ahead'dir (SPEC §2.1 yayın-anı kuralı, CLAUDE.md kural 5 / radar-signal CR-3).

Tasarım notları:
- Depo APPEND-ONLY'dir. Aynı `event_time` için sonradan revize edilmiş bir değer
  gelirse (on-chain revizyon riski) satır GÜNCELLENMEZ, yeni `available_at` ile yeni
  satır yazılır. Böylece "o gün ne biliyorduk" ile "bugün geçmiş için ne diyor"
  ayrı ayrı sorgulanabilir (Historical Revision Delta testinin veri temeli).
- `read_as_of(as_of)` bir metrik/varlık/venue üçlüsü için yalnız
  `available_at <= as_of` satırlarından EN GÜNCEL `event_time`'ı seçer; eşitlikte
  daha geç `available_at` kazanır (revizyon), o da eşitse daha büyük rowid.
- Zaman alanları veritabanında ISO-8601 UTC metin olarak tutulur; metin sıralaması
  kronolojik sıralamayla aynıdır (sabit ofset "+00:00" ve sabit alan genişliği).
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from btc_radar.models.observation import RawObservation

SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE IF NOT EXISTS observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time     TEXT NOT NULL,
    available_at   TEXT NOT NULL,
    ingested_at    TEXT NOT NULL,
    provider       TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_hash   TEXT NOT NULL,
    asset          TEXT NOT NULL,
    venue          TEXT NOT NULL,
    metric         TEXT NOT NULL,
    raw_value      REAL NOT NULL,
    unit           TEXT NOT NULL,
    window         TEXT,
    source_group   TEXT NOT NULL,
    source_url     TEXT NOT NULL,
    quality        REAL NOT NULL,
    notes          TEXT,
    UNIQUE (provider, metric, asset, venue, event_time, available_at, payload_hash)
);
CREATE INDEX IF NOT EXISTS ix_obs_pit ON observations (metric, asset, venue, available_at);
"""


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime yasak (CLAUDE.md kural 7)")
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def payload_hash(obs: RawObservation) -> str:
    """Gözlemin içerik parmak izi: aynı içerik → aynı hash (revizyon tespiti)."""
    payload = {
        "asset": obs.asset,
        "event_time": _iso(obs.timestamp_utc),
        "metric": obs.metric,
        "quality": obs.quality,
        "raw_value": obs.raw_value,
        "unit": obs.unit,
        "venue": obs.venue,
        "window": obs.window,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class PointInTimeStore:
    """Append-only PIT deposu. `path=None` → bellek içi (test)."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path) if self.path else ":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PointInTimeStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def append(self, observations: Iterable[RawObservation], *, provider: str) -> int:
        """Gözlemleri yaz; yazılan satır sayısını döndür.

        Aynı (provider, metrik, varlık, venue, event_time, available_at, payload_hash)
        beşlisi tekrar gelirse sessizce atlanır — idempotent yeniden çekim. İçerik
        değişmişse (payload_hash farklı) YENİ satır yazılır: revizyon kaydı.
        """
        ingested_at = _iso(datetime.now(UTC))
        rows = []
        for obs in observations:
            rows.append(
                (
                    _iso(obs.timestamp_utc),
                    _iso(obs.effective_available_at),
                    ingested_at,
                    provider,
                    SCHEMA_VERSION,
                    payload_hash(obs),
                    obs.asset,
                    obs.venue,
                    obs.metric,
                    obs.raw_value,
                    obs.unit,
                    obs.window,
                    obs.source_group,
                    obs.source_url,
                    obs.quality,
                    obs.notes,
                )
            )
        cur = self._conn.executemany(
            """
            INSERT OR IGNORE INTO observations
                (event_time, available_at, ingested_at, provider, schema_version, payload_hash,
                 asset, venue, metric, raw_value, unit, window, source_group, source_url,
                 quality, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        self._conn.commit()
        return cur.rowcount

    def read_as_of(
        self,
        as_of: datetime,
        *,
        metrics: Sequence[str] | None = None,
        asset: str | None = None,
    ) -> list[dict]:
        """`as_of` anında bilinebilen EN GÜNCEL gözlemler (metrik/varlık/venue başına bir satır).

        `available_at > as_of` olan hiçbir satır dönmez — look-ahead'i depo katmanında
        imkânsız kılar. Sonuç deterministik sırada döner (metric, asset, venue).
        """
        cutoff = _iso(as_of)
        sql = """
            SELECT * FROM observations o
            WHERE o.available_at <= :cutoff
              AND o.id = (
                  SELECT i.id FROM observations i
                  WHERE i.metric = o.metric AND i.asset = o.asset AND i.venue = o.venue
                    AND i.available_at <= :cutoff
                  ORDER BY i.event_time DESC, i.available_at DESC, i.id DESC
                  LIMIT 1
              )
        """
        params: dict[str, object] = {"cutoff": cutoff}
        if metrics:
            placeholders = ",".join(f":m{i}" for i in range(len(metrics)))
            sql += f" AND o.metric IN ({placeholders})"
            params.update({f"m{i}": m for i, m in enumerate(metrics)})
        if asset:
            sql += " AND o.asset = :asset"
            params["asset"] = asset
        sql += " ORDER BY o.metric ASC, o.asset ASC, o.venue ASC"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def revision_history(self, *, metric: str, asset: str, venue: str, event_time: datetime
                         ) -> list[dict]:
        """Aynı olay anı için kaydedilmiş tüm sürümler (Historical Revision Delta girdisi)."""
        rows = self._conn.execute(
            """
            SELECT * FROM observations
            WHERE metric = ? AND asset = ? AND venue = ? AND event_time = ?
            ORDER BY available_at ASC, id ASC
            """,
            (metric, asset, venue, _iso(event_time)),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
