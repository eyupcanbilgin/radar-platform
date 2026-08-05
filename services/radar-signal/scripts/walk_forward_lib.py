"""Purged Walk-Forward + Embargo Ölçüm ve Split Protokolü — Lib Modülü.

Faz 2 araştırma protokolünün temel ilkeleri:
1. Zamanlar her zaman UTC ve timezone-aware olmak zorundadır. Naive timestamp fail-loud.
2. Locked OOS (varsayılan: 2026-08-04T00:00:00Z) dönemi varsayılan olarak kapalıdır; erişim isteği
   `LockedOOSAccessError` üretir.
3. Purge: Forward horizon (örn. 24 saat) nedeniyle train kümesinin sonunda test/embargo dönemine
   sızan örnekler `train_purged_end_utc` ile train kümesinden çıkarılır.
4. Embargo: Train penceresi sonu ile Test penceresi başı arasında en az `min_embargo_days` (1 gün)
   tampon boşluk bırakılır.
5. Boş, yetersiz veya boşluklu veri pencereleri "0/nötr getiri" sayılmaz; `unavailable` veya
   `invalid` olarak işaretlenir.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from scripts.datapaths import SERVICE_ROOT

CONFIG_PATH = SERVICE_ROOT / "config" / "research_protocol.yaml"


class LockedOOSAccessError(Exception):
    """Locked Out-Of-Sample dönemine izinsiz erişim denemesi."""

    pass


class ProtocolValidationError(Exception):
    """Protokol, konfigürasyon veya zaman damgası ihlali."""

    pass


def parse_utc_datetime(dt_val: datetime | str) -> datetime:
    """Verilen datetime veya ISO string'i timezone-aware UTC datetime olarak doğrular/dönüştürür.

    Naive timestamp verilirse fail-loud `ProtocolValidationError` fırlatır.
    """
    if isinstance(dt_val, str):
        # YYYY-MM-DD formatında verilmişse gün sonu/başı varsayımı yapmadan Z ekle
        val = dt_val.strip()
        if len(val) == 10 and val.count("-") == 2:
            val += "T00:00:00Z"
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(val)
        except ValueError as err:
            raise ProtocolValidationError(f"Geçersiz ISO tarih formatı: '{dt_val}'") from err
    elif isinstance(dt_val, datetime):
        dt = dt_val
    else:
        raise ProtocolValidationError(f"Beklenen datetime veya ISO str, alınan: {type(dt_val)}")

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ProtocolValidationError(f"Naive (timezone-unaware) zaman damgası yasaktır: {dt_val}")

    # Always normalize to UTC timezone
    return dt.astimezone(UTC)


def load_research_protocol_config(config_path: Path | None = None) -> dict:
    """`research_protocol.yaml` dosyasını okur ve şema doğrulaması yapar."""
    path = config_path or CONFIG_PATH
    if not path.exists():
        raise ProtocolValidationError(f"Protokol konfigürasyon dosyası bulunamadı: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as err:
        raise ProtocolValidationError(f"Konfigürasyon YAML parse hatası: {err}") from err

    if not isinstance(data, dict):
        raise ProtocolValidationError("Konfigürasyon kök elemanı dict olmalıdır.")

    if data.get("version") != "1.0":
        raise ProtocolValidationError(f"Desteklenmeyen konfigürasyon sürümü: {data.get('version')}")

    for req_sec in ["boundaries", "walk_forward", "data_integrity", "locked_oos", "baselines"]:
        if req_sec not in data:
            raise ProtocolValidationError(f"Konfigürasyonda zorunlu bölüm eksik: '{req_sec}'")

    wf = data["walk_forward"]
    if wf.get("min_embargo_days", 0) < 1:
        raise ProtocolValidationError("min_embargo_days 1 günden az olamaz (fail-closed).")

    # Locked OOS tarihini doğrula
    locked_str = data["boundaries"].get("locked_oos_start_utc")
    if not locked_str:
        raise ProtocolValidationError("locked_oos_start_utc konfigürasyonda eksik.")
    data["boundaries"]["locked_oos_start_dt"] = parse_utc_datetime(locked_str)

    return data


def generate_walk_forward_plan(
    start_time: datetime | str,
    end_time: datetime | str,
    horizon_hours: int | None = None,
    embargo_days: int | None = None,
    train_window_days: int | None = None,
    test_window_days: int | None = None,
    step_days: int | None = None,
    allow_locked_oos: bool = False,
    config: dict | None = None,
) -> dict:
    """Purged walk-forward + embargo split planını deterministik olarak hesaplar."""
    cfg = config or load_research_protocol_config()
    wf_cfg = cfg["walk_forward"]

    start_dt = parse_utc_datetime(start_time)
    end_dt = parse_utc_datetime(end_time)

    if start_dt >= end_dt:
        raise ProtocolValidationError("Baslangic tarihi bitis tarihinden önce olmalidir.")

    h_hours = horizon_hours if horizon_hours is not None else wf_cfg["default_label_horizon_hours"]
    e_days = embargo_days if embargo_days is not None else wf_cfg["default_embargo_days"]
    tr_days = train_window_days if train_window_days is not None else wf_cfg["train_window_days"]
    te_days = test_window_days if test_window_days is not None else wf_cfg["test_window_days"]
    s_days = step_days if step_days is not None else wf_cfg["step_days"]

    if e_days < wf_cfg["min_embargo_days"]:
        raise ProtocolValidationError(
            f"Embargo süresi ({e_days} gün) konfigürasyondaki minimum eşikten "
            f"({wf_cfg['min_embargo_days']} gün) küçük olamaz."
        )

    if h_hours < 0 or tr_days <= 0 or te_days <= 0 or s_days <= 0:
        raise ProtocolValidationError("Horizon, pencere ve adım parametreleri pozitif olmalıdır.")

    locked_start_dt = cfg["boundaries"]["locked_oos_start_dt"]

    # Locked OOS kontrolü (end_time locked_oos sınırına veya ötesine erişiyorsa)
    if end_dt > locked_start_dt and not allow_locked_oos:
        raise LockedOOSAccessError(
            f"Talep edilen bitiş tarihi ({end_dt.isoformat()}), locked OOS "
            f"sınırını ({locked_start_dt.isoformat()}) aşıyor. "
            "Locked OOS varsayılan olarak kapalıdır."
        )

    folds = []
    fold_idx = 0
    curr_train_start = start_dt

    while True:
        train_raw_end = curr_train_start + timedelta(days=tr_days)
        embargo_start = train_raw_end
        embargo_end = embargo_start + timedelta(days=e_days)
        test_start = embargo_end
        test_end = test_start + timedelta(days=te_days)

        if test_end > end_dt:
            break

        # Check fold access to locked OOS
        if test_end > locked_start_dt and not allow_locked_oos:
            raise LockedOOSAccessError(
                f"Fold #{fold_idx} test bitişi ({test_end.isoformat()}), locked OOS "
                f"sınırını ({locked_start_dt.isoformat()}) aşıyor."
            )

        # Purging calculation: train setindeki örneklerin label horizon'ı
        # train_raw_end'i (veya embargo_start'ı) aşıyorsa train setinden düşürülür.
        train_purged_end = train_raw_end - timedelta(hours=h_hours)

        if train_purged_end <= curr_train_start:
            status = "invalid"
            reason = "Purged train window empty or zero duration."
        else:
            status = "valid"
            reason = None

        fold_data = {
            "fold_index": fold_idx,
            "train_start_utc": curr_train_start.isoformat().replace("+00:00", "Z"),
            "train_raw_end_utc": train_raw_end.isoformat().replace("+00:00", "Z"),
            "train_purged_end_utc": train_purged_end.isoformat().replace("+00:00", "Z"),
            "embargo_start_utc": embargo_start.isoformat().replace("+00:00", "Z"),
            "embargo_end_utc": embargo_end.isoformat().replace("+00:00", "Z"),
            "test_start_utc": test_start.isoformat().replace("+00:00", "Z"),
            "test_end_utc": test_end.isoformat().replace("+00:00", "Z"),
            "purged_hours": h_hours,
            "embargo_hours": e_days * 24,
            "status": status,
        }
        if reason:
            fold_data["reason"] = reason

        folds.append(fold_data)

        fold_idx += 1
        curr_train_start = curr_train_start + timedelta(days=s_days)

    if not folds:
        raise ProtocolValidationError(
            "Belirtilen tarih aralığı ve pencere boyutlarıyla geçerli fold üretilemedi."
        )

    return {
        "protocol_version": cfg["version"],
        "parameters": {
            "start_time_utc": start_dt.isoformat().replace("+00:00", "Z"),
            "end_time_utc": end_dt.isoformat().replace("+00:00", "Z"),
            "horizon_hours": h_hours,
            "embargo_days": e_days,
            "train_window_days": tr_days,
            "test_window_days": te_days,
            "step_days": s_days,
            "allow_locked_oos": allow_locked_oos,
        },
        "folds": folds,
    }


def validate_split_plan(plan: dict, config: dict | None = None) -> bool:
    """Split planı nesnesini sözleşmeye, UTC kurallarına ve purge/embargo
    bütünlüğüne göre doğrular.
    """
    cfg = config or load_research_protocol_config()
    wf_cfg = cfg["walk_forward"]
    locked_start_dt = cfg["boundaries"]["locked_oos_start_dt"]

    if not isinstance(plan, dict):
        raise ProtocolValidationError("Plan bir dict olmalıdır.")

    if plan.get("protocol_version") != cfg["version"]:
        raise ProtocolValidationError(
            f"Plan protokol sürümü uyumsuz: {plan.get('protocol_version')}"
        )

    params = plan.get("parameters", {})
    allow_locked_oos = bool(params.get("allow_locked_oos", False))
    embargo_days = params.get("embargo_days", 0)

    if embargo_days < wf_cfg["min_embargo_days"]:
        raise ProtocolValidationError(
            f"Plan embargosu ({embargo_days}) minimum eşikten ({wf_cfg['min_embargo_days']}) düşük."
        )

    folds = plan.get("folds", [])
    if not folds:
        raise ProtocolValidationError("Planda hiç fold yok.")

    for fold in folds:
        tr_start = parse_utc_datetime(fold["train_start_utc"])
        tr_raw_end = parse_utc_datetime(fold["train_raw_end_utc"])
        tr_purged_end = parse_utc_datetime(fold["train_purged_end_utc"])
        emb_start = parse_utc_datetime(fold["embargo_start_utc"])
        emb_end = parse_utc_datetime(fold["embargo_end_utc"])
        te_start = parse_utc_datetime(fold["test_start_utc"])
        te_end = parse_utc_datetime(fold["test_end_utc"])

        # Overlap & sequence checks
        if tr_start >= tr_purged_end:
            raise ProtocolValidationError(
                f"Fold #{fold['fold_index']}: train_start train_purged_end'den büyük veya eşit."
            )
        if tr_purged_end > tr_raw_end:
            raise ProtocolValidationError(
                f"Fold #{fold['fold_index']}: train_purged_end train_raw_end'den büyük."
            )

        if emb_start < tr_raw_end:
            raise ProtocolValidationError(
                f"Fold #{fold['fold_index']}: embargo train_raw_end'den önce başlıyor."
            )

        if te_start < emb_end:
            raise ProtocolValidationError(
                f"Fold #{fold['fold_index']}: test embargo bitişinden önce başlıyor (overlap!)."
            )

        if te_start <= tr_purged_end:
            raise ProtocolValidationError(
                f"Fold #{fold['fold_index']}: test penceresi purged train penceresi ile örtüşüyor!"
            )

        # Locked OOS check
        if te_end > locked_start_dt and not allow_locked_oos:
            raise LockedOOSAccessError(
                f"Fold #{fold['fold_index']}: test bitişi locked OOS sınırını ihlal ediyor."
            )

    return True


def evaluate_window_data(
    fold: dict,
    candles: list[dict] | None = None,
    config: dict | None = None,
) -> dict:
    """Fold penceresindeki verinin eksiksizliğini değerlendirir.

    Boş veya eksik veri asla '0 getiri' veya 'nötr' sayılmaz; 'unavailable' veya 'invalid'
    olarak raporlanır.
    """
    cfg = config or load_research_protocol_config()
    min_candles = cfg["data_integrity"]["min_candles_per_window"]
    max_gap_sec = cfg["data_integrity"]["max_allowed_gap_seconds"]

    res = dict(fold)

    if candles is None or len(candles) == 0:
        res["status"] = "unavailable"
        res["reason"] = "no_data_available"
        return res

    if len(candles) < min_candles:
        res["status"] = "invalid"
        res["reason"] = f"insufficient_candles:{len(candles)}<{min_candles}"
        return res

    # Gap check on candle timestamps if available
    prev_ts = None
    for c in candles:
        ts_val = c.get("timestamp") or c.get("date") or c.get("time")
        if ts_val is not None:
            if isinstance(ts_val, (int, float)):
                cur_dt = datetime.fromtimestamp(ts_val / 1000.0 if ts_val > 2e9 else ts_val, tz=UTC)
            else:
                cur_dt = parse_utc_datetime(ts_val)

            if prev_ts is not None:
                gap = (cur_dt - prev_ts).total_seconds()
                if gap > max_gap_sec:
                    res["status"] = "invalid"
                    res["reason"] = f"data_gap_exceeded:{gap}s>{max_gap_sec}s"
                    return res
            prev_ts = cur_dt

    res["status"] = "valid"
    res["candle_count"] = len(candles)
    return res
