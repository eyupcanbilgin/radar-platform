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
import math
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from btc_radar.core.scoring import ScoreComponent, aggregate
from btc_radar.models.config import WeightsConfig
from btc_radar.models.snapshot import RegimeSnapshot

FEATURE_VERSION = "0.2.0"
SCORING_VERSION = "0.1.0"
LEGACY_CONTENT_HASH_FEATURE_VERSIONS = frozenset({"0.1.0"})

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
    trimmed = [{k: v for k, v in sorted(r.items()) if k not in ("id", "ingested_at")} for r in rows]
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
    # v0.1 hash sözleşmesi cutoff'u kapsamıyordu. Geçmiş immutable snapshot'lar replay
    # için okunabilir kalmalı; v0.2+ yeni sözleşme cutoff'u da bütünlüğe bağlar.
    if snap.feature_version not in LEGACY_CONTENT_HASH_FEATURE_VERSIONS:
        body["data_cutoff_at"] = snap.data_cutoff_at.astimezone(UTC).isoformat(
            timespec="microseconds"
        )
    return _sha(body)


def snapshot_id_of(snap: RegimeSnapshot) -> str:
    """Snapshot kimliğini taşınan ID'ye güvenmeden gövdeden yeniden türet."""
    identity = _identity(
        as_of=snap.as_of,
        weights_hash=snap.weights_hash,
        digest=snap.input_digest,
        feature_version=snap.feature_version,
        scoring_version=snap.scoring_version,
    )
    return "SNAP-" + _sha(identity)[:16]


