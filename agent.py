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
import difflib
import os
import re
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

import channels
from main import (
    download_twilio_media_requests,
    get_paziente_by_phone,
    insert_richiesta,
    patch_recent_inbound_richiesta_media,
    supabase,
    transcribe_audio_bytes_whisper,
    upload_bytes_to_supabase_bucket,
    upload_file_bytes_to_storage,
    _log_conversation_turn,
    _normalize_content_type,
    _storage_relative_path,
)


def _resolve_openai_client():
    """OpenAI client from main at call time.

    Do NOT import openai_client at module level: agent loads while main is still
    initializing, so the bound name would stay None even when OPENAI_API_KEY is set
    (health check on main.openai_client would still show true).
    """
    import main as main_mod

    return main_mod.openai_client

# --------------------------- config / costanti ---------------------------

# Bubble marker (doctor/right side, must match web-app MEDICO_MSG_PREFIX) used
# when the agent logs the clinical-summary turn into `richieste`. Keeping it a
# distinct marker avoids duplicating the patient's last message, which the
# webhook already bridges into the dashboard chat.
AGENT_SUMMARY_MARKER = "👨‍⚕️ You: 📋 Clinical summary updated"

# Passive intake assistant (product design): the AI NEVER interviews nor
# messages the patient. The doctor is the only one who talks to the patient
# (manually) and asks questions (via "Ask the record"). The patient just shares
# information and documents; the agent silently ingests/indexes everything and
# keeps the clinical summary fresh.

