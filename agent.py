"""
MedFlow Anamnesis Agent (PR #3).

LangGraph skeleton del copilot pre-visita. Il worker (`worker.py`) chiama
`run_for_job(payload)` per ogni job in coda; la funzione carica lo stato
da Supabase, invoca il grafo, e si occupa dei side-effect (reply WhatsApp,
log del turno assistant in `conversazioni`, eventuale INSERT in `richieste`,
persistenza dello stato in `pazienti`).

Architettura del grafo:

    START
      |
      v
   input_router  --(audio)--> whisper_transcribe ---+
      |   |                                          |
      |   +--(image/PDF)--> vision_ocr  -------------+
      |                                              |
      +--(testo)------------------------------------>+
                                                     |
                                                     v
                                            anamnesis_copilot
                                              |        |
                                              |        +--(action=ask)--> END (reply al paziente)
                                              |
                                              +--(action=finalize)--> clinical_synthesizer --> END

Persistenza:
- `pazienti.session_state`  = current_phase del grafo (IDLE / COLLECTING_ANAMNESIS /
  SYNTHESIZING / FINISHED).
- `pazienti.session_data`   = JSON con `extracted_docs`, `turn_count`, metadati.
- Storia conversazionale    = `conversazioni` (sorgente di verita', non duplichiamo
  i messaggi dentro session_data).

I prompt sono placeholder: vanno raffinati clinicamente nei PR successivi.
"""
from __future__ import annotations

import base64
import os
import traceback
from datetime import datetime, timezone
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from main import (
    download_twilio_media_requests,
    get_paziente_by_phone,
    insert_richiesta,
    openai_client,
    supabase,
    transcribe_audio_bytes_whisper,
    upload_bytes_to_supabase_bucket,
    upload_file_bytes_to_storage,
    _log_conversation_turn,
    _normalize_content_type,
    _send_whatsapp_reply_and_log,
    _storage_relative_path,
)

# --------------------------- config / costanti ---------------------------