def _is_lower_hex(value: str, *, min_length: int, max_length: int) -> bool:
    return (
        min_length <= len(value) <= max_length
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def _reject_non_finite(value: object, *, path: str) -> None:
    """Breakdown'u deterministik JSON alanıyla sınırla; NaN/Infinity'yi reddet."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"SNAPSHOT BÜTÜNLÜK HATASI: {path} sonlu sayı olmalı")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"SNAPSHOT BÜTÜNLÜK HATASI: {path} anahtarları string olmalı")
            _reject_non_finite(child, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_non_finite(child, path=f"{path}[{index}]")
        return
    raise ValueError(
        f"SNAPSHOT BÜTÜNLÜK HATASI: {path} JSON-uyumlu tür olmalı; {type(value).__name__} geldi"
    )


def verify_regime_snapshot(snap: RegimeSnapshot) -> None:
    """Kimlik, PIT sınırı ve içerik bütünlüğünü yeniden hesaplayarak doğrula.

    Producer ve depo okuma yolları bu fonksiyonu çağırır. Böylece geçerli görünen bir
    Pydantic nesnesi, eski/uydurma ``snapshot_id`` veya kurcalanmış hash ile yayınlanamaz.
    ``data_cutoff_at`` v0.2'den itibaren içerik hash'ine de dahildir.
    """
    as_of = snap.as_of.astimezone(UTC)
    if snap.data_cutoff_at != as_of:
        raise ValueError("SNAPSHOT BÜTÜNLÜK HATASI: data_cutoff_at tam olarak as_of olmalı")
    if snap.computed_at < as_of:
        raise ValueError("SNAPSHOT BÜTÜNLÜK HATASI: computed_at as_of öncesinde olamaz")
    if not _is_lower_hex(snap.weights_hash, min_length=12, max_length=64):
        raise ValueError("SNAPSHOT BÜTÜNLÜK HATASI: weights_hash küçük harf hex olmalı")
    if not _is_lower_hex(snap.input_digest, min_length=64, max_length=64):
        raise ValueError("SNAPSHOT BÜTÜNLÜK HATASI: input_digest 64 haneli küçük harf hex olmalı")
    if snap.stale_sources != sorted(set(snap.stale_sources)):
        raise ValueError("SNAPSHOT BÜTÜNLÜK HATASI: stale_sources sıralı ve tekil olmalı")
    if snap.missing_layers != sorted(set(snap.missing_layers)):
        raise ValueError("SNAPSHOT BÜTÜNLÜK HATASI: missing_layers sıralı ve tekil olmalı")
    _reject_non_finite(snap.breakdown, path="breakdown")

    expected_id = snapshot_id_of(snap)
    if snap.snapshot_id != expected_id:
        raise ValueError(
            f"SNAPSHOT KİMLİK UYUŞMUYOR: beklenen {expected_id}, taşınan {snap.snapshot_id}"
        )
    actual_hash = content_hash_of(snap)
    if snap.content_hash != actual_hash:
        raise ValueError(
            f"İÇERİK HASH UYUŞMUYOR: {snap.snapshot_id} gövdesi taşıdığı hash ile "
            f"tutarsız (beklenen {actual_hash[:12]}, taşınan {snap.content_hash[:12]}) — "
            "kayıt kurcalanmış ya da bozulmuş olabilir"
        )


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
        verify_regime_snapshot(snap)
        try:
            # SELECT→INSERT iki ayrı producer connection'ında yarışmamalı. SQLite
            # yazar kilidini seçimden önce al; bekleyen retry commit sonrası mevcut
            # satırı doğrulayıp idempotent False döner.
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self._conn.execute(
                "SELECT * FROM snapshots WHERE snapshot_id = ?", (snap.snapshot_id,)
            ).fetchone()
            if existing:
                stored = self._decode_row(existing, expected_snapshot_id=snap.snapshot_id)
                if stored.content_hash != snap.content_hash:
                    raise ValueError(
                        f"DEĞİŞMEZLİK İHLALİ: {snap.snapshot_id} farklı içerikle "
                        f"yeniden yazılamaz (mevcut {stored.content_hash[:12]}, "
                        f"gelen {snap.content_hash[:12]})"
                    )
                self._conn.commit()
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
        except Exception:
            self._conn.rollback()
            raise

    @staticmethod
    def _decode_row(
        row: sqlite3.Row,
        *,
        expected_snapshot_id: str | None = None,
        expected_as_of: datetime | None = None,
    ) -> RegimeSnapshot:
        snap = RegimeSnapshot.model_validate_json(row["payload"])
        verify_regime_snapshot(snap)
        if expected_snapshot_id is not None and snap.snapshot_id != expected_snapshot_id:
            raise ValueError(
                "SNAPSHOT DEPO TUTARSIZLIĞI: istenen/kolon snapshot_id payload ile uyuşmuyor"
            )
        if expected_as_of is not None and snap.as_of != expected_as_of:
            raise ValueError("SNAPSHOT DEPO TUTARSIZLIĞI: as_of kolonu payload ile uyuşmuyor")
        expected_columns = {
            "snapshot_id": snap.snapshot_id,
            "as_of": snap.as_of.isoformat(timespec="microseconds"),
            "data_cutoff_at": snap.data_cutoff_at.isoformat(timespec="microseconds"),
            "computed_at": snap.computed_at.isoformat(timespec="microseconds"),
            "content_hash": snap.content_hash,
        }
        for column, expected in expected_columns.items():
            if row[column] != expected:
                raise ValueError(
                    f"SNAPSHOT DEPO TUTARSIZLIĞI: {column} kolonu payload ile uyuşmuyor"
                )
        return snap

    def get(self, snapshot_id: str) -> RegimeSnapshot | None:
        row = self._conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if not row:
            return None
        return self._decode_row(row, expected_snapshot_id=snapshot_id)

    def get_as_of(self, as_of: datetime) -> RegimeSnapshot | None:
        """Tam karar anının tek snapshot'ı; birden fazlaysa örtük seçim yapma."""
        if as_of.tzinfo is None:
            raise ValueError("as_of timezone-aware olmalı")
        as_of = as_of.astimezone(UTC)
        rows = self._conn.execute(
            "SELECT * FROM snapshots WHERE as_of = ? ORDER BY snapshot_id ASC",
            (as_of.isoformat(timespec="microseconds"),),
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(
                "SNAPSHOT BELİRSİZLİĞİ: aynı as_of için birden fazla snapshot var; "
                "snapshot_id açıkça seçilmeli"
            )
        return self._decode_row(rows[0], expected_as_of=as_of)

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])
