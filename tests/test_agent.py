"""
Test del LangGraph agent (PR #3). Niente rete/DB reali: ChatOpenAI e Supabase
sono mockati. I test coprono:

- routing in `route_after_input` (testo / audio / immagine / pdf)
- comportamento di `node_anamnesis_copilot` su decisione ask / finalize
- comportamento di `node_clinical_synthesizer` (genera synthesis dict)
- `load_session` / `save_session` / `load_recent_conversation` round-trip
- entry-point `run_for_job` end-to-end:
    * paziente non trovato -> error
    * ask -> reply inviata e stato salvato come COLLECTING_ANAMNESIS
    * finalize -> sintesi inserita in richieste, stato FINISHED
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import main  # noqa: E402
from agent import ClinicalSynthesis, CopilotDecision  # noqa: E402


PAZIENTE_ID = "11111111-1111-4111-8111-111111111111"
MEDICO_ID = "22222222-2222-4222-8222-222222222222"
PHONE = "+393331234567"


@pytest.fixture
def supa_mock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    sb = MagicMock(name="supabase_mock")
    monkeypatch.setattr(main, "supabase", sb)
    monkeypatch.setattr(agent, "supabase", sb)
    return sb


@pytest.fixture(autouse=True)
def reset_graph_singleton(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent, "_COMPILED_GRAPH", None)


# --------------------------- routing ---------------------------

def test_route_text_goes_to_copilot() -> None:
    state = {"incoming_media_url": "", "incoming_media_content_type": ""}
    assert agent.route_after_input(state) == "anamnesis_copilot"


def test_route_audio_goes_to_whisper() -> None:
    state = {
        "incoming_media_url": "https://twilio/media/xyz",
        "incoming_media_content_type": "audio/ogg",
    }
    assert agent.route_after_input(state) == "whisper_transcribe"


def test_route_image_goes_to_vision() -> None:
    state = {
        "incoming_media_url": "https://twilio/media/xyz",
        "incoming_media_content_type": "image/jpeg",
    }
    assert agent.route_after_input(state) == "vision_ocr"


def test_route_pdf_goes_to_vision() -> None:
    state = {
        "incoming_media_url": "https://twilio/media/xyz",
        "incoming_media_content_type": "application/pdf",
    }
    assert agent.route_after_input(state) == "vision_ocr"


# --------------------------- nodi copilot / synthesizer ---------------------------

def test_copilot_ask_sets_reply_and_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = CopilotDecision(
        action="ask",
        message_to_patient="Da quanto tempo hai questo dolore?",
        reasoning="serve durata",
    )
    monkeypatch.setattr(agent, "_decide_copilot_action", MagicMock(return_value=fake))

    state = {
        "messages": [HumanMessage(content="Ho mal di testa")],
        "turn_count": 1,
    }
    out = agent.node_anamnesis_copilot(state)

    assert out["reply_to_send"] == "Da quanto tempo hai questo dolore?"
    assert out["current_phase"] == "COLLECTING_ANAMNESIS"
    assert any(isinstance(m, AIMessage) for m in out["messages"])


def test_copilot_finalize_sets_synthesizing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = CopilotDecision(action="finalize", reasoning="abbastanza info")
    monkeypatch.setattr(agent, "_decide_copilot_action", MagicMock(return_value=fake))

    state = {
        "messages": [HumanMessage(content="Ho mal di testa da 2 giorni, prendo tachipirina")],
        "turn_count": 3,
    }
    out = agent.node_anamnesis_copilot(state)

    assert out["current_phase"] == "SYNTHESIZING"
    assert "reply_to_send" not in out or out.get("reply_to_send") is None


def test_copilot_force_finalize_at_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety net: se turn_count >= soglia, force SYNTHESIZING senza chiamare l'LLM."""
    mock_llm = MagicMock()
    monkeypatch.setattr(agent, "_decide_copilot_action", mock_llm)

    state = {
        "messages": [HumanMessage(content="ciao")],
        "turn_count": agent.MAX_TURNS_BEFORE_FORCE_FINALIZE,
    }
    out = agent.node_anamnesis_copilot(state)

    assert out["current_phase"] == "SYNTHESIZING"
    assert mock_llm.call_count == 0


def test_synthesizer_produces_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ClinicalSynthesis(
        chief_complaint="Cefalea",
        history_of_present_illness="Mal di testa da 2 giorni",
        medications=["tachipirina"],
        red_flags=[],
        livello_urgenza="bassa",
        sintesi_medica="Cefalea muscolo-tensiva non complicata.",
    )
    monkeypatch.setattr(agent, "_synthesize_clinical", MagicMock(return_value=fake))

    state = {"messages": [HumanMessage(content="Mal di testa da 2 giorni")]}
    out = agent.node_clinical_synthesizer(state)

    assert out["current_phase"] == "FINISHED"
    assert out["synthesis"]["livello_urgenza"] == "bassa"
    assert out["synthesis"]["chief_complaint"] == "Cefalea"
    assert out["reply_to_send"]


# --------------------------- persistenza Supabase ---------------------------

def test_load_session_returns_state_and_data(supa_mock: MagicMock) -> None:
    supa_mock.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"session_state": "COLLECTING_ANAMNESIS", "session_data": {"turn_count": 2}}
    ]
    state, data = agent.load_session(PAZIENTE_ID)
    assert state == "COLLECTING_ANAMNESIS"
    assert data == {"turn_count": 2}


def test_load_session_defaults_to_idle_when_missing(supa_mock: MagicMock) -> None:
    supa_mock.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    state, data = agent.load_session(PAZIENTE_ID)
    assert state == "IDLE"
    assert data == {}