CHAT_MODEL = os.getenv("MEDFLOW_CHAT_MODEL", "gpt-4o")
VISION_MODEL = os.getenv("MEDFLOW_VISION_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("MEDFLOW_EMBEDDING_MODEL", "text-embedding-3-small")

# OCR PDF: cap pagine elaborate per contenere costi vision; soglia di caratteri
# sotto la quale una pagina e' considerata "scansionata" -> OCR vision.
PDF_MAX_PAGES = int(os.getenv("MEDFLOW_PDF_MAX_PAGES", "8"))
PDF_PAGE_MIN_TEXT_CHARS = int(os.getenv("MEDFLOW_PDF_PAGE_MIN_TEXT_CHARS", "40"))
PDF_RENDER_DPI = int(os.getenv("MEDFLOW_PDF_RENDER_DPI", "180"))
EMBEDDING_DIM = 1536  # text-embedding-3-small
MAX_TURNS_BEFORE_FORCE_FINALIZE = int(os.getenv("MEDFLOW_MAX_TURNS", "10"))
HISTORY_LIMIT = int(os.getenv("MEDFLOW_HISTORY_LIMIT", "30"))

# RAG knob
CHUNK_SIZE_CHARS = int(os.getenv("MEDFLOW_CHUNK_SIZE_CHARS", "1600"))
CHUNK_OVERLAP_CHARS = int(os.getenv("MEDFLOW_CHUNK_OVERLAP_CHARS", "200"))
RAG_TOP_K = int(os.getenv("MEDFLOW_RAG_TOP_K", "5"))
RAG_MIN_SIMILARITY = float(os.getenv("MEDFLOW_RAG_MIN_SIMILARITY", "0.5"))
RAG_MIN_QUERY_CHARS = int(os.getenv("MEDFLOW_RAG_MIN_QUERY_CHARS", "8"))
# Retrieval in-chat (dentro l'anamnesi): query costruita dalle ultime N battute
# del paziente (non solo l'ultima) e soglie piu' permissive, cosi' anche risposte
# brevi ("si", "da ieri") agganciano il contesto della conversazione. La
# precisione resta garantita dal prompt ancorato, non dalla soglia.
RAG_QUERY_TURNS = int(os.getenv("MEDFLOW_RAG_QUERY_TURNS", "3"))
RAG_QUERY_MAX_CHARS = int(os.getenv("MEDFLOW_RAG_QUERY_MAX_CHARS", "2000"))
RAG_CHAT_MIN_SIMILARITY = float(os.getenv("MEDFLOW_RAG_CHAT_MIN_SIMILARITY", "0.2"))
RAG_CHAT_MIN_QUERY_CHARS = int(os.getenv("MEDFLOW_RAG_CHAT_MIN_QUERY_CHARS", "2"))

# Consultazione del fascicolo lato medico (interrogazione in linguaggio naturale).
# Soglia piu' permissiva e top_k piu' alto rispetto al RAG interno dell'anamnesi:
# qui il medico fa query mirate e vogliamo recuperare piu' contesto pertinente.
FASCICOLO_TOP_K = int(os.getenv("MEDFLOW_FASCICOLO_TOP_K", "8"))
# Soglia bassa di proposito: la PRECISIONE non e' affidata a questo numero ma al
# prompt ancorato del synthesizer (risponde solo dal contesto, "non risulta" se
# il chunk non e' pertinente). Tenerla bassa migliora il RECALL sui sinonimi
# (es. "temperatura" ~0.24 vs "febbre" ~0.54) senza rischio di allucinazioni.
FASCICOLO_MIN_SIMILARITY = float(os.getenv("MEDFLOW_FASCICOLO_MIN_SIMILARITY", "0.2"))
# Soglia minima per la query del medico: piu' bassa del RAG interno dell'anamnesi
# (RAG_MIN_QUERY_CHARS=8, pensato per scartare "ok"/"si" nei turni paziente).
# Qui una parola singola e mirata ("febbre", "allergie", "hb") e' legittima.
FASCICOLO_MIN_QUERY_CHARS = int(os.getenv("MEDFLOW_FASCICOLO_MIN_QUERY_CHARS", "2"))
# Fascicolo QA: modello leggero e contesto limitato (meno timeout su Render).
FASCICOLO_CHAT_MODEL = os.getenv("MEDFLOW_FASCICOLO_CHAT_MODEL", "gpt-4o-mini")
FASCICOLO_MAX_CONTEXT_CHARS = int(
    os.getenv("MEDFLOW_FASCICOLO_MAX_CONTEXT_CHARS", "12000")
)

ANAMNESIS_SYSTEM_PROMPT = """You are a medical assistant conducting a pre-visit intake on
behalf of a General Practitioner. You speak to the patient over WhatsApp in English, in an
empathetic, clear and professional way. You are not the doctor: you do not diagnose and do
not prescribe.

Your goal: gather, in a few turns, the essential information the doctor needs, taking into
account ALL available context: the patient's previous messages, attached reports (OCR text
in messages flagged with a "[Referto allegato — OCR | fonte_documento: ...]" header), voice
note transcripts, and any prior clinical history injected as a system message by the RAG
system.

Each turn, choose one of two actions:
  - "ask": ONE focused, short, conversational question. Do not list, do not overload.
           Do not repeat questions already answered in earlier turns or in the reports:
           read first what the patient has already said/attached. Probe what is still
           missing for the doctor (e.g. duration, intensity, associated symptoms, current
           therapies, allergies).
  - "finalize": you have enough to hand the summary to the doctor. Finalize as soon as you
                have the main symptoms, duration, context and any obvious medications/red
                flags. Do not drag the conversation out: a few useful questions are better.

Rules:
- One question per turn. No long preambles.
- If the patient attached a report, integrate those values into your reasoning and, if
  needed, ask only for the missing clinical detail (do not ask for data already in the report).
- If you suspect red flags (chest pain, severe dyspnea, neurological deficits, hemorrhage,
  loss of consciousness, acute neurological symptoms), finalize immediately with urgency 'alta'.
- If the doctor has already stepped into the chat (doctor messages), do not contradict them.
- Never reveal PII of other patients, never invent clinical data.

ALWAYS respond with the required structured output, not free text.
""".strip()


SYNTHESIZER_SYSTEM_PROMPT = """You are MedFlow's clinical synthesis agent. From the ENTIRE
patient-bot conversation (and the doctor, if they stepped in), the attached reports (OCR
text) and the voice note transcripts, produce a structured summary for the doctor in
English. The doctor reads it in seconds: it must be accurate, dense and faithful.

Strict schema (the doctor dashboard reads these fields):
- chief_complaint: main reason for contact, one concise sentence.
- history_of_present_illness: history of the present illness. Include when relevant:
  onset and duration, course, triggering/relieving factors, associated symptoms, and the
  objective values present in the reports (e.g. "Hb 12.4 g/dL", "BP 150/95", "glucose
  180 mg/dL") with their units. Report the data, do not interpret it.
- medications: medications mentioned by the patient or in the reports (name + dose if any).
- red_flags: alarm signals that emerged; empty list if none.
- livello_urgenza: 'alta' | 'media' | 'bassa' (lowercase internal codes), consistent with
  the red flags. These are internal sorting codes, not shown to the doctor.
- sintesi_medica: 1-2 concise clinical sentences (max ~35 words) that orient the doctor at once.
- clinical_entities: list of the OBJECTIVE clinical entities that emerged (lab tests and
  their values, vital signs, remote/chronic conditions, medications, documented diagnoses).
  For each:
    * description: the concise datum with value and unit if present (e.g. "Hb 12.4 g/dL").
    * category: the datum type (e.g. 'esame_laboratorio', 'patologia_remota', 'farmaco', 'diagnosi').
    * source_reference: the documentary PROVENANCE. Attached reports reach you as messages
      flagged with a header like [Referto allegato — OCR | fonte_documento: <PATH> | content_type: <CT>]
      (for PDFs the text also contains [Pagina N] markers). When an entity derives from one of
      these reports, populate source_reference with:
        - url: EXACTLY the <PATH> value from the report's fonte_documento header you read the datum from;
        - page: the [Pagina N] number near the datum for multi-page PDFs, otherwise null.
      If instead the datum comes from the patient's text conversation or voice notes (not from
      an attached report), leave source_reference null. DO NOT invent URLs or page numbers.

Constraints:
- USE ONLY the information present in the conversation and the documents. DO NOT invent values,
  diagnoses or medications not mentioned. If a datum is unavailable, omit the field or leave it empty.
- Do not include PII (first name, last name, phone) in the summary.
""".strip()


FASCICOLO_QA_SYSTEM_PROMPT = """You are MedFlow's clinical-record consultation assistant.
A doctor asks you a question about the patient: answer USING EXCLUSIVELY the record excerpts
provided to you (OCR reports, summaries of previous visits, notes).

Rules:
- Do not invent and do not use knowledge outside the record. If the excerpts do not contain
  the answer, say so clearly ("Not found in the patient's record.").
- Report the relevant values and phrases as they appear in the record (e.g. lab values with
  their unit and date, if present).
- Answer in English, concise and clinical, without preambles.
- You are a consultation tool: do not formulate new diagnoses or prescriptions; you support
  the doctor's judgment.
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
    # Lista di TUTTI gli allegati del turno: [{"url", "content_type"}]. Su WhatsApp
    # e' tipicamente 0/1 elemento, ma il grafo e' pronto al multi-allegato.
    incoming_media: list[dict]

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
    # Documenti prodotti in QUESTO turno (OCR referti, trascrizioni vocali) da
    # indicizzare. Permette a embed_and_index di indicizzarli TUTTI, non solo
    # l'ultimo. Ogni elemento e' un doc come in extracted_docs + `index_source_type`.
    pending_index_docs: list[dict]

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


class SourceReference(BaseModel):
    """Provenienza documentale di un'entita' clinica ("Visual Provenance").

    `url` e' il riferimento all'allegato da cui il dato e' stato estratto: il
    path relativo nello storage Supabase (`{telefono}/{filename}`, bucket
    `referti`) oppure, in fallback, l'URL del media. Il frontend lo usa per
    aprire l'immagine/pagina esatta da cui l'AI ha letto il valore.
    `page` e' la pagina (1-based) per i PDF multipagina; None per immagini
    singole o quando la pagina non e' nota."""

    url: str = Field(
        description=(
            "Path storage Supabase ({telefono}/{filename}) o URL del referto "
            "allegato da cui proviene il dato."
        )
    )
    page: int | None = Field(
        default=None,
        description="Numero di pagina (1-based) per PDF multipagina; None per immagini singole.",
    )


class ClinicalEntity(BaseModel):
    """Singola entita' clinica oggettiva estratta (es. esame di laboratorio
    anomalo, valore vitale, patologia remota, farmaco), con il riferimento alla
    fonte documentale quando proviene da un referto allegato."""

    description: str = Field(
        description=(
            "Descrizione concisa dell'entita' clinica, con valore e unita' se "
            "presenti (es. 'Hb 12.4 g/dL', 'pregressa appendicectomia 2019')."
        )
    )
    category: str | None = Field(
        default=None,
        description=(
            "Entity type (English code): 'lab_test', 'past_condition', "
            "'medication', 'diagnosis', 'vital_sign'."
        ),
    )
    source_reference: SourceReference | None = Field(
        default=None,
        description=(
            "Fonte documentale del dato. Popolala SOLO se l'entita' deriva da un "
            "referto allegato (testo marcato [Referto ... | fonte_documento: ...]). "
            "Lascia null se il dato proviene dalla chat o dai vocali del paziente."
        ),
    )


class ClinicalSynthesis(BaseModel):
    """Output strutturato di `clinical_synthesizer`."""

    chief_complaint: str
    history_of_present_illness: str
    medications: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    livello_urgenza: Literal["alta", "media", "bassa"]
    sintesi_medica: str
    # Visual Provenance: entita' cliniche oggettive con riferimento alla fonte
    # documentale. `source_reference` valorizzato solo per dati estratti da
    # referti allegati; null per dati raccolti dalla conversazione/vocali.
    clinical_entities: list[ClinicalEntity] = Field(
        default_factory=list,
        description=(
            "Entita' cliniche oggettive emerse (esami, valori, patologie, farmaci). "
            "Per ognuna popola source_reference SOLO se proviene da un referto allegato."
        ),
    )


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
    client = _resolve_openai_client()
    if not client or not texts:
        return []
    try:
        resp = client.embeddings.create(
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


def _embedding_rpc_param(embedding: list[float]) -> str:
    """Formato pgvector per RPC PostgREST (alcune versioni rifiutano list[float])."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


def _count_anamnesi_chunks(paziente_id: str) -> int:
    if not supabase or not paziente_id:
        return 0
    try:
        resp = (
            supabase.table("anamnesi_documenti")
            .select("id", count="exact")
            .eq("paziente_id", paziente_id)
            .execute()
        )
        return int(resp.count or 0)
    except Exception as e:
        print(
            f"[agent] ERRORE _count_anamnesi_chunks: {type(e).__name__}: {e}",
            flush=True,
        )
        return 0


def _rpc_match_chunks(
    query_emb: list[float],
    paziente_id: str,
    top_k: int,
    min_similarity: float,
) -> list[dict]:
    """Chiama match_anamnesi_documenti; prova formato string pgvector se list fallisce."""
    if not supabase:
        return []
    payloads = [
        {"query_embedding": _embedding_rpc_param(query_emb), "match_paziente_id": paziente_id},
        {"query_embedding": query_emb, "match_paziente_id": paziente_id},
    ]
    last_err: Exception | None = None
    for base in payloads:
        try:
            resp = supabase.rpc(
                "match_anamnesi_documenti",
                {
                    **base,
                    "match_count": top_k,
                    "min_similarity": min_similarity,
                },
            ).execute()
            return list(resp.data or [])
        except Exception as e:
            last_err = e
    if last_err:
        print(
            f"[agent] ERRORE _rpc_match_chunks: {type(last_err).__name__}: {last_err}",
            flush=True,
        )
        traceback.print_exc()
    return []


def _keyword_fallback_chunks(
    paziente_id: str,
    query: str,
    top_k: int = FASCICOLO_TOP_K,
) -> list[dict]:
    """
    Fallback se la similarity search non restituisce nulla: cerca parole della
    domanda nel testo dei chunk gia' indicizzati (utile per termini corti o
    quando la RPC vector e' problematica).
    """
    if not supabase or not paziente_id:
        return []
    cleaned = (query or "").strip().lower()
    if not cleaned:
        return []
    words = [w for w in cleaned.replace("?", "").split() if len(w) >= 3]
    if not words:
        words = [cleaned[:40]]
    try:
        resp = (
            supabase.table("anamnesi_documenti")
            .select("id, source_type, source_id, chunk_index, content, created_at, metadata")
            .eq("paziente_id", paziente_id)
            .order("created_at", desc=True)
            .limit(80)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        print(
            f"[agent] ERRORE _keyword_fallback_chunks: {type(e).__name__}: {e}",
            flush=True,
        )
        return []

    scored: list[tuple[float, dict]] = []
    for row in rows:
        content = (row.get("content") or "").lower()
        if not content:
            continue
        hits = sum(1 for w in words if w in content)
        if hits <= 0:
            continue
        sim = hits / len(words)
        scored.append(
            (
                sim,
                {
                    **row,
                    "similarity": sim,
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


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
    min_query_chars: int = RAG_MIN_QUERY_CHARS,
) -> list[dict]:
    """
    Similarity search via RPC `match_anamnesi_documenti`. Ritorna lista di dict
    (id, source_type, content, similarity, ...). Empty list se non c'e' nulla
    o se qualcosa fallisce.

    `min_query_chars` e' configurabile: il path anamnesi usa la soglia alta di
    default, la consultazione del fascicolo lato medico ne passa una piu' bassa.
    """
    if not supabase or not paziente_id:
        if not supabase:
            print(
                "[agent] retrieve: client Supabase non inizializzato su questo "
                "servizio (SUPABASE_URL / SUPABASE service key mancanti?).",
                flush=True,
            )
        return []
    cleaned_query = (query or "").strip()
    if len(cleaned_query) < min_query_chars:
        return []
    query_emb = _embed_text(cleaned_query)
    if not query_emb:
        print(
            "[agent] retrieve: embedding della query fallito -> 0 risultati. "
            "Verifica OPENAI_API_KEY su QUESTO servizio (e' il web service "
            "'medflow-api' che risponde alle query, non il worker).",
            flush=True,
        )
        return []

    chunks = _rpc_match_chunks(query_emb, paziente_id, top_k, min_similarity)
    if not chunks and min_similarity > 0:
        chunks = _rpc_match_chunks(query_emb, paziente_id, top_k, 0.0)
        if chunks:
            print(
                f"[agent] retrieve: retry min_similarity=0 -> {len(chunks)} chunk.",
                flush=True,
            )
    return _filter_fascicolo_chunks(chunks)


def _filter_fascicolo_chunks(chunks: list[dict]) -> list[dict]:
    """Drop legacy bot interview lines that pollute doctor-facing search."""
    return [
        c
        for c in chunks
        if "[assistant_bot]" not in (c.get("content") or "").lower()
    ]


def _messages_to_openai_chat(messages: list[BaseMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": str(m.content)})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage):
            out.append({"role": "assistant", "content": str(m.content)})
    return out


# Lab / OCR synthesis for Ask the record (no LLM required).
_FASCICOLO_QUERY_TYPO_FIXES: dict[str, str] = {
    "hemoglbin": "hemoglobin",
    "haemoglibin": "hemoglobin",
    "hemoglobn": "hemoglobin",
    "temperture": "temperature",
    "temprature": "temperature",
}

_FASCICOLO_QUERY_VOCAB: tuple[str, ...] = (
    "hemoglobin",
    "haemoglobin",
    "hemoglobina",
    "emoglobina",
    "temperature",
    "body temperature",
    "fever",
    "amylase",
    "lipase",
    "glucose",
    "creatinine",
    "platelets",
    "crp",
    "alt",
    "wbc",
    "allergy",
    "allergies",
    "medication",
    "period",
    "periods",
)


def _fascicolo_canonicalize_query(query: str) -> str:
    """Fix common typos (e.g. hemoglbin) so retrieval and lab routing still work."""
    raw = (query or "").strip()
    if not raw:
        return raw
    parts: list[str] = []
    for token in re.split(r"(\s+)", raw):
        if not token.strip():
            parts.append(token)
            continue
        low = token.lower()
        if low in _FASCICOLO_QUERY_TYPO_FIXES:
            parts.append(_FASCICOLO_QUERY_TYPO_FIXES[low])
            continue
        if len(low) >= 4:
            match = difflib.get_close_matches(
                low, _FASCICOLO_QUERY_VOCAB, n=1, cutoff=0.72
            )
            if match:
                parts.append(match[0])
                continue
        parts.append(token)
    return "".join(parts)


def _dedupe_fascicolo_sources(
    sources: list[dict], *, limit: int = 3
) -> list[dict]:
    """One chip per (source_type, day) — avoids 8 identical Visit summary tags."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for s in sources:
        st = (s.get("source_type") or "source").strip()
        day = (s.get("created_at") or "")[:10]
        key = (st, day)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


# Lab / OCR synthesis for Ask the record (no LLM required).
_FASCICOLO_LAB_TESTS: list[tuple[str, str]] = [
    ("hemoglobin", "hemoglobin"),
    ("haemoglobin", "hemoglobin"),
    ("hgb", "hemoglobin"),
    ("hb ", "hemoglobin"),
    ("emoglobina", "hemoglobin"),
    ("serum amylase", "amylase"),
    ("amylase", "amylase"),
    ("amilasi", "amylase"),
    ("serum lipase", "lipase"),
    ("lipase", "lipase"),
    ("lipasi", "lipase"),
    ("white blood cells", "wbc"),
    ("wbc", "wbc"),
    ("leucociti", "wbc"),
    ("c-reactive protein", "crp"),
    ("crp", "crp"),
    ("proteina c reattiva", "crp"),
    ("alanine aminotransferase", "alt"),
    ("alt", "alt"),
    ("transaminasi", "alt"),
    ("glucose", "glucose"),
    ("glucosio", "glucose"),
    ("creatinine", "creatinine"),
    ("creatinina", "creatinine"),
    ("platelet", "platelets"),
    ("piastrine", "platelets"),
]


def _normalize_fascicolo_text(text: str) -> str:
    """Flatten LaTeX/OCR noise so numeric patterns are easier to match."""
    s = text or ""
    s = re.sub(r"\$\s*([^$]+?)\s*\$", r"\1", s)
    s = re.sub(r"\\text\{([^}]+)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\s*", " ", s)
    s = re.sub(r"[{}]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _extract_hemoglobin_reading(blob: str) -> str | None:
    """Value with unit when present (e.g. 10.1 g/dL)."""
    patterns = (
        r"(?:emoglobina|hemoglobin|haemoglobin|hgb)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(g/dL|g\/dl)",
        r"\bHb\s*(\d+(?:\.\d+)?)\s*(g/dL|g\/dl)",
        r"\bhb\s*(\d+(?:\.\d+)?)\s*(g/dL|g\/dl)",
        r"(?:emoglobina|hemoglobin)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(g/dL|g\/dl)",
    )
    for pat in patterns:
        m = re.search(pat, blob, re.I)
        if m:
            unit = (m.group(2) or "g/dL").replace("\\/", "/")
            return f"{m.group(1)} {unit}"
    m = re.search(
        r"(?:emoglobina|hemoglobin|hgb)\s*[:=]?\s*(\d+(?:\.\d+)?)",
        blob,
        re.I,
    )
    if m:
        return f"{m.group(1)} g/dL"
    return None


def _query_targets_lab_tests(query: str) -> set[str]:
    q = _normalize_fascicolo_text(
        _fascicolo_canonicalize_query(query or "").lower()
    )
    qwords = {w for w in re.split(r"\W+", q) if len(w) >= 2}
    targets: set[str] = set()
    for phrase, key in _FASCICOLO_LAB_TESTS:
        p = phrase.strip().lower()
        if p in q or (len(p) >= 3 and p.replace(" ", "") in q.replace(" ", "")):
            targets.add(key)
            continue
        if " " in p:
            continue
        if p in qwords or (len(p) >= 3 and p in q):
            targets.add(key)
    if qwords & {"lab", "labs", "laboratory", "test", "tests", "emoglobina"}:
        if "emoglobina" in qwords or "hemoglobin" in q or "hgb" in q:
            targets.add("hemoglobin")
    return targets


def _extract_lab_values_from_blob(blob: str) -> dict[str, list[str]]:
    """Map canonical test key -> list of numeric values (with units when found)."""
    normalized = _normalize_fascicolo_text(blob)
    lower = normalized.lower()
    out: dict[str, list[str]] = {}

    for phrase, key in _FASCICOLO_LAB_TESTS:
        if key in out and out[key]:
            continue
        idx = lower.find(phrase.strip().lower())
        if idx < 0:
            continue
        window = normalized[idx : idx + 700]
        raw_vals = re.findall(
            r"(\d+(?:\.\d+)?)\s*(?:U/L|mg/L|g/dL|mmol/L|/μL|×\s*10|10\^3)",
            window,
            re.I,
        )
        if not raw_vals:
            raw_vals = re.findall(
                r"(\d+(?:\.\d+)?)\s*(?:U/L|mg/L|g/dL)",
                window,
                re.I,
            )
        if not raw_vals:
            continue
        seen: set[str] = set()
        vals: list[str] = []
        for v in raw_vals[:4]:
            if v not in seen:
                seen.add(v)
                vals.append(v)
        if vals:
            out[key] = vals
    return out


def _format_lab_answer(test_key: str, values: list[str]) -> str:
    labels = {
        "hemoglobin": "Hemoglobin",
        "amylase": "Serum amylase",
        "lipase": "Serum lipase",
        "wbc": "White blood cell count (WBC)",
        "crp": "C-Reactive protein (CRP)",
        "alt": "ALT",
        "glucose": "Glucose",
        "creatinine": "Creatinine",
        "platelets": "Platelets",
    }
    name = labels.get(test_key, test_key.replace("_", " ").title())
    if len(values) >= 2:
        return f"{name}: admission {values[0]}, discharge {values[1]}."
    return f"{name}: {values[0]}."


def _fascicolo_synthesize_from_chunks(query: str, chunks: list[dict]) -> str | None:
    """
    Turn retrieved RAG chunks into a short English answer without GPT.
    Handles OCR lab tables (referto_ocr) and explicit negatives when a test
    is absent from the record.
    """
    if not chunks:
        return None

    blob_parts: list[str] = []
    has_ocr = False
    for c in chunks[:8]:
        content = (c.get("content") or "").strip()
        if not content:
            continue
        if (c.get("source_type") or "") == "referto_ocr":
            has_ocr = True
        blob_parts.append(content)
    blob = "\n".join(blob_parts)
    if not blob.strip():
        return None

    targets = _query_targets_lab_tests(query)
    labs = _extract_lab_values_from_blob(blob)

    if targets:
        lines: list[str] = []
        missing: list[str] = []
        for key in sorted(targets):
            if key == "hemoglobin":
                hb = _extract_hemoglobin_reading(blob)
                vals = [hb] if hb else list(labs.get(key) or [])
            else:
                vals = list(labs.get(key) or [])
            if vals:
                lines.append(_format_lab_answer(key, vals))
            else:
                missing.append(key)

        if lines:
            answer = " ".join(lines)
            if missing and has_ocr:
                avail = [
                    k
                    for k in ("amylase", "lipase", "wbc", "crp", "alt", "hemoglobin")
                    if labs.get(k)
                ]
                if avail:
                    pretty = ", ".join(
                        _format_lab_answer(k, labs[k]).split(":")[0] for k in avail[:5]
                    )
                    answer += (
                        f" No {missing[0].replace('_', ' ')} value appears in the "
                        f"indexed documents; other labs on file include: {pretty}."
                    )
            return answer

        if has_ocr and missing:
            avail = [
                _format_lab_answer(k, v)
                for k, v in labs.items()
                if v
            ][:5]
            if avail:
                return (
                    f"No {missing[0].replace('_', ' ')} value appears in the indexed "
                    f"record. From the uploaded clinical document: "
                    + "; ".join(avail)
                    + "."
                )

    # Generic: pull a short relevant snippet (not full excerpt dump).
    qwords = {w for w in re.split(r"\W+", (query or "").lower()) if len(w) >= 4}
    if qwords and has_ocr:
        norm = _normalize_fascicolo_text(blob)
        best_start = 0
        best_score = 0
        # Find window with most query word hits
        step = 80
        for i in range(0, max(1, len(norm) - 200), step):
            window = norm[i : i + 280].lower()
            score = sum(1 for w in qwords if w in window)
            if score > best_score:
                best_score = score
                best_start = i
        if best_score >= 1:
            snippet = norm[best_start : best_start + 320].strip()
            if len(snippet) > 40:
                return (
                    f"From the patient's indexed documents: …{snippet}… "
                    "(Ask a specific lab name for structured values.)"
                )

    return None


def _fascicolo_direct_answer(query: str, chunks: list[dict]) -> str | None:
    """
    Risposta immediata dai chunk RAG senza LLM: se il testo contiene gia' la
    risposta (es. messaggio paziente "my body temperature is 40"), la restituiamo
    in una frase. Evita dipendenza da OpenAI sul web service Render.
    """
    if not chunks:
        return None
    q = _fascicolo_canonicalize_query(query).strip().lower()
    qwords = {w for w in re.split(r"\W+", q) if len(w) >= 3}

    # --- body temperature / fever (prefer latest patient-reported value) ---
    canon_q = q
    if qwords & {"temperature", "temp", "fever", "febbr", "febvere"} or (
        "body" in canon_q and "temperature" in canon_q
    ):
        patient_temps: list[tuple[str, str, str]] = []
        summary_temps: list[tuple[str, str, str]] = []

        for c in chunks[:8]:
            created = (c.get("created_at") or "")[:19]
            content = (c.get("content") or "")
            for line in content.splitlines():
                line_s = line.strip()
                if not line_s:
                    continue
                ll = line_s.lower()
                is_patient_line = (
                    ("[paziente]" in ll or "[user]" in ll or ll.startswith("messaggio:"))
                    and "clinical summary" not in ll
                    and "sintesi clinica" not in ll
                )
                is_summary = "sintesi clinica" in ll or "clinical summary" in ll

                for pat in (
                    r"my body temperature is\s+(\d{2}(?:\.\d)?)",
                    r"body temperature(?:\s+is)?\s+(?:of\s+)?(\d{2}(?:\.\d)?)\s*°?\s*c",
                    r"febbre\s+(?:a\s+)?(\d{2}(?:\.\d)?)",
                    r"(?:bt|temp(?:erature)?)\s*[:=]?\s*(\d{2}(?:\.\d)?)\s*°?\s*c",
                    r"(\d{2}(?:\.\d)?)\s*°c",
                ):
                    for m in re.finditer(pat, line_s, re.I):
                        raw = m.group(1)
                        try:
                            v = float(raw)
                        except ValueError:
                            continue
                        if v < 34 or v > 45:
                            continue
                        disp = f"{raw}°C"
                        excerpt = re.sub(
                            r"^\[(?:paziente|user)\]\s*|^Messaggio:\s*",
                            "",
                            line_s,
                            flags=re.I,
                        ).strip()[:120]
                        row = (created, disp, excerpt)
                        if is_patient_line:
                            patient_temps.append(row)
                        elif is_summary:
                            summary_temps.append(row)

        patient_temps.sort(key=lambda x: x[0], reverse=True)
        summary_temps.sort(key=lambda x: x[0], reverse=True)

        if patient_temps:
            _ts, disp, excerpt = patient_temps[0]
            answer = (
                f"The most recent body temperature reported by the patient "
                f"is {disp}."
            )
            if excerpt and len(excerpt) > 8:
                answer += f' Context: "{excerpt}".'
            return answer

        if summary_temps:
            _ts, disp, _ex = summary_temps[0]
            return (
                f"The latest body temperature noted in the clinical summary "
                f"is {disp}."
            )

    # --- generic: best matching patient line ---
    best_line = ""
    best_score = 0
    for c in chunks[:6]:
        for line in (c.get("content") or "").splitlines():
            line_s = line.strip()
            if len(line_s) < 6:
                continue
            ll = line_s.lower()
            if "clinical summary updated" in ll or "sintesi clinica:" in ll[:30]:
                continue
            score = sum(1 for w in qwords if w in ll)
            if "[paziente]" in ll or "[user]" in ll:
                score += 3
            if ll.startswith("messaggio:") and "you:" not in ll[:20]:
                score += 2
            if score > best_score:
                best_score = score
                best_line = line_s

    if best_score >= 2 and best_line:
        clean = re.sub(r"^\[(?:paziente|user)\]\s*", "", best_line, flags=re.I)
        clean = re.sub(r"^Messaggio:\s*", "", clean, flags=re.I).strip()
        if clean and len(clean) < 500:
            return f"From the patient's record: {clean}"

    return None


def _fascicolo_compose_record_answer(query: str, chunks: list[dict]) -> str | None:
    """
    Builds a short English answer from patient messages + clinical summaries
    across all retrieved chunks (no LLM). Used before/alongside GPT synthesis.
    """
    if not chunks:
        return None
    synthesized = _fascicolo_synthesize_from_chunks(query, chunks)
    if synthesized:
        return synthesized
    temp = _fascicolo_direct_answer(query, chunks)
    if temp:
        return temp

    qwords = {w for w in re.split(r"\W+", (query or "").lower()) if len(w) >= 3}
    if not qwords:
        return None

    patient_quotes: list[str] = []
    summary_facts: list[str] = []

    for c in chunks[:10]:
        for line in (c.get("content") or "").splitlines():
            line_s = line.strip()
            if not line_s or "[assistant_bot]" in line_s.lower():
                continue
            ll = line_s.lower()
            if "sintesi clinica:" in ll:
                fact = line_s.split(":", 1)[-1].strip()
                if fact and any(w in fact.lower() for w in qwords):
                    if fact not in summary_facts:
                        summary_facts.append(fact[:300])
            elif "[paziente]" in ll or (
                ll.startswith("messaggio:") and "you:" not in ll[:24]
            ):
                clean = re.sub(
                    r"^\[(?:paziente|user)\]\s*|^Messaggio:\s*",
                    "",
                    line_s,
                    flags=re.I,
                ).strip()
                if clean and any(w in clean.lower() for w in qwords):
                    if clean not in patient_quotes:
                        patient_quotes.append(clean[:300])

    if not patient_quotes and not summary_facts:
        return None

    parts: list[str] = []
    if patient_quotes:
        parts.append(f'The patient reported: "{patient_quotes[0]}"')
    if summary_facts:
        parts.append(f"Clinical summary: {summary_facts[0]}")
    return "Based on the record — " + ". ".join(parts) + "."


def _fascicolo_excerpt_fallback(
    chunks: list[dict], query: str, *, llm_failed: bool = False
) -> str:
    """Last resort: prefer structured synthesis; never dump multi-page OCR."""
    composed = _fascicolo_synthesize_from_chunks(query, chunks)
    if composed:
        return composed
    composed = _fascicolo_compose_record_answer(query, chunks)
    if composed:
        return composed

    intro = (
        "I could not synthesize a full answer from the record right now."
        if llm_failed
        else "Here is a short excerpt from the record:"
    )
    lines = [intro, ""]
    c0 = chunks[0] if chunks else {}
    content = _normalize_fascicolo_text((c0.get("content") or "").strip())
    if content:
        st = c0.get("source_type") or "source"
        snippet = content[:500] + ("…" if len(content) > 500 else "")
        lines.append(f"({st}) {snippet}")
    return "\n".join(lines).strip()


def _truncate_fascicolo_context(context_block: str) -> str:
    if len(context_block) <= FASCICOLO_MAX_CONTEXT_CHARS:
        return context_block
    return (
        context_block[:FASCICOLO_MAX_CONTEXT_CHARS]
        + "\n\n[... additional excerpts omitted for length ...]"
    )


def _openai_chat_text(
    client,
    *,
    model: str,
    messages: list[dict],
    max_tokens: int = 600,
) -> str:
    """Chat completion via OpenAI SDK (no LangChain)."""
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _generate_fascicolo_answer_minimal(query: str, chunks: list[dict]) -> str:
    """Second-chance answer: 1–2 best chunks only, gpt-4o-mini, short output."""
    client = _resolve_openai_client()
    if not client or not chunks:
        return ""
    parts = []
    for c in chunks[:2]:
        content = (c.get("content") or "").strip()
        if content:
            parts.append(content[:2500])
    if not parts:
        return ""
    excerpt = "\n---\n".join(parts)
    try:
        return _openai_chat_text(
            client,
            model="gpt-4o-mini",
            max_tokens=250,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You answer a doctor's question using ONLY the patient "
                        "excerpt below. English, 1-3 sentences. If the excerpt "
                        "does not contain the answer, say it is not in the record."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nExcerpt:\n{excerpt}",
                },
            ],
        )
    except Exception as e:
        print(
            f"[agent] fascicolo minimal LLM fail: {type(e).__name__}: {e}",
            flush=True,
        )
        return ""


def _generate_fascicolo_answer(messages: list[BaseMessage]) -> str:
    """Risposta in linguaggio naturale sul fascicolo (OpenAI SDK, multi-model retry)."""
    client = _resolve_openai_client()
    if not client:
        llm = _get_chat_llm(temperature=0.0)
        resp = llm.invoke(messages)
        text = getattr(resp, "content", "")
        if isinstance(text, list):
            text = " ".join(
                part.get("text", "") for part in text if isinstance(part, dict)
            )
        return (text or "").strip()

    oai_messages = _messages_to_openai_chat(messages)
    models: list[str] = []
    for m in (FASCICOLO_CHAT_MODEL, CHAT_MODEL, "gpt-4o-mini"):
        if m and m not in models:
            models.append(m)

    last_err: Exception | None = None
    for model in models:
        try:
            text = _openai_chat_text(
                client, model=model, messages=oai_messages, max_tokens=600
            )
            if text:
                print(f"[agent] fascicolo LLM ok (model={model})", flush=True)
                return text
        except Exception as e:
            last_err = e
            print(
                f"[agent] fascicolo LLM fail model={model}: "
                f"{type(e).__name__}: {e}",
                flush=True,
            )
    if last_err:
        raise last_err
    return ""


def answer_fascicolo_query(paziente_id: str, query: str) -> dict:
    """
    Consultazione del fascicolo lato medico: data una domanda in linguaggio
    naturale, recupera i chunk pertinenti del paziente via RAG e produce una
    risposta ancorata SOLO a quel contesto, con l'elenco delle fonti.

    Ritorna sempre un dict serializzabile: {"answer": str, "sources": list[dict]}.
    Mai solleva: errori -> messaggio fallback + sources vuoto.
    """
    cleaned = (query or "").strip()
    if not paziente_id or len(cleaned) < FASCICOLO_MIN_QUERY_CHARS:
        return {
            "answer": "Please enter a more specific question to query the record.",
            "sources": [],
        }

    search_q = _fascicolo_canonicalize_query(cleaned)
    if search_q != cleaned:
        print(
            f"[agent] fascicolo: query normalized {cleaned!r} -> {search_q!r}",
            flush=True,
        )

    indexed_total = _count_anamnesi_chunks(paziente_id)
    if indexed_total == 0:
        print(
            f"[agent] fascicolo: 0 chunk in DB per paziente={paziente_id}, "
            "avvio backfill sincrono.",
            flush=True,
        )
        backfill_stats = backfill_fascicolo(paziente_id)
        indexed_total = _count_anamnesi_chunks(paziente_id)
        print(
            f"[agent] fascicolo backfill done stats={backfill_stats} "
            f"indexed_total={indexed_total}",
            flush=True,
        )

    chunks = retrieve_relevant_chunks(
        paziente_id,
        search_q,
        top_k=FASCICOLO_TOP_K,
        min_similarity=FASCICOLO_MIN_SIMILARITY,
        min_query_chars=FASCICOLO_MIN_QUERY_CHARS,
    )
    if not chunks and indexed_total > 0:
        chunks = _keyword_fallback_chunks(
            paziente_id, search_q, top_k=FASCICOLO_TOP_K
        )
        if chunks:
            print(
                f"[agent] fascicolo: keyword fallback -> {len(chunks)} chunk.",
                flush=True,
            )

    print(
        f"[agent] fascicolo query paziente={paziente_id} chars={len(cleaned)} "
        f"indexed_in_db={indexed_total} -> {len(chunks)} chunk recuperati.",
        flush=True,
    )
    if not chunks:
        if indexed_total == 0:
            return {
                "answer": (
                    "This patient's record has not been indexed yet (no searchable "
                    "documents in the database). Send a WhatsApp message or run "
                    "backfill_index.py, then try again."
                ),
                "sources": [],
            }
        return {
            "answer": (
                "I could not find anything in the patient's record that answers this "
                "question. Try rephrasing (e.g. include a symptom name or lab value)."
            ),
            "sources": [],
        }

    sources = _dedupe_fascicolo_sources(
        [
            {
                "source_type": c.get("source_type"),
                "source_id": c.get("source_id"),
                "similarity": round(float(c.get("similarity") or 0.0), 3),
                "created_at": c.get("created_at"),
                "content": (c.get("content") or "")[:400] or None,
            }
            for c in chunks
        ]
    )

    direct = _fascicolo_compose_record_answer(search_q, chunks)
    if direct:
        print("[agent] fascicolo: composed answer (no LLM).", flush=True)
        return {"answer": direct, "sources": sources}

    context_parts = []
    for i, c in enumerate(chunks, start=1):
        st = c.get("source_type") or "?"
        ts = c.get("created_at") or ""
        content = c.get("content") or ""
        context_parts.append(f"[Source {i} | {st} | {ts}]\n{content}")
    context_block = _truncate_fascicolo_context("\n\n".join(context_parts))

    messages: list[BaseMessage] = [
        SystemMessage(content=FASCICOLO_QA_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Doctor's question:\n{search_q}\n\n"
                f"Excerpts from the patient's record:\n{context_block}"
            )
        ),
    ]

    if not _resolve_openai_client():
        print(
            "[agent] fascicolo: OPENAI_API_KEY assente su QUESTO servizio "
            "(web service Render, non il worker). Uso estratti senza LLM.",
            flush=True,
        )
        direct = _fascicolo_compose_record_answer(search_q, chunks)
        if direct:
            return {"answer": direct, "sources": sources}
        answer = _fascicolo_excerpt_fallback(chunks, search_q, llm_failed=False)
        return {"answer": answer, "sources": sources}

    answer = ""
    try:
        answer = _generate_fascicolo_answer(messages)
    except Exception as e:
        print(
            f"[agent] ERRORE answer_fascicolo_query LLM: {type(e).__name__}: {e}",
            flush=True,
        )
        traceback.print_exc()

    if not answer:
        answer = _generate_fascicolo_answer_minimal(search_q, chunks)
        if answer:
            print("[agent] fascicolo: risposta da minimal LLM.", flush=True)

    if not answer:
        direct = _fascicolo_compose_record_answer(search_q, chunks)
        if direct:
            answer = direct
        else:
            answer = _fascicolo_excerpt_fallback(chunks, search_q, llm_failed=True)

    return {"answer": answer, "sources": sources}