CHAT_MODEL = os.getenv("MEDFLOW_CHAT_MODEL", "gpt-4o")
VISION_MODEL = os.getenv("MEDFLOW_VISION_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("MEDFLOW_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small
MAX_TURNS_BEFORE_FORCE_FINALIZE = int(os.getenv("MEDFLOW_MAX_TURNS", "8"))
HISTORY_LIMIT = int(os.getenv("MEDFLOW_HISTORY_LIMIT", "30"))

# RAG knob
CHUNK_SIZE_CHARS = int(os.getenv("MEDFLOW_CHUNK_SIZE_CHARS", "1600"))
CHUNK_OVERLAP_CHARS = int(os.getenv("MEDFLOW_CHUNK_OVERLAP_CHARS", "200"))
RAG_TOP_K = int(os.getenv("MEDFLOW_RAG_TOP_K", "5"))
RAG_MIN_SIMILARITY = float(os.getenv("MEDFLOW_RAG_MIN_SIMILARITY", "0.5"))
RAG_MIN_QUERY_CHARS = int(os.getenv("MEDFLOW_RAG_MIN_QUERY_CHARS", "8"))

ANAMNESIS_SYSTEM_PROMPT = """Sei un assistente medico che conduce un'anamnesi pre-visita
per conto di un Medico di Medicina Generale. Parli al paziente via WhatsApp in italiano,
in modo empatico, chiaro e professionale. Non sei il medico: non diagnostichi e non prescrivi.

Il tuo obiettivo: raccogliere in pochi turni le informazioni essenziali per il medico.
Per ogni turno devi decidere tra due azioni:
  - "ask": fai UNA sola domanda mirata, breve, in italiano colloquiale. Non elencare,
           non sovraccaricare. Se il paziente ha allegato un referto OCR, tienine conto.
  - "finalize": ritieni di avere abbastanza informazioni per consegnare la sintesi al medico.
                Scegli "finalize" non appena hai sintomi principali, durata, contesto e
                eventuali farmaci in corso o red flags evidenti.

Regole:
- Una domanda per turno. Niente preamboli lunghi.
- Se sospetti red flag (dolore toracico forte, dispnea grave, deficit neurologici,
  emorragie, perdita di coscienza), finalizza subito con livello_urgenza='alta'.
- Mai mostrare PII di altri pazienti, mai inventare dati clinici.

Rispondi SEMPRE con l'output strutturato richiesto, non con testo libero.
""".strip()


SYNTHESIZER_SYSTEM_PROMPT = """Sei l'agente di sintesi clinica di MedFlow. A partire
dallo storico della conversazione paziente-bot e dagli eventuali referti OCR, produci
una sintesi strutturata per il medico in italiano.

Schema rigoroso (la dashboard del medico legge questi campi):
- chief_complaint: motivo principale, una frase.
- history_of_present_illness: dettagli (durata, fattori scatenanti, sintomi associati).
- medications: lista di farmaci citati dal paziente.
- red_flags: eventuali segnali di allarme.
- livello_urgenza: 'alta' | 'media' | 'bassa' (minuscolo, italiano).
- sintesi_medica: 1-2 frasi clinico-sintetiche, max 30 parole.

Non includere PII (nome, cognome, telefono) nella sintesi.
""".strip()


# --------------------------- schema stato grafo ---------------------------

class AgentState(TypedDict, total=False):
    """Stato della LangGraph runtime. `total=False` perche' alcuni campi sono
    valorizzati solo da certi nodi (es. `synthesis` solo dal synthesizer)."""

    # Identita' (passata dal worker, non muta durante il turno)
    paziente_id: str
    medico_id: str
    phone: str
    message_sid: str

    # Input del turno corrente
    incoming_body: str
    incoming_media_url: str
    incoming_media_content_type: str

    # Storia condivisa: il reducer `add_messages` accumula in modo idempotente.
    messages: Annotated[list[BaseMessage], add_messages]

    # Memoria di sessione (persistita su pazienti.session_data)
    extracted_docs: list[dict]
    turn_count: int
    current_phase: str  # IDLE | COLLECTING_ANAMNESIS | SYNTHESIZING | FINISHED

    # Output del turno (consumati dal worker dopo invoke)
    reply_to_send: str | None
    synthesis: dict | None

    # Flag transient: settato da vision_ocr/whisper, consumato da embed_and_index.
    needs_indexing: bool

    # Per debug / log
    last_error: str | None


# --------------------------- schemi pydantic per LLM ---------------------------

class CopilotDecision(BaseModel):
    """Output strutturato di `anamnesis_copilot`."""

    action: Literal["ask", "finalize"] = Field(
        description="ask = una domanda al paziente; finalize = passa al synthesizer"
    )
    message_to_patient: str | None = Field(
        default=None,
        description="Testo da inviare al paziente. Obbligatorio se action='ask'.",
    )
    reasoning: str | None = Field(
        default=None,
        description="Breve nota interna (non inviata al paziente).",
    )


class ClinicalSynthesis(BaseModel):
    """Output strutturato di `clinical_synthesizer`."""

    chief_complaint: str
    history_of_present_illness: str
    medications: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    livello_urgenza: Literal["alta", "media", "bassa"]
    sintesi_medica: str


# --------------------------- helper RAG (chunking + embeddings) ---------------------------

def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    """
    Chunker semplice character-based con sliding window e overlap. Sufficiente
    per referti OCR e sintesi cliniche (1-3 pagine tipiche).
    - text vuoto / solo whitespace -> []
    - text <= chunk_size -> [text]
    - altrimenti finestre [0..chunk_size], [chunk_size-overlap..2*chunk_size-overlap], ...
    """
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap deve essere in [0, chunk_size).")
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start += step
    return chunks


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed via OpenAI. Lista vuota se openai non e' configurato o errore."""
    if not openai_client or not texts:
        return []
    try:
        resp = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        return [d.embedding for d in resp.data]
    except Exception as e:
        print(f"[agent] ERRORE embed_texts: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return []


def _embed_text(text: str) -> list[float] | None:
    out = _embed_texts([text])
    return out[0] if out else None


def index_document(
    paziente_id: str,
    medico_id: str,
    source_type: str,
    source_id: str | None,
    text: str,
    metadata: dict | None = None,
) -> int:
    """
    Splitta `text` in chunk, li embedda e li inserisce in `anamnesi_documenti`.
    Ritorna il numero di chunk effettivamente scritti.
    Errori (rete, tabella mancante, ecc.) -> log + 0 (l'agent procede senza RAG).
    """
    if not supabase:
        print("[agent] index_document: Supabase non configurato, skip.", flush=True)
        return 0
    if not paziente_id or not medico_id:
        return 0
    chunks = chunk_text(text)
    if not chunks:
        return 0
    embeddings = _embed_texts(chunks)
    if len(embeddings) != len(chunks):
        print(
            f"[agent] index_document: mismatch chunks={len(chunks)} vs "
            f"embeddings={len(embeddings)}, skip.",
            flush=True,
        )
        return 0

    md = metadata or {}
    rows = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        rows.append(
            {
                "paziente_id": paziente_id,
                "medico_id": medico_id,
                "source_type": source_type,
                "source_id": source_id,
                "chunk_index": i,
                "content": chunk,
                "embedding": emb,
                "metadata": md,
            }
        )
    try:
        supabase.table("anamnesi_documenti").insert(rows).execute()
        print(
            f"[agent] indicizzati {len(rows)} chunk (source_type={source_type}, "
            f"source_id={source_id}).",
            flush=True,
        )
        return len(rows)
    except Exception as e:
        print(f"[agent] ERRORE index_document: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return 0


def retrieve_relevant_chunks(
    paziente_id: str,
    query: str,
    top_k: int = RAG_TOP_K,
    min_similarity: float = RAG_MIN_SIMILARITY,
) -> list[dict]:
    """
    Similarity search via RPC `match_anamnesi_documenti`. Ritorna lista di dict
    (id, source_type, content, similarity, ...). Empty list se non c'e' nulla
    o se qualcosa fallisce.
    """
    if not supabase or not paziente_id:
        return []
    cleaned_query = (query or "").strip()
    if len(cleaned_query) < RAG_MIN_QUERY_CHARS:
        return []
    query_emb = _embed_text(cleaned_query)
    if not query_emb:
        return []
    try:
        resp = supabase.rpc(
            "match_anamnesi_documenti",
            {
                "query_embedding": query_emb,
                "match_paziente_id": paziente_id,
                "match_count": top_k,
                "min_similarity": min_similarity,
            },
        ).execute()
        return list(resp.data or [])
    except Exception as e:
        print(
            f"[agent] ERRORE retrieve_relevant_chunks: {type(e).__name__}: {e}",
            flush=True,
        )
        traceback.print_exc()
        return []


# --------------------------- helper LLM (mockable) ---------------------------

def _get_chat_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(model=CHAT_MODEL, temperature=temperature, timeout=30)


def _decide_copilot_action(messages: list[BaseMessage]) -> CopilotDecision:
    """Wrapper isolato cosi' i test possono monkeypatchare in modo netto."""
    llm = _get_chat_llm(temperature=0.2)
    structured = llm.with_structured_output(CopilotDecision)
    return structured.invoke(messages)


def _synthesize_clinical(messages: list[BaseMessage]) -> ClinicalSynthesis:
    llm = _get_chat_llm(temperature=0.0)
    structured = llm.with_structured_output(ClinicalSynthesis)
    return structured.invoke(messages)


def _vision_extract_text(file_bytes: bytes, content_type: str) -> str:
    """OCR via GPT-4o vision. Supporta `image/*`. Per `application/pdf`
    ritorna un placeholder finche' non aggiungiamo conversione PDF->immagine
    (followup PR). Il chiamante decide come gestirlo."""
    ct = (content_type or "").lower().strip()
    if ct == "application/pdf":
        return (
            "[Referto PDF allegato — OCR su PDF non ancora implementato in questo PR. "
            "Chiedi al paziente di descrivere a voce o di inviare una foto della pagina rilevante.]"
        )
    if not ct.startswith("image/"):
        return f"[Allegato non interpretabile come immagine: {ct or 'sconosciuto'}]"

    try:
        b64 = base64.b64encode(file_bytes).decode("ascii")
        data_url = f"data:{ct};base64,{b64}"
        llm = ChatOpenAI(model=VISION_MODEL, temperature=0.0, timeout=60)
        msg = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Estrai integralmente il contenuto clinico del referto in italiano. "
                        "Mantieni valori numerici, range di riferimento e diagnosi. "
                        "NON aggiungere commenti. Solo testo estratto."
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        )
        resp = llm.invoke([msg])
        text = getattr(resp, "content", None)
        if isinstance(text, list):
            text = " ".join(
                part.get("text", "") for part in text if isinstance(part, dict)
            )
        return (text or "").strip() or "[OCR vuoto]"
    except Exception as e:
        print(f"[agent] ERRORE vision OCR: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return f"[Errore OCR: {type(e).__name__}]"


# --------------------------- nodi del grafo ---------------------------

def node_input_router(state: AgentState) -> dict:
    """Incrementa il turn_count. Il vero routing avviene nelle conditional edges."""
    return {"turn_count": int(state.get("turn_count") or 0) + 1}


def route_after_input(state: AgentState) -> str:
    ct = (state.get("incoming_media_content_type") or "").lower().strip()
    url = (state.get("incoming_media_url") or "").strip()
    if url and ct.startswith("audio/"):
        return "whisper_transcribe"
    if url and (ct.startswith("image/") or ct == "application/pdf"):
        return "vision_ocr"
    return "anamnesis_copilot"


def node_vision_ocr(state: AgentState) -> dict:
    """Scarica il referto, fa OCR via GPT-4o vision, archivia su bucket `referti`
    e appende l'estratto allo stato + come HumanMessage cosi' il copilot lo vede."""
    url = state.get("incoming_media_url", "")
    ct_hint = state.get("incoming_media_content_type", "")
    phone = state.get("phone", "") or ""
    msid = state.get("message_sid", "") or ""

    file_bytes, dl_ct, dl_cd = download_twilio_media_requests(url)
    if not file_bytes:
        return {
            "messages": [
                HumanMessage(content="[Referto inviato dal paziente: download fallito]")
            ],
            "last_error": "vision_download_failed",
        }

    ct_resolved = _normalize_content_type(dl_ct, ct_hint)

    try:
        object_path = _storage_relative_path("referti", phone, ct_resolved, dl_cd, msid)
        upload_bytes_to_supabase_bucket("referti", object_path, file_bytes, ct_resolved)
    except Exception as e:
        print(f"[agent] ERRORE upload referto: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    extracted_text = _vision_extract_text(file_bytes, ct_resolved)
    docs = list(state.get("extracted_docs") or [])
    docs.append(
        {
            "source_url": url,
            "content_type": ct_resolved,
            "extracted_text": extracted_text,
            "extracted_at": _utcnow_iso(),
        }
    )
    return {
        "extracted_docs": docs,
        "messages": [
            HumanMessage(content=f"[Referto allegato — OCR]\n{extracted_text}")
        ],
        "needs_indexing": True,
    }


def node_whisper_transcribe(state: AgentState) -> dict:
    """Scarica l'audio, trascrive con Whisper, archivia su bucket `vocali`."""
    url = state.get("incoming_media_url", "")
    ct_hint = state.get("incoming_media_content_type", "")
    phone = state.get("phone", "") or ""
    msid = state.get("message_sid", "") or ""

    file_bytes, dl_ct, dl_cd = download_twilio_media_requests(url)
    if not file_bytes:
        return {
            "messages": [
                HumanMessage(
                    content="[Vocale paziente: download fallito, chiedi di riprovare]"
                )
            ],
            "last_error": "whisper_download_failed",
        }

    ct_resolved = _normalize_content_type(dl_ct, ct_hint)

    try:
        upload_file_bytes_to_storage(file_bytes, phone, ct_resolved, dl_cd, msid)
    except Exception as e:
        print(f"[agent] ERRORE upload vocale: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()

    transcript = transcribe_audio_bytes_whisper(file_bytes, ct_resolved) or ""
    if not transcript.strip():
        return {
            "messages": [
                HumanMessage(
                    content="[Vocale paziente: trascrizione non disponibile]"
                )
            ],
            "last_error": "whisper_empty",
        }
    return {
        "messages": [
            HumanMessage(content=f"[Vocale paziente — trascrizione]\n{transcript}")
        ],
    }


def _last_human_text(messages: list[BaseMessage]) -> str:
    """Estrae il testo dell'ultimo HumanMessage utile come query RAG."""
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            content = m.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                # multi-part (vision): concatena le sole parti "text"
                joined = " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ).strip()
                if joined:
                    return joined
    return ""


def node_retrieval(state: AgentState) -> dict:
    """
    RAG: cerca chunk rilevanti nella storia del paziente e li inietta come
    SystemMessage nel contesto. No-op se non c'e' una query utile (es. primo
    turno con storia vuota) o se la tabella anamnesi_documenti non e' ancora
    popolata. Mai bloccante.
    """
    pid = state.get("paziente_id") or ""
    messages = state.get("messages") or []
    query = _last_human_text(messages)
    if not pid or not query:
        return {}

    chunks = retrieve_relevant_chunks(pid, query)
    if not chunks:
        return {}

    parts = []
    for c in chunks:
        sim = float(c.get("similarity") or 0.0)
        st = c.get("source_type") or "?"
        ts = c.get("created_at") or ""
        content = c.get("content") or ""
        parts.append(f"[{st} | sim={sim:.2f} | {ts}]\n{content}")
    context_block = "\n\n".join(parts)

    rag_msg = SystemMessage(
        content=(
            "Contesto storico paziente (recuperato via RAG, usalo SOLO se "
            "clinicamente pertinente alla conversazione corrente, non ripeterlo "
            "letteralmente al paziente):\n"
            f"{context_block}"
        )
    )
    print(
        f"[agent] retrieval: {len(chunks)} chunk pertinenti per paziente={pid}.",
        flush=True,
    )
    return {"messages": [rag_msg]}


def node_embed_and_index(state: AgentState) -> dict:
    """
    Indicizza l'ultimo documento estratto (OCR / trascrizione) in
    `anamnesi_documenti` per renderlo retrievable nei turni futuri. Si attiva
    solo se il nodo a monte ha settato `needs_indexing=True`. Mai bloccante.
    """
    if not state.get("needs_indexing"):
        return {}
    pid = state.get("paziente_id") or ""
    mid = state.get("medico_id") or ""
    docs = state.get("extracted_docs") or []
    msid = state.get("message_sid") or ""
    if not pid or not mid or not docs:
        return {"needs_indexing": False}

    latest = docs[-1] or {}
    text = (latest.get("extracted_text") or "").strip()
    # Salta i marker di errore / placeholder che vision_ocr emette
    skip_prefixes = ("[Errore", "[Referto PDF", "[Allegato non interpretabile", "[OCR vuoto")
    if not text or text.startswith(skip_prefixes):
        return {"needs_indexing": False}

    index_document(
        paziente_id=pid,
        medico_id=mid,
        source_type="referto_ocr",
        source_id=msid or None,
        text=text,
        metadata={
            "content_type": latest.get("content_type"),
            "source_url": latest.get("source_url"),
        },
    )
    return {"needs_indexing": False}


def node_anamnesis_copilot(state: AgentState) -> dict:
    """Core: il copilot decide ask vs finalize. Safety net su turn_count."""
    turn_count = int(state.get("turn_count") or 0)

    if turn_count >= MAX_TURNS_BEFORE_FORCE_FINALIZE:
        print(
            f"[agent] max turni raggiunto ({turn_count}>={MAX_TURNS_BEFORE_FORCE_FINALIZE}), force finalize.",
            flush=True,
        )
        return {"current_phase": "SYNTHESIZING"}

    history = state.get("messages") or []
    llm_messages: list[BaseMessage] = [SystemMessage(content=ANAMNESIS_SYSTEM_PROMPT)]
    llm_messages.extend(history)

    try:
        decision = _decide_copilot_action(llm_messages)
    except Exception as e:
        print(f"[agent] ERRORE LLM copilot: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return {
            "reply_to_send": (
                "Mi spiace, sto avendo un problema tecnico. Riprova tra qualche minuto."
            ),
            "current_phase": state.get("current_phase") or "COLLECTING_ANAMNESIS",
            "last_error": f"copilot_llm:{type(e).__name__}",
        }

    if decision.action == "finalize":
        return {"current_phase": "SYNTHESIZING"}

    reply = (decision.message_to_patient or "").strip()
    if not reply:
        reply = "Puoi descrivermi meglio cosa stai provando?"
    return {
        "messages": [AIMessage(content=reply)],
        "reply_to_send": reply,
        "current_phase": "COLLECTING_ANAMNESIS",
    }


def route_after_copilot(state: AgentState) -> str:
    if state.get("current_phase") == "SYNTHESIZING":
        return "clinical_synthesizer"
    return END


def node_clinical_synthesizer(state: AgentState) -> dict:
    """Produce il JSON strutturato per `richieste` e chiude la sessione."""
    history = state.get("messages") or []
    llm_messages: list[BaseMessage] = [SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT)]
    llm_messages.extend(history)

    try:
        synth = _synthesize_clinical(llm_messages)
    except Exception as e:
        print(f"[agent] ERRORE LLM synth: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return {
            "current_phase": "COLLECTING_ANAMNESIS",
            "reply_to_send": (
                "Sto avendo un problema a riassumere le tue informazioni. Riprova piu' tardi."
            ),
            "last_error": f"synth_llm:{type(e).__name__}",
        }

    synthesis_payload = synth.model_dump()

    # Indicizza la sintesi per il RAG dei futuri turni / visite successive.
    pid = state.get("paziente_id") or ""
    mid = state.get("medico_id") or ""
    msid = state.get("message_sid") or ""
    if pid and mid:
        synthesis_text = (
            f"Chief complaint: {synth.chief_complaint}\n\n"
            f"HPI: {synth.history_of_present_illness}\n\n"
            f"Farmaci citati: {', '.join(synth.medications) if synth.medications else '-'}\n\n"
            f"Red flags: {', '.join(synth.red_flags) if synth.red_flags else '-'}\n\n"
            f"Urgenza: {synth.livello_urgenza}\n"
            f"Sintesi: {synth.sintesi_medica}"
        )
        index_document(
            paziente_id=pid,
            medico_id=mid,
            source_type="richiesta_sintesi",
            source_id=msid or None,
            text=synthesis_text,
            metadata={
                "livello_urgenza": synth.livello_urgenza,
                "synthesized_at": _utcnow_iso(),
            },
        )

    closing_reply = (
        "Grazie. Ho preparato la sintesi per il medico, che ti rispondera' appena possibile."
    )
    return {
        "synthesis": synthesis_payload,
        "current_phase": "FINISHED",
        "reply_to_send": closing_reply,
        "messages": [AIMessage(content=closing_reply)],
    }


# --------------------------- build graph ---------------------------

def build_graph():
    """
    Topologia PR #4:

        START -> input_router --cond--> { vision_ocr | whisper_transcribe | retrieval }
        vision_ocr         -> retrieval
        whisper_transcribe -> retrieval
        retrieval          -> embed_and_index
        embed_and_index    -> anamnesis_copilot
        anamnesis_copilot --cond--> { END | clinical_synthesizer }
        clinical_synthesizer -> END

    `route_after_input` ritorna il valore "anamnesis_copilot" anche per la via
    testo, ma la conditional edge lo mappa a "retrieval" (entry point della
    pipeline RAG -> indexing -> copilot).
    """
    g = StateGraph(AgentState)
    g.add_node("input_router", node_input_router)
    g.add_node("vision_ocr", node_vision_ocr)
    g.add_node("whisper_transcribe", node_whisper_transcribe)
    g.add_node("retrieval", node_retrieval)
    g.add_node("embed_and_index", node_embed_and_index)
    g.add_node("anamnesis_copilot", node_anamnesis_copilot)
    g.add_node("clinical_synthesizer", node_clinical_synthesizer)

    g.add_edge(START, "input_router")
    g.add_conditional_edges(
        "input_router",
        route_after_input,
        {
            "vision_ocr": "vision_ocr",
            "whisper_transcribe": "whisper_transcribe",
            # via testo: salta direttamente alla pipeline RAG.
            "anamnesis_copilot": "retrieval",
        },
    )
    g.add_edge("vision_ocr", "retrieval")
    g.add_edge("whisper_transcribe", "retrieval")
    g.add_edge("retrieval", "embed_and_index")
    g.add_edge("embed_and_index", "anamnesis_copilot")
    g.add_conditional_edges(
        "anamnesis_copilot",
        route_after_copilot,
        {
            "clinical_synthesizer": "clinical_synthesizer",
            END: END,
        },
    )
    g.add_edge("clinical_synthesizer", END)

    return g.compile()


# Singleton: compiliamo una volta al boot del processo worker.
_COMPILED_GRAPH = None


def get_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_graph()
    return _COMPILED_GRAPH


# --------------------------- persistenza Supabase ---------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_session(paziente_id: str) -> tuple[str, dict]:
    """Carica `session_state, session_data` dalla riga pazienti."""
    if not supabase:
        return "IDLE", {}
    try:
        resp = (
            supabase.table("pazienti")
            .select("session_state, session_data")
            .eq("id", paziente_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            state = row.get("session_state") or "IDLE"
            data = row.get("session_data") or {}
            if not isinstance(data, dict):
                data = {}
            return state, data
    except Exception as e:
        print(f"[agent] ERRORE load_session({paziente_id}): {e}", flush=True)
        traceback.print_exc()
    return "IDLE", {}


def save_session(paziente_id: str, session_state: str, session_data: dict) -> None:
    if not supabase:
        return
    try:
        supabase.table("pazienti").update(
            {
                "session_state": session_state,
                "session_data": session_data,
                "session_updated_at": _utcnow_iso(),
            }
        ).eq("id", paziente_id).execute()
    except Exception as e:
        print(f"[agent] ERRORE save_session({paziente_id}): {e}", flush=True)
        traceback.print_exc()


def load_recent_conversation(
    paziente_id: str, limit: int = HISTORY_LIMIT
) -> list[BaseMessage]:
    """Carica gli ultimi N turni da `conversazioni` come BaseMessage langchain."""
    if not supabase:
        return []
    try:
        resp = (
            supabase.table("conversazioni")
            .select("role, content, created_at")
            .eq("paziente_id", paziente_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = list(reversed(resp.data or []))
    except Exception as e:
        print(f"[agent] ERRORE load_recent_conversation: {e}", flush=True)
        traceback.print_exc()
        return []

    out: list[BaseMessage] = []
    for row in rows:
        role = row.get("role")
        content = row.get("content")
        if not content:
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role in ("assistant_bot", "assistant_doctor"):
            out.append(AIMessage(content=content))
    return out


# --------------------------- entry-point chiamato dal worker ---------------------------

def run_for_job(payload: dict) -> dict:
    """
    Entry-point del worker. Sequenza per un job:
      1) risolve paziente_id/medico_id dal numero;
      2) carica session_state, session_data, storia da Supabase;
      3) invoca il grafo;
      4) se c'e' `reply_to_send`, lo manda via Twilio (e logga `assistant_bot`);
      5) se c'e' `synthesis`, fa INSERT su `richieste`;
      6) persiste current_phase + session_data su `pazienti`.

    Ritorna un dict di summary per i log del worker.
    """
    from_phone = (payload.get("from_number") or "").strip()
    body = payload.get("body") or ""
    media_url = payload.get("media_url_0") or ""
    media_ct = payload.get("media_content_type_0") or ""
    message_sid = payload.get("message_sid") or ""

    if not from_phone:
        return {"status": "error", "reason": "missing_from_number"}

    pid, mid, _nome = get_paziente_by_phone(from_phone)
    if not pid or not mid:
        return {"status": "error", "reason": "paziente_not_found", "from": from_phone}

    session_state, session_data = load_session(pid)
    history = load_recent_conversation(pid)

    initial_state: AgentState = {
        "paziente_id": pid,
        "medico_id": mid,
        "phone": from_phone,
        "message_sid": message_sid,
        "incoming_body": body,
        "incoming_media_url": media_url,
        "incoming_media_content_type": media_ct,
        "messages": history,
        "extracted_docs": list(session_data.get("extracted_docs") or []),
        "turn_count": int(session_data.get("turn_count") or 0),
        "current_phase": session_state or "IDLE",
        "reply_to_send": None,
        "synthesis": None,
        "needs_indexing": False,
        "last_error": None,
    }

    graph = get_graph()
    try:
        final_state: AgentState = graph.invoke(initial_state)
    except Exception as e:
        print(f"[agent] ERRORE invoke grafo: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return {"status": "error", "reason": "graph_invoke_failed", "detail": str(e)}

    reply = final_state.get("reply_to_send")
    synthesis = final_state.get("synthesis")
    new_phase = final_state.get("current_phase") or "COLLECTING_ANAMNESIS"

    sent_reply = False
    if reply:
        try:
            _send_whatsapp_reply_and_log(
                to_number=from_phone,
                text=reply,
                paziente_id=pid,
                medico_id=mid,
            )
            sent_reply = True
        except Exception as e:
            print(f"[agent] ERRORE invio reply: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    synthesis_inserted = False
    if synthesis:
        try:
            insert_richiesta(
                paziente_id=pid,
                medico_id=mid,
                messaggio_originale=body or synthesis.get("chief_complaint", ""),
                riassunto_clinico=synthesis.get("sintesi_medica"),
                urgenza=synthesis.get("livello_urgenza"),
                url_media=None,
            )
            synthesis_inserted = True
            _log_conversation_turn(
                paziente_id=pid,
                medico_id=mid,
                role="system",
                content=None,
                metadata={"event": "synthesis_inserted", "synthesis": synthesis},
            )
        except Exception as e:
            print(f"[agent] ERRORE insert_richiesta: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    new_session_data = {
        "extracted_docs": final_state.get("extracted_docs") or [],
        "turn_count": int(final_state.get("turn_count") or 0),
        "last_error": final_state.get("last_error"),
        "last_invocation_at": _utcnow_iso(),
    }
    save_session(pid, new_phase, new_session_data)

    return {
        "status": "ok",
        "paziente_id": pid,
        "phase": new_phase,
        "sent_reply": sent_reply,
        "synthesis_inserted": synthesis_inserted,
    }