def test_save_session_writes_state_data_and_ts(supa_mock: MagicMock) -> None:
    agent.save_session(PAZIENTE_ID, "FINISHED", {"turn_count": 5})
    upd = supa_mock.table.return_value.update
    upd.assert_called_once()
    payload = upd.call_args.args[0]
    assert payload["session_state"] == "FINISHED"
    assert payload["session_data"] == {"turn_count": 5}
    assert "session_updated_at" in payload


def test_load_recent_conversation_converts_roles(supa_mock: MagicMock) -> None:
    supa_mock.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
        {"role": "assistant_bot", "content": "Ciao", "created_at": "2026-05-17T10:00:00Z"},
        {"role": "user", "content": "Ho mal di testa", "created_at": "2026-05-17T09:59:00Z"},
    ]
    msgs = agent.load_recent_conversation(PAZIENTE_ID)
    # Il select e' ordinato desc + reversed nel codice -> primo elemento e' user.
    assert len(msgs) == 2
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert msgs[0].content == "Ho mal di testa"


# --------------------------- run_for_job end-to-end ---------------------------

@pytest.fixture
def patch_run_helpers(monkeypatch: pytest.MonkeyPatch):
    """Mocca tutte le dipendenze di run_for_job tranne l'LLM (gestito per-test)."""
    monkeypatch.setattr(
        agent,
        "get_paziente_by_phone",
        MagicMock(return_value=(PAZIENTE_ID, MEDICO_ID, None)),
    )
    monkeypatch.setattr(agent, "load_session", MagicMock(return_value=("IDLE", {})))
    monkeypatch.setattr(agent, "load_recent_conversation", MagicMock(return_value=[]))
    monkeypatch.setattr(agent, "save_session", MagicMock())
    monkeypatch.setattr(agent, "_send_whatsapp_reply_and_log", MagicMock())
    monkeypatch.setattr(agent, "insert_richiesta", MagicMock())
    monkeypatch.setattr(agent, "_log_conversation_turn", MagicMock())


def _payload(**overrides) -> dict:
    base = {
        "from_number": PHONE,
        "body": "Ho mal di testa",
        "num_media": 0,
        "media_url_0": "",
        "media_content_type_0": "",
        "message_sid": "SM_TEST_001",
        "profile_name": "",
    }
    base.update(overrides)
    return base


def test_run_for_job_returns_error_when_paziente_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "get_paziente_by_phone",
        MagicMock(return_value=(None, None, None)),
    )
    out = agent.run_for_job(_payload())
    assert out["status"] == "error"
    assert out["reason"] == "paziente_not_found"


def test_run_for_job_ask_flow(
    patch_run_helpers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent,
        "_decide_copilot_action",
        MagicMock(
            return_value=CopilotDecision(
                action="ask",
                message_to_patient="Da quanto tempo?",
            )
        ),
    )

    out = agent.run_for_job(_payload())

    assert out["status"] == "ok"
    assert out["phase"] == "COLLECTING_ANAMNESIS"
    assert out["sent_reply"] is True
    assert out["synthesis_inserted"] is False
    agent._send_whatsapp_reply_and_log.assert_called_once()
    agent.insert_richiesta.assert_not_called()
    agent.save_session.assert_called_once()
    saved_state = agent.save_session.call_args.args[1]
    assert saved_state == "COLLECTING_ANAMNESIS"


def test_run_for_job_finalize_inserts_richiesta(
    patch_run_helpers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent,
        "_decide_copilot_action",
        MagicMock(return_value=CopilotDecision(action="finalize")),
    )
    monkeypatch.setattr(
        agent,
        "_synthesize_clinical",
        MagicMock(
            return_value=ClinicalSynthesis(
                chief_complaint="Dolore toracico",
                history_of_present_illness="Da 30 minuti, irradiato a braccio sx",
                medications=[],
                red_flags=["irradiazione braccio sinistro"],
                livello_urgenza="alta",
                sintesi_medica="Sospetto evento coronarico acuto, indirizzare a PS.",
            )
        ),
    )

    out = agent.run_for_job(_payload(body="Mi sento il petto schiacciato"))

    assert out["status"] == "ok"
    assert out["phase"] == "FINISHED"
    assert out["synthesis_inserted"] is True
    agent.insert_richiesta.assert_called_once()
    kw = agent.insert_richiesta.call_args.kwargs
    assert kw["urgenza"] == "alta"
    assert kw["riassunto_clinico"].startswith("Sospetto")
    saved_state = agent.save_session.call_args.args[1]
    assert saved_state == "FINISHED"


def test_run_for_job_vision_path_appends_extracted_doc(
    patch_run_helpers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent,
        "download_twilio_media_requests",
        MagicMock(return_value=(b"fake-image-bytes", "image/jpeg", None)),
    )
    monkeypatch.setattr(agent, "upload_bytes_to_supabase_bucket", MagicMock())
    monkeypatch.setattr(
        agent, "_vision_extract_text", MagicMock(return_value="Emoglobina 12.4 g/dL")
    )
    monkeypatch.setattr(
        agent,
        "_decide_copilot_action",
        MagicMock(
            return_value=CopilotDecision(
                action="ask", message_to_patient="Da quando hai questi valori?"
            )
        ),
    )

    out = agent.run_for_job(
        _payload(
            body="",
            media_url_0="https://twilio/media/xyz",
            media_content_type_0="image/jpeg",
            num_media=1,
        )
    )

    assert out["status"] == "ok"
    saved_data = agent.save_session.call_args.args[2]
    assert isinstance(saved_data.get("extracted_docs"), list)
    assert saved_data["extracted_docs"][-1]["extracted_text"].startswith("Emoglobina")
