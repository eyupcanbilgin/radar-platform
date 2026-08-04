"""Single-instance guard: a second collector must not start silently."""

import json
from datetime import UTC, datetime

import pytest

from btc_radar.core.runlock import RunLockError, exclusive_run_lock

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def test_lock_is_created_with_owner_details_and_released_on_exit(tmp_path):
    lock_path = tmp_path / "run" / "producer.lock"

    with exclusive_run_lock(lock_path, now=NOW) as held:
        assert held == lock_path
        content = json.loads(lock_path.read_text(encoding="utf-8"))
        assert isinstance(content["pid"], int)
        assert content["acquired_at"] == "2026-08-04T12:00:00+00:00"

    assert not lock_path.exists()


def test_second_holder_is_refused_with_the_owner_in_the_message(tmp_path):
    lock_path = tmp_path / "producer.lock"

    with exclusive_run_lock(lock_path, now=NOW):
        with pytest.raises(RunLockError, match="pid="):
            with exclusive_run_lock(lock_path, now=NOW):
                pass


def test_lock_is_released_even_when_the_body_raises(tmp_path):
    lock_path = tmp_path / "producer.lock"

    with pytest.raises(RuntimeError, match="boom"):
        with exclusive_run_lock(lock_path, now=NOW):
            raise RuntimeError("boom")

    # Kilit temizlendi: çöken bir süreç sonraki başlatmayı kalıcı olarak engellememeli.
    with exclusive_run_lock(lock_path, now=NOW):
        assert lock_path.exists()


def test_an_unreadable_lock_still_refuses_instead_of_taking_over(tmp_path):
    lock_path = tmp_path / "producer.lock"
    lock_path.write_text("not json", encoding="utf-8")

    with pytest.raises(RunLockError, match="içerik okunamadı"):
        with exclusive_run_lock(lock_path, now=NOW):
            pass
