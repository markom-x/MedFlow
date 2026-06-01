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
    # PR #4: nodi retrieval / embed_and_index sono nel grafo; li azzeriamo per
    # questo test cosi' verifichiamo solo la propagazione di extracted_docs.
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", MagicMock(return_value=[]))
    monkeypatch.setattr(agent, "index_document", MagicMock(return_value=0))

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


# --------------------------- PR #4: chunking ---------------------------

def test_chunk_text_empty_returns_empty() -> None:
    assert agent.chunk_text("") == []
    assert agent.chunk_text("   \n  ") == []


def test_chunk_text_short_returns_single() -> None:
    s = "Referto breve."
    assert agent.chunk_text(s, chunk_size=100, overlap=10) == [s]


def test_chunk_text_long_splits_with_overlap() -> None:
    s = "x" * 250
    chunks = agent.chunk_text(s, chunk_size=100, overlap=20)
    assert len(chunks) >= 3
    assert all(len(c) <= 100 for c in chunks)
    # Le finestre si sovrappongono: i primi 20 char del chunk[1] devono coincidere
    # con gli ultimi 20 di chunk[0].
    assert chunks[1][:20] == chunks[0][-20:]


def test_chunk_text_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError):
        agent.chunk_text("abc", chunk_size=10, overlap=10)
    with pytest.raises(ValueError):
        agent.chunk_text("abc", chunk_size=10, overlap=-1)


# --------------------------- PR #4: embeddings ---------------------------

def _fake_embedding(dim: int = 1536, seed: float = 0.1) -> list[float]:
    return [seed] * dim


def test_embed_texts_returns_empty_when_no_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "openai_client", None)
    assert agent._embed_texts(["ciao"]) == []
    assert agent._embed_text("ciao") is None


def test_embed_texts_batches_and_returns_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_resp = MagicMock()
    fake_resp.data = [
        MagicMock(embedding=_fake_embedding(seed=0.1)),
        MagicMock(embedding=_fake_embedding(seed=0.2)),
    ]
    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = fake_resp
    monkeypatch.setattr(agent, "openai_client", fake_client)

    out = agent._embed_texts(["a", "b"])
    assert len(out) == 2
    assert out[0][0] == pytest.approx(0.1)
    assert out[1][0] == pytest.approx(0.2)
    fake_client.embeddings.create.assert_called_once()


# --------------------------- PR #4: index_document ---------------------------

def test_index_document_inserts_one_row_per_chunk(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent,
        "_embed_texts",
        MagicMock(return_value=[_fake_embedding(seed=0.1), _fake_embedding(seed=0.2)]),
    )
    monkeypatch.setattr(
        agent,
        "chunk_text",
        MagicMock(return_value=["chunk uno", "chunk due"]),
    )

    n = agent.index_document(
        paziente_id=PAZIENTE_ID,
        medico_id=MEDICO_ID,
        source_type="referto_ocr",
        source_id="SM_TEST_001",
        text="testo lungo",
        metadata={"content_type": "image/jpeg"},
    )
    assert n == 2
    insert_call = supa_mock.table.return_value.insert
    insert_call.assert_called_once()
    rows = insert_call.call_args.args[0]
    assert len(rows) == 2
    assert rows[0]["chunk_index"] == 0
    assert rows[1]["chunk_index"] == 1
    assert rows[0]["source_type"] == "referto_ocr"
    assert rows[0]["source_id"] == "SM_TEST_001"
    assert rows[0]["paziente_id"] == PAZIENTE_ID
    assert rows[0]["medico_id"] == MEDICO_ID
    assert isinstance(rows[0]["embedding"], list)
    assert len(rows[0]["embedding"]) == 1536


def test_index_document_skips_empty_text(supa_mock: MagicMock) -> None:
    assert agent.index_document(PAZIENTE_ID, MEDICO_ID, "referto_ocr", None, "") == 0
    supa_mock.table.return_value.insert.assert_not_called()