# --------------------------- backfill: indicizza l'intero fascicolo ---------------------------

def _already_indexed_source_ids(paziente_id: str, source_type: str) -> set[str]:
    """source_id gia' presenti in anamnesi_documenti per (paziente, source_type).
    Rende il backfill idempotente: non re-indicizza cio' che c'e' gia'."""
    if not supabase or not paziente_id:
        return set()
    try:
        resp = (
            supabase.table("anamnesi_documenti")
            .select("source_id")
            .eq("paziente_id", paziente_id)
            .eq("source_type", source_type)
            .execute()
        )
        return {r["source_id"] for r in (resp.data or []) if r.get("source_id")}
    except Exception as e:
        print(
            f"[agent] ERRORE _already_indexed_source_ids: {type(e).__name__}: {e}",
            flush=True,
        )
        return set()


def _richiesta_to_text(row: dict) -> str:
    """Testo indicizzabile a partire da una riga `richieste`."""
    parts: list[str] = []
    summ = (row.get("riassunto_clinico") or "").strip()
    msg = (row.get("messaggio_originale") or "").strip()
    urg = (row.get("urgenza") or "").strip()
    if summ:
        parts.append(f"Sintesi clinica: {summ}")
    if msg:
        parts.append(f"Messaggio: {msg}")
    if urg:
        parts.append(f"Urgenza: {urg}")
    return "\n".join(parts).strip()


