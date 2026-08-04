from pathlib import Path

import pytest

from enricher.telegram import (
    ConsoleSender,
    DeliveryConfigurationError,
    NotConfigured,
    TelegramSender,
    load_env_file,
    sender_from_environment,
)


def test_delivery_mode_is_required_and_never_silently_falls_back():
    with pytest.raises(DeliveryConfigurationError, match="açıkça"):
        sender_from_environment(environ={})


@pytest.mark.parametrize(
    "environment",
    [
        {"RADAR_SIGNAL_DELIVERY_MODE": "telegram"},
        {"RADAR_SIGNAL_DELIVERY_MODE": "telegram", "TELEGRAM_BOT_TOKEN": "secret"},
        {"RADAR_SIGNAL_DELIVERY_MODE": "telegram", "TELEGRAM_CHAT_ID": "123"},
    ],
)
def test_telegram_mode_requires_both_credentials(environment):
    with pytest.raises(NotConfigured, match="eksik"):
        sender_from_environment(environ=environment)


def test_explicit_console_mode_needs_no_telegram_secret():
    assert isinstance(
        sender_from_environment(environ={"RADAR_SIGNAL_DELIVERY_MODE": "console"}),
        ConsoleSender,
    )


def test_explicit_telegram_mode_builds_configured_sender():
    sender = sender_from_environment(
        environ={
            "RADAR_SIGNAL_DELIVERY_MODE": "telegram",
            "TELEGRAM_BOT_TOKEN": "secret",
            "TELEGRAM_CHAT_ID": "123",
        }
    )
    assert isinstance(sender, TelegramSender)
    assert sender.configured is True


def test_env_file_loads_without_overriding_process_environment(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(
        "RADAR_SIGNAL_DELIVERY_MODE=telegram\n"
        "TELEGRAM_BOT_TOKEN=file-secret\n"
        'TELEGRAM_CHAT_ID="123"\n',
        encoding="utf-8",
    )
    environment = {"TELEGRAM_BOT_TOKEN": "process-secret"}
    load_env_file(path, environ=environment)
    assert environment == {
        "RADAR_SIGNAL_DELIVERY_MODE": "telegram",
        "TELEGRAM_BOT_TOKEN": "process-secret",
        "TELEGRAM_CHAT_ID": "123",
    }


def test_malformed_env_fails_without_exposing_values(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("not-an-assignment", encoding="utf-8")
    with pytest.raises(DeliveryConfigurationError, match="line=1") as error:
        load_env_file(path, environ={})
    assert "not-an-assignment" not in str(error.value)
