"""
Test di regressione per le fondamenta del PR #1 (idempotenza + log conversazionale).

Non tocca rete/DB reali: tutto monkeypatchato. Usa fastapi.testclient.TestClient
per simulare i POST Twilio sul webhook.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Permette di lanciare `pytest tests/ -v` dalla root del repo.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


PAZIENTE_ID = "11111111-1111-4111-8111-111111111111"
MEDICO_ID = "22222222-2222-4222-8222-222222222222"
ATTIVAZIONE_UUID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """
    Fixture base con tutti i monkeypatch richiesti dalla spec.
    I singoli test possono sovrascrivere `side_effect` / `return_value`.
    """
    monkeypatch.setattr(main, "supabase", MagicMock(name="supabase_mock"))
    monkeypatch.setattr(main, "openai_client", None)

    monkeypatch.setattr(main, "_claim_message_sid", MagicMock(return_value=True))
    monkeypatch.setattr(
        main,
        "get_paziente_by_phone",
        MagicMock(return_value=(PAZIENTE_ID, MEDICO_ID, None)),
    )
    monkeypatch.setattr(
        main,
        "fetch_paziente_if_exists",
        MagicMock(return_value=(PAZIENTE_ID, MEDICO_ID, True)),
    )
    monkeypatch.setattr(
        main,
        "extract_fields_with_openai",
        MagicMock(
            return_value={
                "sintesi_medica": "Cefalea",
                "sintomi_chiave": ["mal di testa"],
                "farmaci_citati": [],
                "red_flags": [],
                "is_richiesta_ricetta": False,
                "livello_urgenza": "VERDE",
                "riassunto_clinico": "Cefalea",
                "urgenza_db": "VERDE",
            }
        ),
    )
    monkeypatch.setattr(main, "insert_richiesta", MagicMock(return_value=None))
    monkeypatch.setattr(main, "_log_conversation_turn", MagicMock(return_value=None))
    monkeypatch.setattr(main, "_send_whatsapp_reply_and_log", MagicMock(return_value=None))
    monkeypatch.setattr(main, "_send_whatsapp_template_and_log", MagicMock(return_value=None))
    monkeypatch.setattr(
        main, "_enqueue_process_message_job", MagicMock(return_value=True)
    )
    monkeypatch.setattr(main, "process_message", MagicMock(return_value=None))

    monkeypatch.setattr(main, "_medico_exists", MagicMock(return_value=True))
    monkeypatch.setattr(
        main,
        "link_paziente_to_medico",
        MagicMock(return_value=(PAZIENTE_ID, MEDICO_ID, False)),
    )
    monkeypatch.setattr(
        main,
        "_update_paziente_name_if_allowed",
        MagicMock(return_value=False),
    )

    return TestClient(main.app)


def _user_logged_with_role_user(call_args_list) -> bool:
    """True se almeno una chiamata a _log_conversation_turn ha role='user'."""
    for call in call_args_list:
        kwargs = call.kwargs
        if kwargs.get("role") == "user":
            return True
        args = call.args
        if len(args) >= 3 and args[2] == "user":
            return True
    return False


def test_happy_path_enqueues_and_logs_user(client: TestClient) -> None:
    """
    Test 1 — happy path (PR #2 architecture): paziente esistente, GDPR accettato.
    Il webhook NON elabora piu' in sincrono: deve loggare il turno user
    e accodare un job per il worker. `process_message` (sync) NON deve essere
    chiamato finche' l'enqueue va a buon fine.
    """
    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+393331234567",
            "Body": "Ho mal di testa",
            "MessageSid": "SM_OK_001",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    assert main._enqueue_process_message_job.call_count == 1
    assert main.process_message.call_count == 0
    assert main._log_conversation_turn.call_count >= 1
    assert _user_logged_with_role_user(main._log_conversation_turn.call_args_list)


def test_happy_path_falls_back_to_sync_when_enqueue_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test 1bis — fallback retrocompat: se l'enqueue fallisce (es. migrazione PR #2
    non ancora applicata), il webhook elabora in sincrono come PR #1.
    """
    monkeypatch.setattr(
        main, "_enqueue_process_message_job", MagicMock(return_value=False)
    )

    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+393331234567",
            "Body": "Ho mal di testa",
            "MessageSid": "SM_OK_002",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    assert main._enqueue_process_message_job.call_count == 1
    assert main.process_message.call_count == 1


def test_retry_duplicate_is_skipped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test 2 — retry duplicato: _claim_message_sid ritorna False.
    Il webhook deve uscire subito, senza insert e senza log.
    """
    monkeypatch.setattr(main, "_claim_message_sid", MagicMock(return_value=False))

    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+393331234567",
            "Body": "Ho mal di testa",
            "MessageSid": "SM_OK_001",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    assert main._enqueue_process_message_job.call_count == 0
    assert main.process_message.call_count == 0
    assert main._log_conversation_turn.call_count == 0


def test_onboarding_activation_sends_gdpr_template_and_logs_user(
    client: TestClient,
) -> None:
    """
    Test 3 — onboarding: comando attivazione su numero nuovo, GDPR non ancora
    accettato. Il webhook deve inviare il template GDPR e loggare l'attivazione
    come turno user.
    """
    response = client.post(
        "/webhook",
        data={
            "From": "whatsapp:+393331234567",
            "Body": f"attivazione {ATTIVAZIONE_UUID}",
            "MessageSid": "SM_ACT_001",
            "NumMedia": "0",
        },
    )

    assert response.status_code == 200
    assert main._send_whatsapp_template_and_log.call_count == 1
    template_call = main._send_whatsapp_template_and_log.call_args
    assert (
        template_call.kwargs.get("template_sid")
        == main.GDPR_CONSENT_WHATSAPP_TEMPLATE_SID
    )

    assert main._log_conversation_turn.call_count >= 1
    assert _user_logged_with_role_user(main._log_conversation_turn.call_args_list)

    assert main.insert_richiesta.call_count == 0
    assert main._enqueue_process_message_job.call_count == 0
    assert main.process_message.call_count == 0