def backfill_fascicolo(paziente_id: str | None = None) -> dict:
    """
    Indicizza in `anamnesi_documenti` tutto il contenuto testuale gia' presente
    in `richieste` e `conversazioni`, cosi' la consultazione del fascicolo lato
    medico puo' "raggiungere" la storia esistente (non solo referti/sintesi
    prodotti dall'agent in avanti).

    - Idempotente: salta i source_id gia' indicizzati per quel paziente.
    - Se `paziente_id` e' None processa tutti i pazienti.
    - Best-effort: gli errori sono loggati, non sollevati.

    Ritorna statistiche di sintesi.
    """
    stats = {
        "richieste_indicizzate": 0,
        "conversazioni_indicizzate": 0,
        "chunk": 0,
        "saltate": 0,
    }
    if not supabase:
        stats["error"] = "supabase_non_configurato"
        return stats

    # ----- richieste -----
    try:
        q = supabase.table("richieste").select(
            "id, paziente_id, medico_id, messaggio_originale, riassunto_clinico, "
            "urgenza, created_at"
        )
        if paziente_id:
            q = q.eq("paziente_id", paziente_id)
        richieste = q.execute().data or []
    except Exception as e:
        print(f"[agent] ERRORE backfill select richieste: {e}", flush=True)
        richieste = []

    seen_ric: dict[str, set[str]] = {}
    for row in richieste:
        pid = str(row.get("paziente_id") or "")
        mid = str(row.get("medico_id") or "")
        rid = str(row.get("id") or "")
        if not pid or not mid or not rid:
            continue
        if pid not in seen_ric:
            seen_ric[pid] = _already_indexed_source_ids(pid, "richiesta_sintesi")
        if rid in seen_ric[pid]:
            stats["saltate"] += 1
            continue
        text = _richiesta_to_text(row)
        if not text:
            continue
        n = index_document(
            paziente_id=pid,
            medico_id=mid,
            source_type="richiesta_sintesi",
            source_id=rid,
            text=text,
            metadata={
                "backfill": True,
                "origine": "richieste",
                "urgenza": row.get("urgenza"),
                "created_at": row.get("created_at"),
            },
        )
        if n:
            stats["richieste_indicizzate"] += 1
            stats["chunk"] += n
            seen_ric[pid].add(rid)

    # ----- conversazioni -----
    try:
        q = supabase.table("conversazioni").select(
            "id, paziente_id, medico_id, role, content, created_at"
        )
        if paziente_id:
            q = q.eq("paziente_id", paziente_id)
        conversazioni = q.execute().data or []
    except Exception as e:
        print(f"[agent] ERRORE backfill select conversazioni: {e}", flush=True)
        conversazioni = []

    seen_conv: dict[str, set[str]] = {}
    for row in conversazioni:
        pid = str(row.get("paziente_id") or "")
        mid = str(row.get("medico_id") or "")
        cid = str(row.get("id") or "")
        content = (row.get("content") or "").strip()
        if not pid or not mid or not cid or not content:
            continue
        if pid not in seen_conv:
            seen_conv[pid] = _already_indexed_source_ids(pid, "conversazione")
        if cid in seen_conv[pid]:
            stats["saltate"] += 1
            continue
        role = row.get("role") or "?"
        n = index_document(
            paziente_id=pid,
            medico_id=mid,
            source_type="conversazione",
            source_id=cid,
            text=f"[{role}] {content}",
            metadata={
                "backfill": True,
                "origine": "conversazioni",
                "role": role,
                "created_at": row.get("created_at"),
            },
        )
        if n:
            stats["conversazioni_indicizzate"] += 1
            stats["chunk"] += n
            seen_conv[pid].add(cid)

    print(f"[agent] backfill_fascicolo completato: {stats}", flush=True)
    return stats


