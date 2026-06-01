"""
Test dell'astrazione di canale (PR A omnicanale). Niente rete: Supabase e
l'adapter WhatsApp sono mockati. Coperture:
  - deliver_to_patient su canale whatsapp risolve il telefono e invia
  - errore se manca il telefono
  - errore su canale non supportato
  - errore su input mancante
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import channels  # noqa: E402

PAZIENTE_ID = "11111111-1111-4111-8111-111111111111"
MEDICO_ID = "22222222-2222-4222-8222-222222222222"


def test_deliver_whatsapp_resolves_phone_and_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        channels, "_resolve_patient_phone", MagicMock(return_value="+393331112222")
    )
    mock_send = MagicMock()
    monkeypatch.setattr(channels, "_send_whatsapp_reply_and_log", mock_send)

    out = channels.deliver_to_patient(
        PAZIENTE_ID, "Ciao, come stai?", medico_id=MEDICO_ID, channel="whatsapp"
    )

    assert out == {"status": "ok", "channel": "whatsapp"}
    mock_send.assert_called_once()
    kw = mock_send.call_args.kwargs
    assert kw["to_number"] == "+393331112222"
    assert kw["paziente_id"] == PAZIENTE_ID
    assert kw["medico_id"] == MEDICO_ID


def test_deliver_whatsapp_no_phone_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channels, "_resolve_patient_phone", MagicMock(return_value=None))
    mock_send = MagicMock()
    monkeypatch.setattr(channels, "_send_whatsapp_reply_and_log", mock_send)

    out = channels.deliver_to_patient(PAZIENTE_ID, "testo", channel="whatsapp")
    assert out["status"] == "error"
    assert out["reason"] == "telefono_mancante"
    mock_send.assert_not_called()


def test_deliver_unsupported_channel_errors() -> None:
    out = channels.deliver_to_patient(PAZIENTE_ID, "testo", channel="piccione")
    assert out["status"] == "error"
    assert "canale_non_supportato" in out["reason"]


def test_deliver_empty_input_errors() -> None:
    assert channels.deliver_to_patient("", "x")["reason"] == "input_mancante"
    assert channels.deliver_to_patient(PAZIENTE_ID, "  ")["reason"] == "input_mancante"


def test_deliver_default_channel_is_whatsapp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        channels, "_resolve_patient_phone", MagicMock(return_value="+39333")
    )
    monkeypatch.setattr(channels, "_send_whatsapp_reply_and_log", MagicMock())
    # channel non passato -> usa DEFAULT_CHANNEL (whatsapp)
    out = channels.deliver_to_patient(PAZIENTE_ID, "testo")
    assert out == {"status": "ok", "channel": "whatsapp"}
