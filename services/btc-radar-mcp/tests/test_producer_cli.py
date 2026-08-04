import json
from datetime import UTC, datetime

import pytest

from btc_radar.producer import _parse_as_of, main


def test_parse_as_of_requires_exact_utc_hour():
    assert _parse_as_of("2026-08-03T12:00:00Z") == datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    with pytest.raises(Exception, match="1h sınırı"):
        _parse_as_of("2026-08-03T12:15:00Z")


def test_publish_cli_creates_fail_closed_artifact(tmp_path, capsys):
    pit = tmp_path / "pit.sqlite"
    snapshots = tmp_path / "snapshots.sqlite"
    context_root = tmp_path / "context"

    main(
        [
            "publish",
            "--as-of",
            "2026-08-03T12:00:00Z",
            "--pit-db",
            str(pit),
            "--snapshot-db",
            str(snapshots),
            "--context-root",
            str(context_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "created"
    assert payload["rows_considered"] == 0
    assert payload["directional_decision_allowed"] is False
    assert payload["direction"] is None
    assert (context_root / "v1/BTCUSDT/1h/2026/08/03/12.json").is_file()


def test_publish_cli_requires_context_root(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "publish",
                "--as-of",
                "2026-08-03T12:00:00Z",
                "--pit-db",
                str(tmp_path / "pit.sqlite"),
                "--snapshot-db",
                str(tmp_path / "snapshots.sqlite"),
            ]
        )