def index_job(payload: dict) -> dict:
    """
    Indicizzazione automatica di una singola riga, innescata da un trigger DB che
    accoda un job `index_document` su `public.jobs` ad ogni INSERT su
    `richieste`/`conversazioni`. Consumato dal worker.

    Payload atteso: {source_table, source_id, paziente_id, medico_id}.
    Idempotente: salta se il source_id e' gia' indicizzato. Best-effort: ritorna
    un dict di esito, e solleva solo via worker se status == 'error'.
    """
    if not supabase:
        return {"status": "error", "reason": "supabase_non_configurato"}

    source_table = (payload.get("source_table") or "").strip()
    source_id = str(payload.get("source_id") or "").strip()
    paziente_id = str(payload.get("paziente_id") or "").strip()
    if not source_table or not source_id or not paziente_id:
        return {"status": "error", "reason": "payload_incompleto"}

    if source_table == "richieste":
        source_type = "richiesta_sintesi"
    elif source_table == "conversazioni":
        source_type = "conversazione"
    else:
        return {"status": "error", "reason": f"source_table_sconosciuta:{source_table}"}

    # Idempotenza: non re-indicizzare.
    if source_id in _already_indexed_source_ids(paziente_id, source_type):
        return {"status": "skipped", "reason": "gia_indicizzato", "source_id": source_id}

    try:
        resp = (
            supabase.table(source_table)
            .select("*")
            .eq("id", source_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        print(f"[agent] ERRORE index_job fetch {source_table}: {e}", flush=True)
        traceback.print_exc()
        return {"status": "error", "reason": "fetch_failed"}

    if not rows:
        return {"status": "error", "reason": "row_non_trovata", "source_id": source_id}
    row = rows[0]
    mid = str(row.get("medico_id") or "")
    if not mid:
        return {"status": "error", "reason": "medico_id_mancante", "source_id": source_id}

    if source_table == "richieste":
        text = _richiesta_to_text(row)
        metadata = {
            "origine": "richieste",
            "urgenza": row.get("urgenza"),
            "created_at": row.get("created_at"),
        }
    else:  # conversazioni
        content = (row.get("content") or "").strip()
        if not content:
            return {"status": "skipped", "reason": "content_vuoto", "source_id": source_id}
        role = row.get("role") or "?"
        text = f"[{role}] {content}"
        metadata = {
            "origine": "conversazioni",
            "role": role,
            "created_at": row.get("created_at"),
        }

    if not text:
        return {"status": "skipped", "reason": "testo_vuoto", "source_id": source_id}

    n = index_document(
        paziente_id=paziente_id,
        medico_id=mid,
        source_type=source_type,
        source_id=source_id,
        text=text,
        metadata=metadata,
    )
    return {
        "status": "ok" if n else "error",
        "reason": None if n else "index_document_zero_chunk",
        "chunk": n,
        "source_id": source_id,
        "source_type": source_type,
    }


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


_OCR_PROMPT = (
    "Estrai integralmente il contenuto clinico del referto in italiano. "
    "Mantieni valori numerici, range di riferimento e diagnosi. "
    "NON aggiungere commenti. Solo testo estratto."
)


def _vision_ocr_image_bytes(img_bytes: bytes, content_type: str) -> str:
    """OCR di una singola immagine via GPT-4o vision. Usato sia per gli allegati
    immagine sia per le pagine PDF renderizzate a PNG."""
    try:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_url = f"data:{content_type};base64,{b64}"
        llm = ChatOpenAI(model=VISION_MODEL, temperature=0.0, timeout=60)
        msg = HumanMessage(
            content=[
                {"type": "text", "text": _OCR_PROMPT},
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


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Estrazione testo da PDF via PyMuPDF. Strategia ibrida per pagina:
    - se la pagina ha testo nativo (PDF digitale) lo usa direttamente (zero costo);
    - se la pagina e' scansionata (poco/niente testo) la renderizza a PNG e fa
      OCR vision.
    Cap a `PDF_MAX_PAGES` per contenere i costi. Solleva ImportError se PyMuPDF
    non e' installato (gestito dal chiamante)."""
    import fitz  # PyMuPDF; import lazy cosi' l'import del modulo non fallisce

    parts: list[str] = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        total = doc.page_count
        n_pages = min(total, PDF_MAX_PAGES)
        for i in range(n_pages):
            page = doc.load_page(i)
            native = (page.get_text() or "").strip()
            if len(native) >= PDF_PAGE_MIN_TEXT_CHARS:
                parts.append(f"[Pagina {i + 1}]\n{native}")
            else:
                pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
                png_bytes = pix.tobytes("png")
                ocr = _vision_ocr_image_bytes(png_bytes, "image/png")
                parts.append(f"[Pagina {i + 1} - OCR]\n{ocr}")
        if total > n_pages:
            parts.append(
                f"[...{total - n_pages} pagine ulteriori non elaborate (cap {PDF_MAX_PAGES})]"
            )
    finally:
        doc.close()
    return "\n\n".join(p for p in parts if p.strip()).strip()


def _vision_extract_text(file_bytes: bytes, content_type: str) -> str:
    """Estrae testo clinico da un allegato. Supporta `image/*` (vision) e
    `application/pdf` (PyMuPDF: testo nativo + OCR vision sulle pagine scansionate)."""
    ct = (content_type or "").lower().strip()

    if ct == "application/pdf":
        try:
            text = _extract_pdf_text(file_bytes)
            return text or "[PDF senza testo estraibile]"
        except ImportError:
            print("[agent] PyMuPDF non installato: impossibile leggere il PDF", flush=True)
            return (
                "[Referto PDF allegato — lettura PDF non disponibile (PyMuPDF mancante). "
                "Chiedi al paziente una foto della pagina rilevante.]"
            )
        except Exception as e:
            print(f"[agent] ERRORE lettura PDF: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            return f"[Errore lettura PDF: {type(e).__name__}]"

    if not ct.startswith("image/"):
        return f"[Allegato non interpretabile come immagine: {ct or 'sconosciuto'}]"

    return _vision_ocr_image_bytes(file_bytes, ct)


# --------------------------- nodi del grafo ---------------------------

def node_input_router(state: AgentState) -> dict:
    """Incrementa il turn_count. Il vero routing avviene nelle conditional edges."""
    return {"turn_count": int(state.get("turn_count") or 0) + 1}


def _incoming_media_list(state: AgentState) -> list[dict]:
    """Lista normalizzata degli allegati del turno. Usa `incoming_media` se
    presente, altrimenti ricostruisce dal singolo allegato legacy."""
    media = state.get("incoming_media")
    if media:
        return [m for m in media if (m or {}).get("url")]
    url = (state.get("incoming_media_url") or "").strip()
    if url:
        return [{"url": url, "content_type": state.get("incoming_media_content_type") or ""}]
    return []


def route_after_input(state: AgentState) -> str:
    media = _incoming_media_list(state)
    if not media:
        return "patient_intake"
    # Routing sul primo allegato (su WhatsApp ce n'e' uno solo per messaggio).
    ct = (media[0].get("content_type") or "").lower().strip()
    if ct.startswith("audio/"):
        return "whisper_transcribe"
    if ct.startswith("image/") or ct == "application/pdf":
        return "vision_ocr"
    # Allegato non audio/immagine/pdf: nessuna estrazione, va all'intake.
    return "patient_intake"


def node_vision_ocr(state: AgentState) -> dict:
    """Scarica il referto, fa OCR via GPT-4o vision, archivia su bucket `referti`
    e appende l'estratto allo stato + come HumanMessage cosi' il copilot lo vede."""
    phone = state.get("phone", "") or ""
    msid = state.get("message_sid", "") or ""

    # Elabora TUTTI gli allegati immagine/PDF del turno (multi-documento).
    media = [
        m
        for m in _incoming_media_list(state)
        if not (m.get("content_type") or "").lower().strip().startswith("audio/")
    ]
    if not media:
        return {}

    docs = list(state.get("extracted_docs") or [])
    pending: list[dict] = []
    new_messages: list[BaseMessage] = []

    for idx, item in enumerate(media):
        url = (item.get("url") or "").strip()
        ct_hint = item.get("content_type") or ""
        if not url:
            continue

        file_bytes, dl_ct, dl_cd = download_twilio_media_requests(url)
        if not file_bytes:
            new_messages.append(
                HumanMessage(content="[Referto inviato dal paziente: download fallito]")
            )
            continue

        ct_resolved = _normalize_content_type(dl_ct, ct_hint)
        # Path storage Supabase ({telefono}/{filename}, bucket `referti`): e' il
        # riferimento di provenienza ("Visual Provenance") che il frontend usa
        # per riaprire il referto esatto. Lo calcoliamo a prescindere dall'esito
        # dell'upload; in fallback usiamo l'URL del media.
        sid_for_path = f"{msid}-{idx}" if msid else msid
        try:
            object_path = _storage_relative_path(
                "referti", phone, ct_resolved, dl_cd, sid_for_path
            )
        except Exception as e:
            print(f"[agent] ERRORE path referto: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            object_path = None
        try:
            if object_path:
                upload_bytes_to_supabase_bucket(
                    "referti", object_path, file_bytes, ct_resolved
                )
        except Exception as e:
            print(f"[agent] ERRORE upload referto: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

        provenance_ref = object_path or url

        extracted_text = _vision_extract_text(file_bytes, ct_resolved)
        doc = {
            "source_url": url,
            "storage_path": object_path,
            # Riferimento canonico di provenienza per il synthesizer/frontend.
            "source_reference": provenance_ref,
            "content_type": ct_resolved,
            "extracted_text": extracted_text,
            "extracted_at": _utcnow_iso(),
            "index_source_type": "referto_ocr",
            "media_index": idx,
        }
        docs.append(doc)
        pending.append(doc)
        label = "Referto allegato — OCR" if len(media) == 1 else f"Referto {idx + 1} — OCR"
        # Header di provenienza inline cosi' il synthesizer puo' associare ogni
        # valore al documento (e alla pagina, via i marcatori [Pagina N] del PDF).
        header = f"[{label} | fonte_documento: {provenance_ref} | content_type: {ct_resolved}]"
        new_messages.append(HumanMessage(content=f"{header}\n{extracted_text}"))

    if not new_messages:
        return {"last_error": "vision_download_failed"}

    return {
        "extracted_docs": docs,
        "pending_index_docs": pending,
        "messages": new_messages,
        "needs_indexing": bool(pending),
    }


def node_whisper_transcribe(state: AgentState) -> dict:
    """Scarica l'audio, trascrive con Whisper, archivia su bucket `vocali`.
    Indicizza la trascrizione nel fascicolo: il contenuto vocale non finisce in
    `conversazioni` (il webhook logga Body vuoto per gli audio), quindi senza
    questo passaggio sarebbe invisibile al RAG."""
    phone = state.get("phone", "") or ""
    msid = state.get("message_sid", "") or ""

    # Primo allegato audio del turno.
    audio = next(
        (
            m
            for m in _incoming_media_list(state)
            if (m.get("content_type") or "").lower().strip().startswith("audio/")
        ),
        None,
    )
    url = (audio or {}).get("url") or state.get("incoming_media_url", "")
    ct_hint = (audio or {}).get("content_type") or state.get("incoming_media_content_type", "")

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

    docs = list(state.get("extracted_docs") or [])
    doc = {
        "source_url": url,
        "content_type": ct_resolved,
        "extracted_text": transcript.strip(),
        "extracted_at": _utcnow_iso(),
        "index_source_type": "conversazione",
    }
    docs.append(doc)
    return {
        "extracted_docs": docs,
        "pending_index_docs": [doc],
        "needs_indexing": True,
        "messages": [
            HumanMessage(content=f"[Vocale paziente — trascrizione]\n{transcript}")
        ],
    }


def _human_message_text(m: BaseMessage) -> str:
    """Testo di un HumanMessage (gestisce anche il formato multi-part vision)."""
    if not isinstance(m, HumanMessage):
        return ""
    content = m.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
    return ""


def _last_human_text(messages: list[BaseMessage]) -> str:
    """Estrae il testo dell'ultimo HumanMessage utile come query RAG."""
    for m in reversed(messages or []):
        text = _human_message_text(m)
        if text:
            return text
    return ""


def _recent_human_text(
    messages: list[BaseMessage],
    max_turns: int = RAG_QUERY_TURNS,
    max_chars: int = RAG_QUERY_MAX_CHARS,
) -> str:
    """Concatena le ultime `max_turns` battute del paziente per una query RAG piu'
    ricca: cosi' anche un "si"/"da ieri" eredita il contesto dei turni precedenti.
    Cap a `max_chars` per non gonfiare l'embedding con interi referti OCR."""
    collected: list[str] = []
    for m in reversed(messages or []):
        text = _human_message_text(m)
        if text:
            collected.append(text)
        if len(collected) >= max_turns:
            break
    collected.reverse()
    query = "\n".join(collected).strip()
    if len(query) > max_chars:
        query = query[-max_chars:]
    return query


def node_retrieval(state: AgentState) -> dict:
    """
    RAG: cerca chunk rilevanti nella storia del paziente e li inietta come
    SystemMessage nel contesto. No-op se non c'e' una query utile (es. primo
    turno con storia vuota) o se la tabella anamnesi_documenti non e' ancora
    popolata. Mai bloccante.
    """
    pid = state.get("paziente_id") or ""
    messages = state.get("messages") or []
    query = _recent_human_text(messages)
    if not pid or not query:
        return {}

    chunks = retrieve_relevant_chunks(
        pid,
        query,
        min_similarity=RAG_CHAT_MIN_SIMILARITY,
        min_query_chars=RAG_CHAT_MIN_QUERY_CHARS,
    )
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
            "Patient historical context (retrieved via RAG, use it ONLY if "
            "clinically relevant to the current conversation, do not repeat it "
            "verbatim to the patient):\n"
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
    Indicizza in `anamnesi_documenti` TUTTI i documenti prodotti in questo turno
    (OCR referti, trascrizioni vocali), non solo l'ultimo, per renderli
    retrievable nei turni futuri e nel fascicolo lato medico. Si attiva solo se
    un nodo a monte ha settato `needs_indexing=True`. Mai bloccante.
    """
    pid = state.get("paziente_id") or ""
    mid = state.get("medico_id") or ""
    msid = state.get("message_sid") or ""

    # Indicizzazione INLINE del testo del paziente: rende il messaggio
    # interrogabile dal fascicolo anche se il trigger DB di auto-index
    # (add_auto_index_triggers.sql) non e' stato applicato. Idempotente per
    # message_sid (source_id dedicato "-msg" per non collidere con gli allegati).
    body = (state.get("incoming_body") or "").strip()
    if pid and mid and len(body) >= 4:
        try:
            index_document(
                paziente_id=pid,
                medico_id=mid,
                source_type="conversazione",
                source_id=(f"{msid}-msg" if msid else None),
                text=f"[paziente] {body}",
                metadata={"origine": "chat_inline", "message_sid": msid},
            )
        except Exception as e:
            print(
                f"[agent] index inline testo paziente fallito: {type(e).__name__}: {e}",
                flush=True,
            )

    if not state.get("needs_indexing"):
        return {}

    # Indicizza i doc di questo turno; fallback all'ultimo doc per retro-compat.
    pending = state.get("pending_index_docs")
    if not pending:
        docs = state.get("extracted_docs") or []
        pending = [docs[-1]] if docs else []

    if not pid or not mid or not pending:
        return {"needs_indexing": False, "pending_index_docs": []}

    # Marker di errore / placeholder che NON vanno indicizzati.
    skip_prefixes = ("[Errore", "[Referto PDF", "[Allegato non interpretabile", "[OCR vuoto", "[PDF senza testo")

    multi = len(pending) > 1
    for i, doc in enumerate(pending):
        text = (doc.get("extracted_text") or "").strip()
        if not text or text.startswith(skip_prefixes):
            continue
        # source_id = message_sid per il caso singolo (retro-compat); suffisso
        # per-documento solo quando il turno porta piu' allegati.
        if not msid:
            source_id = None
        elif multi:
            source_id = f"{msid}-{doc.get('media_index', i)}"
        else:
            source_id = msid
        index_document(
            paziente_id=pid,
            medico_id=mid,
            source_type=doc.get("index_source_type") or "referto_ocr",
            source_id=source_id,
            text=text,
            metadata={
                "content_type": doc.get("content_type"),
                "source_url": doc.get("source_url"),
                "storage_path": doc.get("storage_path"),
                "source_reference": doc.get("source_reference"),
            },
        )
    return {"needs_indexing": False, "pending_index_docs": []}


def node_patient_intake(state: AgentState) -> dict:
    """
    Passive intake: the assistant is SILENT toward the patient. It never asks
    questions and never sends acknowledgments — the doctor is the only one who
    talks to the patient (manually, from the dashboard). The patient just
    uploads information/documents; here we only route to the synthesizer, which
    refreshes the clinical summary the doctor can query.
    """
    return {"current_phase": "SYNTHESIZING"}


def node_clinical_synthesizer(state: AgentState) -> dict:
    """
    Refresh the structured clinical summary from the full history (conversation
    + documents). Runs on every patient message. Does NOT send a reply to the
    patient (the intake node already acknowledged): the summary is for the
    doctor. The RAG indexing of the summary happens via the DB trigger on the
    `richiesta` inserted in `run_for_job`.
    """
    history = state.get("messages") or []
    llm_messages: list[BaseMessage] = [SystemMessage(content=SYNTHESIZER_SYSTEM_PROMPT)]
    llm_messages.extend(history)

    try:
        synth = _synthesize_clinical(llm_messages)
    except Exception as e:
        print(f"[agent] ERRORE LLM synth: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        # Keep the intake acknowledgment already set; just skip the summary.
        return {
            "current_phase": "FINISHED",
            "last_error": f"synth_llm:{type(e).__name__}",
        }

    synthesis_payload = synth.model_dump()
    return {
        "synthesis": synthesis_payload,
        "current_phase": "FINISHED",
    }


# --------------------------- build graph ---------------------------

def build_graph():
    """
    Topology (passive intake — the AI never interviews the patient):

        START -> input_router --cond--> { vision_ocr | whisper_transcribe | retrieval }
        vision_ocr         -> retrieval
        whisper_transcribe -> retrieval
        retrieval          -> embed_and_index
        embed_and_index    -> patient_intake
        patient_intake     -> clinical_synthesizer
        clinical_synthesizer -> END

    `route_after_input` returns "patient_intake" for the text path too, but the
    conditional edge maps it to "retrieval" (entry point of the
    RAG -> indexing -> intake -> summary pipeline).
    """
    g = StateGraph(AgentState)
    g.add_node("input_router", node_input_router)
    g.add_node("vision_ocr", node_vision_ocr)
    g.add_node("whisper_transcribe", node_whisper_transcribe)
    g.add_node("retrieval", node_retrieval)
    g.add_node("embed_and_index", node_embed_and_index)
    g.add_node("patient_intake", node_patient_intake)
    g.add_node("clinical_synthesizer", node_clinical_synthesizer)

    g.add_edge(START, "input_router")
    g.add_conditional_edges(
        "input_router",
        route_after_input,
        {
            "vision_ocr": "vision_ocr",
            "whisper_transcribe": "whisper_transcribe",
            # text path: jump straight to the RAG pipeline.
            "patient_intake": "retrieval",
        },
    )
    g.add_edge("vision_ocr", "retrieval")
    g.add_edge("whisper_transcribe", "retrieval")
    g.add_edge("retrieval", "embed_and_index")
    g.add_edge("embed_and_index", "patient_intake")
    g.add_edge("patient_intake", "clinical_synthesizer")
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

    # Lista allegati: preferisci `media` (multi-allegato), fallback al singolo
    # campo legacy per i job gia' in coda / retro-compatibilita'.
    incoming_media = payload.get("media")
    if not incoming_media and media_url:
        incoming_media = [{"url": media_url, "content_type": media_ct}]
    incoming_media = [m for m in (incoming_media or []) if (m or {}).get("url")]

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
        "incoming_media_url": media_url or (incoming_media[0]["url"] if incoming_media else ""),
        "incoming_media_content_type": media_ct
        or (incoming_media[0].get("content_type", "") if incoming_media else ""),
        "incoming_media": incoming_media,
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
        # Egress astratto (PR A): il canale lo risolve `channels`, non l'agente.
        delivery = channels.deliver_to_patient(
            paziente_id=pid,
            text=reply,
            medico_id=mid,
        )
        sent_reply = delivery.get("status") == "ok"
        if not sent_reply:
            print(f"[agent] invio reply non riuscito: {delivery}", flush=True)

    synthesis_inserted = False
    if synthesis:
        try:
            insert_richiesta(
                paziente_id=pid,
                medico_id=mid,
                messaggio_originale=AGENT_SUMMARY_MARKER,
                riassunto_clinico=synthesis.get("sintesi_medica"),
                urgenza=synthesis.get("livello_urgenza"),
                url_media=None,
                # Sintesi strutturata completa (incl. clinical_entities +
                # source_reference) cosi' il frontend puo' offrire il bottone
                # "apri referto" sulle entita' con provenienza documentale.
                dati_clinici=synthesis,
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

    for doc in final_state.get("extracted_docs") or []:
        sp = (doc.get("storage_path") or "").strip()
        if sp:
            patch_recent_inbound_richiesta_media(pid, sp)
            break

    return {
        "status": "ok",
        "paziente_id": pid,
        "phase": new_phase,
        "sent_reply": sent_reply,
        "synthesis_inserted": synthesis_inserted,
    }
