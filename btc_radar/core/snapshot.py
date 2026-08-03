"""Snapshot üretimi ve değişmez saklama — CR-002 P0-1.

Akış: PIT deposundan `available_at <= as_of` satırları oku → bileşenlere çevir
(`component_builder`, Faz 1'de signal_rules.yaml'dan üretilecek) → SPEC §5.1
aritmetiğiyle skorla → değişmez kayıt yaz.

DEĞİŞMEZLİK: aynı `snapshot_id` farklı içerikle yeniden yazılamaz. `snapshot_id`
girdilerin (as_of, versiyonlar, weights hash, PIT satırları) deterministik türevidir;
dolayısıyla aynı girdi → aynı id → çakışma denetimi gerçek bir koruma sağlar.

`computed_at` bilinçli olarak içerik hash'inin DIŞINDADIR: duvar saati replay'de
değişir, skor değişmez.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from btc_radar.core.scoring import ScoreComponent, aggregate
from btc_radar.models.config import WeightsConfig
from btc_radar.models.snapshot import RegimeSnapshot

FEATURE_VERSION = "0.1.0"
SCORING_VERSION = "0.1.0"

ComponentBuilder = Callable[[list[dict], datetime], list[ScoreComponent]]

_DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id     TEXT PRIMARY KEY,
    as_of           TEXT NOT NULL,
    data_cutoff_at  TEXT NOT NULL,
    computed_at     TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    payload         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_snap_as_of ON snapshots (as_of);
"""


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _sha(obj: object) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def input_digest(rows: list[dict]) -> str:
    """Kullanılan PIT satırlarının deterministik parmak izi.

    `ingested_at` ve `id` HARİÇ tutulur: aynı veriyi farklı zamanda yeniden yazan bir
    depo kopyası aynı digest'i üretmelidir (veri aynıysa skor da aynıdır).
    """
    trimmed = [
        {k: v for k, v in sorted(r.items()) if k not in ("id", "ingested_at")} for r in rows
    ]
    return _sha(trimmed)


def freshness(
    *, as_of: datetime, event_time: datetime, expected_period_seconds: float, stale_multiple: float
) -> float:
    """f katsayısı (SPEC §3.3): veri yaşı / beklenen periyot.

    Periyot içinde 1.0; sonra doğrusal azalarak `stale_multiple × periyot`ta 0.
    Eğim parametresi config'den gelir (weights.yaml → freshness.stale_multiple);
    koda eşik gömülmez (CLAUDE.md kural 3). Gelecek tarihli veri hatadır.
    """
    if expected_period_seconds <= 0:
        raise ValueError("expected_period_seconds > 0 olmalı")
    if stale_multiple <= 1.0:
        raise ValueError("stale_multiple > 1.0 olmalı")
    age = (as_of - event_time).total_seconds()
    if age < 0:
        raise ValueError(
            f"gelecekten veri: event_time {event_time.isoformat()} > as_of {as_of.isoformat()}"
        )
    if age <= expected_period_seconds:
        return 1.0
    span = expected_period_seconds * (stale_multiple - 1.0)
    return max(0.0, round(1.0 - (age - expected_period_seconds) / span, 6))


def _identity(
    *, as_of: datetime, weights_hash: str, digest: str, feature_version: str, scoring_version: str
) -> dict:
    return {
        "as_of": as_of.astimezone(UTC).isoformat(timespec="microseconds"),
        "feature_version": feature_version,
        "scoring_version": scoring_version,
        "weights_hash": weights_hash,
        "input_digest": digest,
    }


def content_hash_of(snap: RegimeSnapshot) -> str:
    """Snapshot gövdesinden içerik hash'ini YENİDEN hesaplar.

    Depo, nesnenin taşıdığı `content_hash` alanına güvenmez; her yazımda bunu doğrular.
    Aksi halde alanı elle değiştirilmiş bir kayıt "aynı içerik" sanılıp sessizce geçerdi
    (bu testle yakalanan gerçek açık).
    """
    body = {
        **_identity(
            as_of=snap.as_of,
            weights_hash=snap.weights_hash,
            digest=snap.input_digest,
            feature_version=snap.feature_version,
            scoring_version=snap.scoring_version,
        ),
        "snapshot_id": snap.snapshot_id,
        "direction": snap.direction,
        "fragility": snap.fragility,
        "confidence": snap.confidence,
        "regime_label": snap.regime_label,
        "stale_sources": sorted(snap.stale_sources),
        "missing_layers": snap.missing_layers,
        "breakdown": snap.breakdown,
    }
    return _sha(body)