def test_index_document_skips_when_embedding_fails(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent, "chunk_text", MagicMock(return_value=["chunk uno"]))
    monkeypatch.setattr(agent, "_embed_texts", MagicMock(return_value=[]))
    assert (
        agent.index_document(PAZIENTE_ID, MEDICO_ID, "referto_ocr", None, "x" * 10)
        == 0
    )
    supa_mock.table.return_value.insert.assert_not_called()


# --------------------------- PR #4: retrieve_relevant_chunks ---------------------------

def test_retrieve_returns_empty_for_short_query(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent, "_embed_text", MagicMock(return_value=_fake_embedding()))
    out = agent.retrieve_relevant_chunks(PAZIENTE_ID, "ah")
    assert out == []
    supa_mock.rpc.assert_not_called()


def test_retrieve_calls_match_rpc_and_returns_data(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent, "_embed_text", MagicMock(return_value=_fake_embedding()))
    supa_mock.rpc.return_value.execute.return_value.data = [
        {
            "id": "c1",
            "source_type": "referto_ocr",
            "content": "Emoglobina 12.4",
            "similarity": 0.83,
            "metadata": {},
            "created_at": "2026-05-01T10:00:00Z",
        }
    ]
    out = agent.retrieve_relevant_chunks(PAZIENTE_ID, "ho fatto le analisi del sangue")
    assert len(out) == 1
    assert out[0]["similarity"] == pytest.approx(0.83)
    supa_mock.rpc.assert_called_once()
    rpc_args = supa_mock.rpc.call_args
    assert rpc_args.args[0] == "match_anamnesi_documenti"
    rpc_payload = rpc_args.args[1]
    assert rpc_payload["match_paziente_id"] == PAZIENTE_ID
    assert isinstance(rpc_payload["query_embedding"], list)


def test_retrieve_returns_empty_on_rpc_error(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent, "_embed_text", MagicMock(return_value=_fake_embedding()))
    supa_mock.rpc.return_value.execute.side_effect = RuntimeError("rpc down")
    out = agent.retrieve_relevant_chunks(PAZIENTE_ID, "una query abbastanza lunga")
    assert out == []


# --------------------------- PR #4: nodi retrieval / embed_and_index ---------------------------

def test_node_retrieval_injects_system_message_when_chunks_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "retrieve_relevant_chunks",
        MagicMock(
            return_value=[
                {
                    "source_type": "richiesta_sintesi",
                    "content": "Cefalea muscolo-tensiva ricorrente",
                    "similarity": 0.71,
                    "created_at": "2026-04-01T10:00:00Z",
                }
            ]
        ),
    )
    state = {
        "paziente_id": PAZIENTE_ID,
        "messages": [HumanMessage(content="Mi e' tornato il mal di testa")],
    }
    out = agent.node_retrieval(state)
    assert "messages" in out
    sys_msg = out["messages"][0]
    from langchain_core.messages import SystemMessage  # local import for clarity
    assert isinstance(sys_msg, SystemMessage)
    assert "Cefalea muscolo-tensiva" in sys_msg.content


def test_node_retrieval_noop_when_no_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", MagicMock(return_value=[]))
    state = {
        "paziente_id": PAZIENTE_ID,
        "messages": [HumanMessage(content="Mi e' tornato il mal di testa")],
    }
    assert agent.node_retrieval(state) == {}


def test_node_retrieval_noop_when_no_human_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_retrieve = MagicMock(return_value=[])
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", mock_retrieve)
    state = {"paziente_id": PAZIENTE_ID, "messages": []}
    assert agent.node_retrieval(state) == {}
    mock_retrieve.assert_not_called()


