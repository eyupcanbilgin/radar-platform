"""Fully synthetic tests for the operator delivery kill-switch.

No network, no `user_data/`, no live outbox: only files in `tmp_path`.
"""

from pathlib import Path

from decision_engine.delivery_pause import MAX_REASON_CHARS, read_pause_state


def test_no_switch_configured_means_no_pause():
    """Anahtar opt-in'dir; verilmediğinde varsayılan davranış değişmez."""
    state = read_pause_state(None)
    assert state.paused is False
    assert state.reason is None


def test_missing_file_means_running(tmp_path: Path):
    state = read_pause_state(tmp_path / "yok.pause")
    assert state.paused is False


def test_existence_alone_pauses_delivery(tmp_path: Path):
    """VARLIK sinyaldir: içerik ayrıştırılmaz, truthy/falsy yorumlanmaz."""
    switch = tmp_path / "delivery.pause"
    switch.write_text("", encoding="utf-8")

    state = read_pause_state(switch)

    assert state.paused is True
    assert state.reason is None


def test_content_travels_as_the_reason(tmp_path: Path):
    """ "Neden hiçbir şey gitmiyor?" sorusu hafızadan değil logdan cevaplanabilmeli."""
    switch = tmp_path / "delivery.pause"
    switch.write_text("  kart metni yanlış\n  operatör: eyupcan\n", encoding="utf-8")

    state = read_pause_state(switch)

    assert state.paused is True
    assert state.reason == "kart metni yanlış operatör: eyupcan"


def test_a_file_saying_false_still_pauses(tmp_path: Path):
    """Klasik tuzak: içeriğe bakan bir anahtar "false" yazınca çalışmaya devam ederdi."""
    switch = tmp_path / "delivery.pause"
    switch.write_text("false", encoding="utf-8")

    assert read_pause_state(switch).paused is True


def test_unreadable_file_resolves_to_paused(tmp_path: Path):
    """Bir durdurma kontrolünde belirsizlik DURMA yönünde çözülmelidir."""
    switch = tmp_path / "delivery.pause"
    switch.write_bytes(b"\xff\xfe gecersiz utf-8")

    state = read_pause_state(switch)

    assert state.paused is True
    assert "okunamadı" in (state.reason or "")


def test_long_reason_is_truncated(tmp_path: Path):
    switch = tmp_path / "delivery.pause"
    switch.write_text("x" * (MAX_REASON_CHARS * 3), encoding="utf-8")

    assert len(read_pause_state(switch).reason) == MAX_REASON_CHARS


def test_payload_is_reportable(tmp_path: Path):
    switch = tmp_path / "delivery.pause"
    switch.write_text("bakım", encoding="utf-8")

    assert read_pause_state(switch).as_payload() == {
        "delivery_paused": True,
        "pause_reason": "bakım",
    }


def test_lifting_the_switch_resumes(tmp_path: Path):
    """Duraklatma tutar, atmaz: anahtar kalkınca teslimat yeniden mümkün olur."""
    switch = tmp_path / "delivery.pause"
    switch.write_text("dur", encoding="utf-8")
    assert read_pause_state(switch).paused is True

    switch.unlink()

    assert read_pause_state(switch).paused is False