def compute_snapshot(
    rows: list[dict],
    *,
    as_of: datetime,
    weights: WeightsConfig,
    weights_hash: str,
    component_builder: ComponentBuilder,
    stale_sources: list[str] | None = None,
    computed_at: datetime | None = None,
) -> RegimeSnapshot:
    """PIT satırlarından değişmez snapshot üretir. Saf: I/O yok (computed_at hariç)."""
    if as_of.tzinfo is None:
        raise ValueError("as_of timezone-aware olmalı")
    components = component_builder(rows, as_of)
    scores = aggregate(components, weights)
    digest = input_digest(rows)

    identity = _identity(
        as_of=as_of,
        weights_hash=weights_hash,
        digest=digest,
        feature_version=FEATURE_VERSION,
        scoring_version=SCORING_VERSION,
    )
    snapshot_id = "SNAP-" + _sha(identity)[:16]

    snap = RegimeSnapshot(
        snapshot_id=snapshot_id,
        as_of=as_of,
        data_cutoff_at=as_of,
        computed_at=computed_at or datetime.now(UTC),
        direction=scores.direction,
        fragility=scores.fragility,
        confidence=scores.confidence,
        regime_label=scores.regime_label,
        feature_version=FEATURE_VERSION,
        scoring_version=SCORING_VERSION,
        weights_hash=weights_hash,
        input_digest=digest,
        content_hash="",  # bir sonraki satırda gövdeden türetilir
        stale_sources=sorted(stale_sources or []),
        missing_layers=scores.missing_layers,
        breakdown=scores.breakdown,
    )
    return snap.model_copy(update={"content_hash": content_hash_of(snap)})


class SnapshotStore:
    """Değişmez snapshot deposu. Aynı id + farklı içerik → hata."""

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

    def __enter__(self) -> "SnapshotStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def put(self, snap: RegimeSnapshot) -> bool:
        """Yaz. Zaten aynı içerikle varsa False döner (idempotent); çelişkide hata.

        Gelen kaydın `content_hash` alanına GÜVENİLMEZ — gövdeden yeniden hesaplanıp
        doğrulanır; uyuşmazlık kurcalanmış/bozulmuş kayıt demektir ve yazma reddedilir.
        """
        actual = content_hash_of(snap)
        if actual != snap.content_hash:
            raise ValueError(
                f"İÇERİK HASH UYUŞMUYOR: {snap.snapshot_id} gövdesi taşıdığı hash ile "
                f"tutarsız (beklenen {actual[:12]}, taşınan {snap.content_hash[:12]}) — "
                "kayıt kurcalanmış ya da bozulmuş olabilir"
            )
        existing = self._conn.execute(
            "SELECT content_hash FROM snapshots WHERE snapshot_id = ?", (snap.snapshot_id,)
        ).fetchone()
        if existing:
            if existing["content_hash"] != snap.content_hash:
                raise ValueError(
                    f"DEĞİŞMEZLİK İHLALİ: {snap.snapshot_id} farklı içerikle yeniden yazılamaz "
                    f"(mevcut {existing['content_hash'][:12]}, gelen {snap.content_hash[:12]})"
                )
            return False
        self._conn.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?)",
            (
                snap.snapshot_id,
                snap.as_of.isoformat(timespec="microseconds"),
                snap.data_cutoff_at.isoformat(timespec="microseconds"),
                snap.computed_at.isoformat(timespec="microseconds"),
                snap.content_hash,
                snap.model_dump_json(),
            ),
        )
        self._conn.commit()
        return True

    def get(self, snapshot_id: str) -> RegimeSnapshot | None:
        row = self._conn.execute(
            "SELECT payload FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        return RegimeSnapshot.model_validate_json(row["payload"]) if row else None

    def get_as_of(self, as_of: datetime) -> RegimeSnapshot | None:
        """Tam o karar anının snapshot'ı. 'latest' sorgusu bilinçli olarak YOKTUR."""
        row = self._conn.execute(
            "SELECT payload FROM snapshots WHERE as_of = ? ORDER BY computed_at DESC LIMIT 1",
            (as_of.astimezone(UTC).isoformat(timespec="microseconds"),),
        ).fetchone()
        return RegimeSnapshot.model_validate_json(row["payload"]) if row else None

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])