def test_node_embed_and_index_runs_when_flag_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_index = MagicMock(return_value=3)
    monkeypatch.setattr(agent, "index_document", mock_index)
    state = {
        "needs_indexing": True,
        "paziente_id": PAZIENTE_ID,
        "medico_id": MEDICO_ID,
        "message_sid": "SM_1",
        "extracted_docs": [
            {
                "extracted_text": "Emoglobina 12.4 g/dL, glicemia nella norma.",
                "content_type": "image/jpeg",
                "source_url": "https://twilio/x",
            }
        ],
    }
    out = agent.node_embed_and_index(state)
    assert out["needs_indexing"] is False
    mock_index.assert_called_once()
    kw = mock_index.call_args.kwargs
    assert kw["source_type"] == "referto_ocr"
    assert kw["source_id"] == "SM_1"


def test_node_embed_and_index_skips_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_index = MagicMock()
    monkeypatch.setattr(agent, "index_document", mock_index)
    state = {"needs_indexing": False, "extracted_docs": [{"extracted_text": "x"}]}
    assert agent.node_embed_and_index(state) == {}
    mock_index.assert_not_called()


def test_node_embed_and_index_skips_error_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_index = MagicMock()
    monkeypatch.setattr(agent, "index_document", mock_index)
    state = {
        "needs_indexing": True,
        "paziente_id": PAZIENTE_ID,
        "medico_id": MEDICO_ID,
        "extracted_docs": [{"extracted_text": "[Errore OCR: TimeoutError]"}],
    }
    out = agent.node_embed_and_index(state)
    assert out == {"needs_indexing": False}
    mock_index.assert_not_called()


# --------------------------- PR #4: synthesizer indexa la sintesi ---------------------------

def test_synthesizer_indexes_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ClinicalSynthesis(
        chief_complaint="Dolore lombare",
        history_of_present_illness="Da 5 giorni dopo sollevamento pesi",
        medications=["ibuprofene 400"],
        red_flags=[],
        livello_urgenza="bassa",
        sintesi_medica="Lombalgia muscolo-tensiva, gestibile in ambulatorio.",
    )
    monkeypatch.setattr(agent, "_synthesize_clinical", MagicMock(return_value=fake))
    mock_index = MagicMock(return_value=1)
    monkeypatch.setattr(agent, "index_document", mock_index)

    state = {
        "messages": [HumanMessage(content="Mi fa male la schiena da 5 giorni")],
        "paziente_id": PAZIENTE_ID,
        "medico_id": MEDICO_ID,
        "message_sid": "SM_FIN_001",
    }
    out = agent.node_clinical_synthesizer(state)

    assert out["current_phase"] == "FINISHED"
    mock_index.assert_called_once()
    kw = mock_index.call_args.kwargs
    assert kw["source_type"] == "richiesta_sintesi"
    assert "Dolore lombare" in kw["text"]
    assert kw["metadata"]["livello_urgenza"] == "bassa"


# --------------------------- PR #4: run_for_job con RAG attivo ---------------------------

