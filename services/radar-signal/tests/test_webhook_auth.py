from datetime import UTC, datetime, timedelta

import pytest

from enricher.webhook_auth import (
    NonceStore,
    parse_request_time,
    require_fresh,
    signature_for,
    verify_signature,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def test_signature_binds_timestamp_nonce_and_exact_body():
    body = b'{"signal":"one"}'
    signature = signature_for(
        secret="secret",
        timestamp="1785921600",
        nonce="nonce-0000000001",
        body=body,
    )
    assert verify_signature(
        secret="secret",
        timestamp="1785921600",
        nonce="nonce-0000000001",
        body=body,
        supplied=signature,
    )
    assert not verify_signature(
        secret="secret",
        timestamp="1785921600",
        nonce="nonce-0000000001",
        body=body + b" ",
        supplied=signature,
    )


def test_nonce_reservation_is_durable_and_atomic(tmp_path):
    path = tmp_path / "nonces.sqlite"
    with NonceStore(path) as store:
        assert store.reserve(
            nonce="nonce-0000000001",
            request_time=NOW,
            accepted_at=NOW,
            retention_seconds=900,
        )
    with NonceStore(path) as restarted:
        assert not restarted.reserve(
            nonce="nonce-0000000001",
            request_time=NOW,
            accepted_at=NOW + timedelta(seconds=1),
            retention_seconds=900,
        )


def test_expired_nonce_can_be_pruned_and_reused(tmp_path):
    with NonceStore(tmp_path / "nonces.sqlite") as store:
        assert store.reserve(
            nonce="nonce-0000000001",
            request_time=NOW,
            accepted_at=NOW,
            retention_seconds=10,
        )
        assert store.reserve(
            nonce="nonce-0000000001",
            request_time=NOW + timedelta(seconds=11),
            accepted_at=NOW + timedelta(seconds=11),
            retention_seconds=10,
        )


def test_timestamp_and_clock_validation_fail_closed():
    with pytest.raises(ValueError, match="10 haneli"):
        parse_request_time("not-a-time")
    with pytest.raises(ValueError, match="saat penceresi"):
        require_fresh(
            request_time=NOW - timedelta(seconds=301),
            now=NOW,
            max_clock_skew_seconds=300,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        require_fresh(
            request_time=NOW,
            now=datetime(2026, 8, 5, 12, 0),
            max_clock_skew_seconds=300,
        )


def test_lifecycle_rejects_non_positive_auth_thresholds(tmp_path):
    from enricher.policy import LIFECYCLE_PATH, load_lifecycle

    content = LIFECYCLE_PATH.read_text(encoding="utf-8").replace(
        "max_clock_skew_seconds: 300", "max_clock_skew_seconds: 0"
    )
    path = tmp_path / "lifecycle.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="positive|pozitif"):
        load_lifecycle(path)
