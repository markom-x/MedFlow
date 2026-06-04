"""Regression: link_paziente_to_medico must succeed when Supabase update returns empty data."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_link_paziente_update_empty_data_still_returns_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDFLOW_SKIP_GDPR", "0")
    mock_sb = MagicMock(name="supabase")
    existing_resp = MagicMock()
    existing_resp.data = [{"id": "p1", "gdpr_consent": False}]
    update_resp = MagicMock()
    update_resp.data = None

    table = MagicMock()
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        existing_resp
    )
    table.update.return_value.eq.return_value.execute.return_value = update_resp
    mock_sb.table.return_value = table

    monkeypatch.setattr(main, "supabase", mock_sb)

    pid, mid, consent = main.link_paziente_to_medico(
        "+393331234567", "0aec5fee-921d-43bf-87b6-c4019182c742"
    )
    assert pid == "p1"
    assert mid == "0aec5fee-921d-43bf-87b6-c4019182c742"
    assert consent is False


def test_link_paziente_demo_mode_auto_consents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDFLOW_SKIP_GDPR", "1")
    mock_sb = MagicMock(name="supabase")
    existing_resp = MagicMock()
    existing_resp.data = [{"id": "p1", "gdpr_consent": False}]
    update_resp = MagicMock()
    update_resp.data = None

    table = MagicMock()
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
        existing_resp
    )
    table.update.return_value.eq.return_value.execute.return_value = update_resp
    mock_sb.table.return_value = table

    monkeypatch.setattr(main, "supabase", mock_sb)
    monkeypatch.setattr(main, "set_paziente_gdpr_consent", MagicMock(return_value=True))

    _pid, _mid, consent = main.link_paziente_to_medico(
        "+393331234567", "0aec5fee-921d-43bf-87b6-c4019182c742"
    )
    assert consent is True
    main.set_paziente_gdpr_consent.assert_called_once_with("p1", True)