def test_run_for_job_text_path_invokes_retrieval_and_injects_context(
    patch_run_helpers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end del path testo con RAG attivo. Simuliamo il flow reale PR #2:
    il webhook ha gia' loggato il messaggio in `conversazioni`, quindi
    `load_recent_conversation` lo restituisce come HumanMessage. Il nodo
    `retrieval` ne usa il contenuto come query semantica."""
    monkeypatch.setattr(
        agent,
        "load_recent_conversation",
        MagicMock(
            return_value=[HumanMessage(content="Mi e' tornato il mal di testa")]
        ),
    )

    captured_messages: dict = {}

    def fake_decide(messages):
        captured_messages["msgs"] = messages
        return CopilotDecision(
            action="ask",
            message_to_patient="Hai gia' provato qualche farmaco?",
        )

    monkeypatch.setattr(agent, "_decide_copilot_action", fake_decide)
    mock_retrieve = MagicMock(
        return_value=[
            {
                "source_type": "richiesta_sintesi",
                "content": "Anamnesi precedente: cefalea ricorrente, no red flags.",
                "similarity": 0.78,
                "created_at": "2026-03-01T10:00:00Z",
            }
        ]
    )
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", mock_retrieve)
    monkeypatch.setattr(agent, "index_document", MagicMock(return_value=0))

    out = agent.run_for_job(_payload(body="Mi e' tornato il mal di testa"))

    assert out["status"] == "ok"
    mock_retrieve.assert_called_once()
    rpc_args = mock_retrieve.call_args
    assert rpc_args.args[0] == PAZIENTE_ID
    assert "mal di testa" in rpc_args.args[1]

    from langchain_core.messages import SystemMessage

    rag_systems = [
        m
        for m in captured_messages["msgs"]
        if isinstance(m, SystemMessage) and "Contesto storico paziente" in m.content
    ]
    assert len(rag_systems) == 1
    assert "cefalea ricorrente" in rag_systems[0].content


# --------------------------- consultazione fascicolo (RAG medico-facing) ---------------------------

def test_answer_fascicolo_query_short_query_no_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_retrieve = MagicMock()
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", mock_retrieve)
    out = agent.answer_fascicolo_query(PAZIENTE_ID, "hb?")
    assert out["sources"] == []
    assert "specifica" in out["answer"].lower()
    mock_retrieve.assert_not_called()


def test_answer_fascicolo_query_no_chunks_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", MagicMock(return_value=[]))
    mock_llm = MagicMock()
    monkeypatch.setattr(agent, "_generate_fascicolo_answer", mock_llm)

    out = agent.answer_fascicolo_query(PAZIENTE_ID, "qual e' l'ultimo valore di emoglobina?")
    assert out["sources"] == []
    assert "fascicolo" in out["answer"].lower()
    # Niente chiamata LLM se non c'e' contesto.
    mock_llm.assert_not_called()


def test_answer_fascicolo_query_grounds_on_chunks_and_returns_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_retrieve = MagicMock(
        return_value=[
            {
                "source_type": "referto_ocr",
                "source_id": "SM_OCR_1",
                "content": "Emoglobina 12.4 g/dL (v.n. 13-17)",
                "similarity": 0.81,
                "created_at": "2026-05-01T10:00:00Z",
            },
            {
                "source_type": "richiesta_sintesi",
                "source_id": "SM_FIN_2",
                "content": "Anemia lieve in follow-up.",
                "similarity": 0.62,
                "created_at": "2026-04-01T10:00:00Z",
            },
        ]
    )
    monkeypatch.setattr(agent, "retrieve_relevant_chunks", mock_retrieve)

    captured: dict = {}

    def fake_answer(messages):
        captured["msgs"] = messages
        return "Ultima emoglobina: 12.4 g/dL (sotto il valore minimo)."

    monkeypatch.setattr(agent, "_generate_fascicolo_answer", fake_answer)

    out = agent.answer_fascicolo_query(
        PAZIENTE_ID, "qual e' l'ultimo valore di emoglobina?"
    )

    assert out["answer"].startswith("Ultima emoglobina")
    assert len(out["sources"]) == 2
    assert out["sources"][0]["source_type"] == "referto_ocr"
    assert out["sources"][0]["source_id"] == "SM_OCR_1"
    assert out["sources"][0]["similarity"] == pytest.approx(0.81)

    # Il fascicolo usa knob piu' permissivi del RAG interno.
    rpc_kwargs = mock_retrieve.call_args.kwargs
    assert rpc_kwargs["top_k"] == agent.FASCICOLO_TOP_K
    assert rpc_kwargs["min_similarity"] == agent.FASCICOLO_MIN_SIMILARITY

    # Il contesto dei chunk e' iniettato nei messaggi LLM (grounding).
    from langchain_core.messages import HumanMessage as HM, SystemMessage as SM

    assert isinstance(captured["msgs"][0], SM)
    human = next(m for m in captured["msgs"] if isinstance(m, HM))
    assert "Emoglobina 12.4" in human.content
    assert "emoglobina" in human.content.lower()


def test_answer_fascicolo_query_llm_error_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "retrieve_relevant_chunks",
        MagicMock(
            return_value=[
                {
                    "source_type": "referto_ocr",
                    "content": "Emoglobina 12.4",
                    "similarity": 0.8,
                    "created_at": "2026-05-01T10:00:00Z",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        agent,
        "_generate_fascicolo_answer",
        MagicMock(side_effect=RuntimeError("LLM down")),
    )

    out = agent.answer_fascicolo_query(PAZIENTE_ID, "una domanda abbastanza lunga")
    assert out["sources"] == []
    assert out["error"] == "RuntimeError"
    assert "errore" in out["answer"].lower()


# --------------------------- backfill_fascicolo ---------------------------

def test_richiesta_to_text_composes_fields() -> None:
    text = agent._richiesta_to_text(
        {
            "riassunto_clinico": "Cefalea muscolo-tensiva",
            "messaggio_originale": "Ho mal di testa e un po' di febbre",
            "urgenza": "bassa",
        }
    )
    assert "Sintesi clinica: Cefalea" in text
    assert "Messaggio: Ho mal di testa" in text
    assert "Urgenza: bassa" in text


def _table_router(rows_by_table: dict[str, list[dict]]):
    """Costruisce una side_effect per supabase.table() che ritorna builder
    distinti per tabella, supportando il chaining .select(...).eq(...).execute()."""

    def factory(name: str):
        tbl = MagicMock(name=f"table_{name}")
        data = rows_by_table.get(name, [])
        # .select(...).execute().data  e  .select(...).eq(...).execute().data
        select_builder = tbl.select.return_value
        select_builder.execute.return_value.data = data
        select_builder.eq.return_value.execute.return_value.data = data
        select_builder.eq.return_value.eq.return_value.execute.return_value.data = data
        return tbl

    return factory


def test_backfill_indexes_richieste_and_conversazioni(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent, "_already_indexed_source_ids", MagicMock(return_value=set())
    )
    mock_index = MagicMock(return_value=1)
    monkeypatch.setattr(agent, "index_document", mock_index)

    supa_mock.table.side_effect = _table_router(
        {
            "richieste": [
                {
                    "id": "ric-1",
                    "paziente_id": PAZIENTE_ID,
                    "medico_id": MEDICO_ID,
                    "messaggio_originale": "Ho febbre a 38.5 da ieri",
                    "riassunto_clinico": "Stato febbrile",
                    "urgenza": "media",
                    "created_at": "2026-05-30T10:00:00Z",
                }
            ],
            "conversazioni": [
                {
                    "id": "conv-1",
                    "paziente_id": PAZIENTE_ID,
                    "medico_id": MEDICO_ID,
                    "role": "user",
                    "content": "La temperatura stamattina era 37.8",
                    "created_at": "2026-05-30T11:00:00Z",
                }
            ],
        }
    )

    stats = agent.backfill_fascicolo()

    assert stats["richieste_indicizzate"] == 1
    assert stats["conversazioni_indicizzate"] == 1
    assert stats["chunk"] == 2

    calls = {c.kwargs["source_type"]: c.kwargs for c in mock_index.call_args_list}
    assert calls["richiesta_sintesi"]["source_id"] == "ric-1"
    assert "febbre" in calls["richiesta_sintesi"]["text"].lower()
    assert calls["conversazione"]["source_id"] == "conv-1"
    assert "temperatura" in calls["conversazione"]["text"].lower()


def test_backfill_skips_already_indexed(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ric-1 gia' indicizzata -> deve essere saltata.
    monkeypatch.setattr(
        agent,
        "_already_indexed_source_ids",
        MagicMock(side_effect=lambda pid, st: {"ric-1"} if st == "richiesta_sintesi" else set()),
    )
    mock_index = MagicMock(return_value=1)
    monkeypatch.setattr(agent, "index_document", mock_index)

    supa_mock.table.side_effect = _table_router(
        {
            "richieste": [
                {
                    "id": "ric-1",
                    "paziente_id": PAZIENTE_ID,
                    "medico_id": MEDICO_ID,
                    "messaggio_originale": "x",
                    "riassunto_clinico": "y",
                    "urgenza": "bassa",
                }
            ],
            "conversazioni": [],
        }
    )

    stats = agent.backfill_fascicolo(PAZIENTE_ID)
    assert stats["richieste_indicizzate"] == 0
    assert stats["saltate"] == 1
    mock_index.assert_not_called()


def test_backfill_no_supabase_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "supabase", None)
    stats = agent.backfill_fascicolo()
    assert stats.get("error") == "supabase_non_configurato"


# --------------------------- index_job (indicizzazione automatica via trigger) ---------------------------

def _single_row_table(row: dict | None):
    """side_effect per supabase.table() che ritorna .select(*).eq(id).limit(1).execute().data."""

    def factory(_name: str):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
            [row] if row else []
        )
        return tbl

    return factory


def test_index_job_richiesta_indexes_row(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent, "_already_indexed_source_ids", MagicMock(return_value=set())
    )
    mock_index = MagicMock(return_value=1)
    monkeypatch.setattr(agent, "index_document", mock_index)
    supa_mock.table.side_effect = _single_row_table(
        {
            "id": "ric-1",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
            "messaggio_originale": "Ho febbre a 39",
            "riassunto_clinico": "Stato febbrile",
            "urgenza": "alta",
        }
    )

    out = agent.index_job(
        {
            "source_table": "richieste",
            "source_id": "ric-1",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
        }
    )
    assert out["status"] == "ok"
    assert out["source_type"] == "richiesta_sintesi"
    kw = mock_index.call_args.kwargs
    assert kw["source_id"] == "ric-1"
    assert "febbre" in kw["text"].lower()


def test_index_job_conversazione_indexes_with_role(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent, "_already_indexed_source_ids", MagicMock(return_value=set())
    )
    mock_index = MagicMock(return_value=1)
    monkeypatch.setattr(agent, "index_document", mock_index)
    supa_mock.table.side_effect = _single_row_table(
        {
            "id": "conv-1",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
            "role": "user",
            "content": "La temperatura era 37.9",
        }
    )

    out = agent.index_job(
        {
            "source_table": "conversazioni",
            "source_id": "conv-1",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
        }
    )
    assert out["status"] == "ok"
    assert out["source_type"] == "conversazione"
    assert "[user]" in mock_index.call_args.kwargs["text"]


def test_index_job_skips_when_already_indexed(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent, "_already_indexed_source_ids", MagicMock(return_value={"ric-1"})
    )
    mock_index = MagicMock()
    monkeypatch.setattr(agent, "index_document", mock_index)

    out = agent.index_job(
        {
            "source_table": "richieste",
            "source_id": "ric-1",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
        }
    )
    assert out["status"] == "skipped"
    mock_index.assert_not_called()


def test_index_job_unknown_table_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    out = agent.index_job(
        {
            "source_table": "pazienti",
            "source_id": "x",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
        }
    )
    assert out["status"] == "error"
    assert "source_table_sconosciuta" in out["reason"]


def test_index_job_incomplete_payload_errors() -> None:
    out = agent.index_job({"source_table": "richieste"})
    assert out["status"] == "error"
    assert out["reason"] == "payload_incompleto"


def test_index_job_row_not_found_errors(
    supa_mock: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent, "_already_indexed_source_ids", MagicMock(return_value=set())
    )
    supa_mock.table.side_effect = _single_row_table(None)
    out = agent.index_job(
        {
            "source_table": "richieste",
            "source_id": "ghost",
            "paziente_id": PAZIENTE_ID,
            "medico_id": MEDICO_ID,
        }
    )
    assert out["status"] == "error"
    assert out["reason"] == "row_non_trovata"
