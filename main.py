import base64
import json
import mimetypes
import os
import re
import secrets
import tempfile
import time
import traceback
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import Response
from openai import OpenAI
from supabase import Client, create_client
from twilio.rest import Client as TwilioClient

load_dotenv()
print(f'DEBUG ENV: {os.getenv("SUPABASE_URL")}')

app = FastAPI(
    title="WhatsApp Twilio Webhook",
    description="MVP webhook per messaggi Twilio (Sandbox WhatsApp).",
)


@app.api_route("/", methods=["GET", "HEAD"])
def healthcheck_root() -> dict[str, str]:
    return {"status": "ok", "service": "MedFlow API"}


openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else None

supabase_url = os.getenv("SUPABASE_URL")
# Solo service role: la chiave anon non bypassa RLS e le INSERT dal webhook fallirebbero.
supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not supabase_service_role_key and os.getenv("SUPABASE_KEY"):
    print(
        "[config] SUPABASE_SERVICE_ROLE_KEY mancante: SUPABASE_KEY non viene usata qui "
        "(potrebbe essere anon). Imposta SUPABASE_SERVICE_ROLE_KEY su Render/.env.",
        flush=True,
    )
supabase: Client | None = (
    create_client(supabase_url, supabase_service_role_key)
    if supabase_url and supabase_service_role_key
    else None
)

# Twilio Content Template (GDPR) senza variabili.
GDPR_CONSENT_WHATSAPP_TEMPLATE_SID = "HXa9cb1f2bbffe1e2a078daf05ad19a956"


def _jwt_role_hint(key: str | None) -> str:
    """Legge il claim `role` dal JWT Supabase senza validare la firma (solo diagnostica log)."""
    if not key or "." not in key:
        return "sconosciuto"
    try:
        payload_b64 = key.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return str(payload.get("role", "mancante"))
    except Exception:
        return "non_decodificabile"


@app.on_event("startup")
def _log_startup_config() -> None:
    print("[startup] FastAPI avviato.", flush=True)
    if openai_client and openai_api_key:
        print("[startup] OpenAI client: OK (chiave presente).", flush=True)
    else:
        print("[startup] OpenAI client: NON configurato (OPENAI_API_KEY).", flush=True)
    if supabase and supabase_url and supabase_service_role_key:
        role = _jwt_role_hint(supabase_service_role_key)
        print(
            "[startup] Supabase client: OK (SUPABASE_SERVICE_ROLE_KEY presente, bypass RLS).",
            flush=True,
        )
        print(f"[startup] JWT role hint (diagnostica): {role}", flush=True)
        if role not in ("service_role",):
            print(
                "[startup] ATTENZIONE: la chiave non risulta service_role nel JWT — "
                "verifica di aver copiato la service_role da Supabase (Settings → API).",
                flush=True,
            )
    else:
        print(
            "[startup] Supabase: NON configurato (servono SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY).",
            flush=True,
        )

SYSTEM_PROMPT = """
You are a clinical data extractor and a strict privacy filter. You must completely ignore and discard any Personally Identifiable Information (PII) such as names, surnames, locations, or phone numbers that the user might mention in the text. Your output must contain ONLY the structured clinical JSON, stripped of any identity.
Sei un infermiere di triage esperto che assiste un Medico di Medicina Generale.
Il tuo compito è analizzare il messaggio del paziente ed estrarre i dati clinici in un formato JSON rigoroso.

REGOLE DI TRIAGE:
- ROSSO: Dolore toracico forte, difficoltà respiratoria (dispnea), perdita di coscienza, emorragie, deficit neurologici.
- GIALLO: Febbre alta (>39) persistente, dolori addominali forti, ferite, sintomi acuti in peggioramento.
- BIANCO/VERDE: Ricette per farmaci cronici, certificati, sintomi lievi, lettura referti.

DEVI RISPONDERE SOLO ED ESCLUSIVAMENTE CON UN OGGETTO JSON CON QUESTA STRUTTURA:
{
  "sintesi_medica": "Riassunto conciso in linguaggio clinico (max 20 parole)",
  "sintomi_chiave": ["sintomo1", "sintomo2"],
  "farmaci_citati": ["farmaco1"],
  "red_flags": ["segnali di allarme"],
  "is_richiesta_ricetta": true/false,
  "livello_urgenza": "ROSSO" | "GIALLO" | "VERDE"
}
"""


def _safe_list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _default_triage_output() -> dict:
    return {
        "sintesi_medica": None,
        "sintomi_chiave": [],
        "farmaci_citati": [],
        "red_flags": [],
        "is_richiesta_ricetta": False,
        "livello_urgenza": "GIALLO",
    }


def extract_fields_with_openai(message: str, from_number: str) -> dict:
    """
    Estrae JSON strutturato di triage clinico dal messaggio paziente.
    Ritorna sempre lo schema richiesto con fallback sicuro (urgenza GIALLO).
    """
    is_placeholder_key = bool(openai_api_key) and (
        "INSERISCI" in openai_api_key.upper() or "HERE" in openai_api_key.upper()
    )

    if not openai_client or is_placeholder_key:
        print("ERRORE: OPENAI_API_KEY mancante. Nessuna estrazione eseguita.")
        return _default_triage_output()

    if not message or not message.strip():
        return _default_triage_output()

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            response_format={"type": "json_object"},
            timeout=15,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Messaggio: {message}",
                },
            ],
        )
    except Exception as e:
        print(f"ERRORE: OpenAI chat.completions (triage): {e}", flush=True)
        traceback.print_exc()
        return _default_triage_output()

    content = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        print("ERRORE parsing JSON OpenAI: fallback default GIALLO.")
        return _default_triage_output()

    default_output = _default_triage_output()
    sintesi = parsed.get("sintesi_medica")
    if sintesi is not None:
        sintesi = str(sintesi).strip() or None

    livello_urgenza = str(parsed.get("livello_urgenza") or "").strip().upper()
    if livello_urgenza not in {"ROSSO", "GIALLO", "VERDE"}:
        livello_urgenza = "GIALLO"

    return {
        "sintesi_medica": sintesi,
        "sintomi_chiave": _safe_list_of_strings(parsed.get("sintomi_chiave")),
        "farmaci_citati": _safe_list_of_strings(parsed.get("farmaci_citati")),
        "red_flags": _safe_list_of_strings(parsed.get("red_flags")),
        "is_richiesta_ricetta": bool(parsed.get("is_richiesta_ricetta")),
        "livello_urgenza": livello_urgenza,
        # Compatibilità interna: valori pronti per colonne DB esistenti.
        "riassunto_clinico": sintesi or default_output["sintesi_medica"],
        "urgenza_db": livello_urgenza,
    }


def super_riassunto_vocale(transcript: str, from_number: str) -> str:
    """
    Genera un Super Riassunto strutturato (markdown) dalla trascrizione Whisper.
    """
    is_placeholder_key = bool(openai_api_key) and (
        "INSERISCI" in openai_api_key.upper() or "HERE" in openai_api_key.upper()
    )
    if not openai_client or is_placeholder_key:
        return f"🎤 **Trascrizione grezza**\n\n{transcript}"

    system_prompt = (
        "Sei un assistente per medici di medicina generale. "
        "Ricevi la trascrizione di un messaggio vocale WhatsApp del paziente. "
        "Produci un Super Riassunto in italiano, in markdown, con esattamente due sezioni con titoli di livello 2:\n"
        "## Cosa ha detto\n"
        "- elenco puntato sintetico di cosa comunica il paziente\n\n"
        "## Azione richiesta\n"
        "- elenco puntato di cosa chiede o di cosa serve al medico (es. ricetta, consiglio, urgenza)\n\n"
        "Sii conciso e clinico. Se mancano informazioni, indicalo nei bullet."
    )
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            timeout=30,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Trascrizione del vocale:\n{transcript}",
                },
            ],
        )
        out = (resp.choices[0].message.content or "").strip()
        return out if out else transcript
    except Exception as e:
        print(f"ERRORE Super Riassunto vocale: {e}")
        return f"🎤 **Trascrizione**\n\n{transcript}"


def _normalize_phone(phone: str | None) -> str:
    value = (phone or "").strip()
    if value.lower().startswith("whatsapp:"):
        value = value.split(":", 1)[1].strip()
    return value


def _normalize_person_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    return cleaned or None


def _is_generic_paziente_name(
    current_name: str | None,
    profile_name_guess: str | None = None,
) -> bool:
    normalized_current = (_normalize_person_name(current_name) or "").casefold()
    if not normalized_current:
        return True

    generic_values = {
        "paziente",
        "paziente whatsapp",
        "utente whatsapp",
        "utente",
        "whatsapp user",
    }
    if normalized_current in generic_values:
        return True

    normalized_profile = (_normalize_person_name(profile_name_guess) or "").casefold()
    if normalized_profile and normalized_current == normalized_profile:
        return True

    return False


def _can_auto_update_paziente_name(
    current_name: str | None,
    profile_name_guess: str | None = None,
) -> bool:
    # Evita overwrite dei nomi presumibilmente inseriti/manuali del medico.
    return _is_generic_paziente_name(current_name, profile_name_guess)


def _update_paziente_name_if_allowed(
    paziente_id: str,
    new_name: str | None,
    profile_name_guess: str | None = None,
    only_if_current_null: bool = False,
) -> bool:
    if not supabase:
        return False

    normalized_new_name = _normalize_person_name(new_name)
    if not normalized_new_name:
        return False

    try:
        current = (
            supabase.table("pazienti")
            .select("id, nome")
            .eq("id", paziente_id)
            .limit(1)
            .execute()
        )
        if not current.data:
            return False

        current_name = current.data[0].get("nome")
        normalized_current = _normalize_person_name(current_name)

        if only_if_current_null and normalized_current:
            return False
        if not only_if_current_null and not _can_auto_update_paziente_name(
            normalized_current, profile_name_guess
        ):
            return False
        if normalized_current and normalized_current.casefold() == normalized_new_name.casefold():
            return False

        updated = (
            supabase.table("pazienti")
            .update({"nome": normalized_new_name})
            .eq("id", paziente_id)
            .execute()
        )
        ok = bool(getattr(updated, "data", None))
        if ok:
            print(
                f"[DB] Nome paziente aggiornato automaticamente (id={paziente_id}, nome={normalized_new_name!r}).",
                flush=True,
            )
        return ok
    except Exception as e:
        print(f"ERRORE update nome paziente={paziente_id}: {e}", flush=True)
        traceback.print_exc()
        return False


def extract_patient_name_with_openai(message: str) -> str | None:
    """
    Se l'utente si presenta nel messaggio, estrae il nome; altrimenti ritorna None.
    """
    is_placeholder_key = bool(openai_api_key) and (
        "INSERISCI" in openai_api_key.upper() or "HERE" in openai_api_key.upper()
    )
    if not openai_client or is_placeholder_key:
        return None

    if not message or not message.strip():
        return None

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            timeout=10,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Estrai solo il nome proprio con cui l'utente si presenta nel messaggio. "
                        "Se non si presenta, restituisci null. "
                        "Rispondi solo con JSON valido nel formato: "
                        '{"nome": "Mario"} oppure {"nome": null}.'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Se l'utente si è presentato dicendo il suo nome, estrailo. "
                        "Altrimenti rispondi null.\n\n"
                        f"Messaggio: {message}"
                    ),
                },
            ],
        )
        content = resp.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return _normalize_person_name(parsed.get("nome"))
    except Exception as e:
        print(f"ERRORE estrazione nome con OpenAI: {e}", flush=True)
        return None


def _whatsapp_address(phone: str) -> str:
    p = phone.strip()
    if p.lower().startswith("whatsapp:"):
        return p
    return f"whatsapp:{p}"


def _send_whatsapp_reply(to_number: str, text: str) -> None:
    """
    Invia una risposta WhatsApp via Twilio REST API.
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    if not sid or not token or not from_number:
        print(
            "ERRORE: impossibile inviare risposta WhatsApp (TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_PHONE_NUMBER mancanti).",
            flush=True,
        )
        return

    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        payload = {
            "From": _whatsapp_address(from_number),
            "To": _whatsapp_address(to_number),
            "Body": text,
        }
        resp = requests.post(url, data=payload, auth=(sid, token), timeout=20)
        if resp.status_code >= 400:
            print(
                f"ERRORE invio WhatsApp reply Twilio: status={resp.status_code}, body={resp.text}",
                flush=True,
            )
            return
        print("TWILIO REPLY OK: messaggio inviato al paziente.", flush=True)
    except Exception as e:
        print(f"ERRORE invio WhatsApp reply Twilio: {e}", flush=True)
        traceback.print_exc()


def _send_whatsapp_template(to_number: str, template_sid: str):
    try:
        from_number = os.getenv("TWILIO_PHONE_NUMBER", "+447863789592")
        client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        message = client.messages.create(
            from_=from_number,
            to=to_number,
            content_sid=template_sid,
        )
        print(f"TWILIO TEMPLATE OK: SID {message.sid}", flush=True)
    except Exception as e:
        print("ERRORE invio WhatsApp template Twilio: ")
        traceback.print_exc()
        raise e


def _extract_activation_medico_id(text: str) -> str | None:
    """
    Estrae il codice da messaggi tipo:
    'Attivazione <uuid-medico>'
    """
    incoming = (text or "").strip()
    m = re.match(
        r"^attivazione\s+([0-9a-fA-F-]{32,40})",
        incoming,
        flags=re.IGNORECASE,
    )
    return m.group(1) if m else None


def _is_valid_uuid(value: str) -> bool:
    return bool(
        re.match(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
            value or "",
        )
    )


def _medico_exists(medico_id: str) -> bool:
    if not supabase:
        return False
    try:
        q = (
            supabase.table("medici")
            .select("id")
            .eq("id", medico_id)
            .limit(1)
            .execute()
        )
        return bool(q.data)
    except Exception as e:
        print(f"ERRORE verifica medico_id su tabella medici: {e}", flush=True)
        traceback.print_exc()
        return False


def _create_paziente_for_medico(phone: str, medico_id: str) -> tuple[str | None, str | None]:
    if not supabase:
        return None, None
    try:
        payload = {"telefono": phone, "medico_id": medico_id, "gdpr_consent": False}
        try:
            created = (
                supabase.table("pazienti")
                .insert(payload)
                .execute()
            )
        except Exception as e:
            # Se esistono colonne obbligatorie extra (es. nome), usiamo un default sicuro.
            print(f"ERRORE onboarding paziente (insert base): {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            payload_with_default_name = {
                "telefono": phone,
                "medico_id": medico_id,
                "nome": "Paziente WhatsApp",
                "gdpr_consent": False,
            }
            created = (
                supabase.table("pazienti")
                .insert(payload_with_default_name)
                .execute()
            )

        row = created.data[0] if getattr(created, "data", None) else {}
        pid = row.get("id")
        mid = row.get("medico_id")
        if pid and mid:
            print(f"[ONBOARDING] Paziente creato: id={pid}, medico_id={mid}", flush=True)
            return str(pid), str(mid)
    except Exception as e:
        print(f"ERRORE onboarding paziente: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    return None, None


def fetch_paziente_if_exists(
    from_number: str,
) -> tuple[str, str | None, bool] | None | Literal["error"]:
    """
    Solo SELECT: nessun insert. Ritorna la riga se esiste, None se non c'è paziente,
    \"error\" se la query fallisce (da non confondere con \"non collegato\").
    """
    if not supabase:
        print("ERRORE: Supabase non configurato (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY).", flush=True)
        return "error"

    try:
        existing = (
            supabase.table("pazienti")
            .select("id, medico_id, gdpr_consent")
            .eq("telefono", from_number)
            .limit(1)
            .execute()
        )
        if not existing.data:
            return None
        row = existing.data[0]
        pid = row.get("id")
        if not pid:
            return None
        medico_id = row.get("medico_id")
        gdpr_consent = bool(row.get("gdpr_consent"))
        return str(pid), (str(medico_id) if medico_id else None), gdpr_consent
    except Exception as e:
        print(f"ERRORE: fetch_paziente_if_exists: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return "error"


def set_paziente_gdpr_consent(paziente_id: str, consent_value: bool) -> bool:
    if not supabase:
        return False
    try:
        result = (
            supabase.table("pazienti")
            .update({"gdpr_consent": consent_value})
            .eq("id", paziente_id)
            .execute()
        )
        return bool(getattr(result, "data", None))
    except Exception as e:
        print(f"ERRORE update gdpr_consent paziente={paziente_id}: {e}", flush=True)
        traceback.print_exc()
        return False


def link_paziente_to_medico(
    from_number: str, medico_id: str
) -> tuple[str | None, str | None, bool]:
    """
    Collega (o crea) un paziente al medico e ritorna (paziente_id, medico_id, gdpr_consent).
    """
    if not supabase:
        return None, None, False
    try:
        existing = (
            supabase.table("pazienti")
            .select("id, gdpr_consent")
            .eq("telefono", from_number)
            .limit(1)
            .execute()
        )
        if existing.data:
            row = existing.data[0]
            paziente_id = row.get("id")
            gdpr_consent = bool(row.get("gdpr_consent"))
            updated = (
                supabase.table("pazienti")
                .update({"medico_id": medico_id})
                .eq("id", paziente_id)
                .execute()
            )
            if getattr(updated, "data", None):
                return str(paziente_id), str(medico_id), gdpr_consent
            return None, None, False

        payload = {
            "telefono": from_number,
            "medico_id": medico_id,
            "gdpr_consent": False,
        }
        try:
            created = supabase.table("pazienti").insert(payload).execute()
        except Exception:
            payload_with_default_name = {
                "telefono": from_number,
                "medico_id": medico_id,
                "nome": "Paziente WhatsApp",
                "gdpr_consent": False,
            }
            created = supabase.table("pazienti").insert(payload_with_default_name).execute()

        if created.data:
            row = created.data[0]
            return str(row.get("id")), str(row.get("medico_id")), bool(row.get("gdpr_consent"))
    except Exception as e:
        print(f"ERRORE link_paziente_to_medico: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
    return None, None, False


def get_paziente_by_phone(from_number: str) -> tuple[str | None, str | None, str | None]:
    if not supabase:
        print("ERRORE: Supabase non configurato (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY).", flush=True)
        return None, None, None

    try:
        print("[DB] Ricerca paziente per telefono…", flush=True)
        existing = (
            supabase.table("pazienti")
            .select("id, medico_id, gdpr_consent, nome")
            .eq("telefono", from_number)
            .limit(1)
            .execute()
        )
        if existing.data:
            pid = existing.data[0]["id"]
            medico_id = existing.data[0].get("medico_id")
            nome = existing.data[0].get("nome")
            print(f"[DB] Paziente esistente id={pid}", flush=True)
            return str(pid), (str(medico_id) if medico_id else None), _normalize_person_name(nome)

        print(
            f"WARNING: numero sconosciuto {from_number}. Nessun paziente trovato, salto inserimento richieste.",
            flush=True,
        )
        return None, None, None
    except Exception as e:
        print(f"ERRORE: Supabase get_paziente_by_phone: {e}", flush=True)
        traceback.print_exc()
        return None, None, None


def insert_richiesta(
    paziente_id: str,
    medico_id: str,
    messaggio_originale: str,
    riassunto_clinico: str | None,
    urgenza: str | None,
    url_media: str | None,
) -> None:
    if not supabase:
        print("ERRORE: Supabase non configurato (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY).", flush=True)
        return

    payload = {
        "paziente_id": paziente_id,
        "medico_id": medico_id,
        "messaggio_originale": messaggio_originale,
        "riassunto_clinico": riassunto_clinico,
        "urgenza": urgenza,
        "url_media": url_media,
    }
    try:
        print("[DB] Inizio salvataggio tabella richieste…", flush=True)
        result = supabase.table("richieste").insert(payload).execute()
        data = getattr(result, "data", None)
        if not data:
            print(
                f"ERRORE: insert richieste — risposta senza `data` (possibile errore PostgREST): {result!r}",
                flush=True,
            )
            return
        print(f"[DB] Salvataggio richieste completato. Righe: {len(data)}", flush=True)
        print("SALVATAGGIO SUPABASE OK: nuova richiesta inserita.", flush=True)
    except Exception as e:
        print(f"ERRORE: insert richieste — {type(e).__name__}: {e}", flush=True)
        for attr in ("message", "details", "hint", "code"):
            if hasattr(e, attr):
                val = getattr(e, attr)
                if val is not None and str(val).strip():
                    print(f"ERRORE:   {attr} = {val!r}", flush=True)
        traceback.print_exc()


def _extension_from_content_type(content_type: str) -> str:
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    if guessed:
        if guessed == ".jpe":
            return ".jpg"
        return guessed
    return ".bin"


def _filename_from_content_disposition(content_disposition: str | None) -> str | None:
    """Estrae filename dall'header Content-Disposition se presente."""
    if not content_disposition:
        return None
    cd = content_disposition.strip()
    m = re.search(r"filename\*=(?:UTF-8''|utf-8'')([^;]+)", cd, re.IGNORECASE)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename="([^"]+)"', cd)
    if m:
        return m.group(1)
    m = re.search(r"filename=([^;\s]+)", cd)
    if m:
        return m.group(1).strip('"')
    return None


def _sanitize_storage_basename(name: str) -> str:
    base = Path(name).name
    for ch in '\\/:*?"<>|':
        base = base.replace(ch, "_")
    return base.replace(" ", "_")


def _temp_suffix_for_audio(content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if "ogg" in ct or ct == "audio/opus":
        return ".ogg"
    if "oga" in ct:
        return ".oga"
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "wav" in ct:
        return ".wav"
    if "m4a" in ct or "mp4" in ct:
        return ".m4a"
    return ".ogg"


def transcribe_audio_bytes_whisper(file_bytes: bytes, content_type: str) -> str | None:
    """
    Trascrive bytes audio con Whisper usando un file temporaneo.
    """
    is_placeholder_key = bool(openai_api_key) and (
        "INSERISCI" in openai_api_key.upper() or "HERE" in openai_api_key.upper()
    )
    if not openai_client or is_placeholder_key:
        print("ERRORE: OpenAI client non disponibile o API key non valida per Whisper.")
        return None

    suffix = _temp_suffix_for_audio(content_type)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        text = getattr(transcript, "text", None)
        if text is not None:
            text = text.strip()
        return text if text else None
    except Exception as e:
        print(f"ERRORE trascrizione Whisper: {e}")
        return None
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as e:
                print(f"ERRORE rimozione file temporaneo audio: {e}")


def download_twilio_media_requests(
    media_url: str,
) -> tuple[bytes | None, str | None, str | None]:
    """
    Scarica i bytes del media da Twilio (MediaUrlN) con Basic Auth.
    Ritorna (content, Content-Type, Content-Disposition) o (None, None, None) in errore.
    """
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not twilio_sid or not twilio_token:
        print("ERRORE: TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN mancanti nel .env.")
        return None, None, None
    if not media_url or not str(media_url).strip():
        return None, None, None
    try:
        r = requests.get(
            str(media_url).strip(),
            auth=(twilio_sid, twilio_token),
            timeout=45,
            allow_redirects=True,
        )
        r.raise_for_status()
        ct = r.headers.get("Content-Type") or r.headers.get("content-type")
        cd = r.headers.get("Content-Disposition") or r.headers.get("content-disposition")
        return r.content, ct, cd
    except requests.RequestException as e:
        print(f"ERRORE download media Twilio (requests): {e}")
        return None, None, None


def _normalize_content_type(downloaded_ct: str | None, twilio_hint: str) -> str:
    """Preferisce il Content-Type della risposta; altrimenti il hint Twilio (MediaContentType0)."""
    ct = (downloaded_ct or "").split(";")[0].strip()
    if ct and ct.lower() != "application/octet-stream":
        return ct
    hint = (twilio_hint or "").split(";")[0].strip()
    return hint or "application/octet-stream"


def _unique_storage_object_name(
    bucket: str,
    content_type: str,
    content_disposition: str | None,
    message_sid: str,
) -> str:
    """Nome oggetto univoco: prefix + timestamp ms + parte MessageSid + estensione da tipo o filename."""
    extension = _extension_from_content_type(content_type)
    original = _filename_from_content_disposition(content_disposition)
    if original and Path(original).suffix:
        extension = Path(original).suffix.lower() or extension
    ts = int(time.time() * 1000)
    sid_raw = (message_sid or "").strip() or secrets.token_hex(4)
    sid_part = _sanitize_storage_basename(sid_raw)
    if len(sid_part) > 40:
        sid_part = sid_part[:40]
    prefix = "vocale_whatsapp" if bucket == "vocali" else "referto_whatsapp"
    return f"{prefix}_{ts}_{sid_part}{extension}"


def _storage_relative_path(
    bucket: str,
    from_number: str,
    content_type: str,
    content_disposition: str | None,
    message_sid: str,
) -> str:
    """
    Path relativo da salvare in DB (senza URL):
    `{telefono_paziente}/{filename}`.
    """
    patient_folder = _sanitize_storage_basename(_normalize_phone(from_number) or "paziente_sconosciuto")
    filename = _unique_storage_object_name(bucket, content_type, content_disposition, message_sid)
    return f"{patient_folder}/{filename}"


def _storage_bucket_for_content_type(content_type: str) -> str:
    """audio/* -> bucket vocali; immagini, PDF e altri allegati -> referti."""
    ct = (content_type or "").strip().lower()
    if ct.startswith("audio/"):
        return "vocali"
    return "referti"


def upload_bytes_to_supabase_bucket(
    bucket: str,
    object_path: str,
    file_bytes: bytes,
    content_type: str,
) -> str | None:
    """Carica su Storage e restituisce il path relativo (object_path), non un URL pubblico."""
    if not supabase:
        print("ERRORE: Supabase non configurato (SUPABASE_URL/SUPABASE_KEY).")
        return None
    if bucket not in {"referti", "vocali"}:
        print(f"ERRORE: bucket non consentito: {bucket}")
        return None
    try:
        supabase.storage.from_(bucket).upload(
            object_path,
            file_bytes,
            file_options={"content-type": content_type or "application/octet-stream"},
        )
        return object_path
    except Exception as e:
        print(f"ERRORE upload Supabase Storage (bucket={bucket}, path={object_path}): {e}")
        return None


def upload_file_bytes_to_storage(
    file_bytes: bytes,
    from_number: str,
    content_type: str,
    content_disposition: str | None,
    message_sid: str = "",
) -> str | None:
    """
    Sceglie vocali vs referti dal Content-Type, genera un path relativo
    e salva in DB SOLO quel path (bucket separato).
    """
    bucket = _storage_bucket_for_content_type(content_type)
    object_path = _storage_relative_path(
        bucket, from_number, content_type, content_disposition, message_sid
    )
    return upload_bytes_to_supabase_bucket(
        bucket, object_path, file_bytes, content_type
    )


def process_message(
    from_number: str,
    body: str,
    num_media: int = 0,
    media_url_0: str = "",
    media_content_type_0: str = "",
    message_sid: str = "",
    profile_name: str = "",
) -> None:
    """
    Elaborazione sincrona (no BackgroundTasks): su Render i task in background
    possono essere troncati allo shutdown del worker subito dopo il 200 OK.
    """
    print("[process_message] === INIZIO (sincrono) ===", flush=True)
    try:
        _process_message_impl(
            from_number,
            body,
            num_media,
            media_url_0,
            media_content_type_0,
            message_sid,
            profile_name,
        )
        print("[process_message] === FINE OK ===", flush=True)
    except Exception as e:
        print(f"ERRORE: process_message fatale: {e}", flush=True)
        traceback.print_exc()


def _process_message_impl(
    from_number: str,
    body: str,
    num_media: int = 0,
    media_url_0: str = "",
    media_content_type_0: str = "",
    message_sid: str = "",
    profile_name: str = "",
) -> None:
    message_text = body.strip() if body else ""
    uploaded_media_path = None
    media_url_clean = (media_url_0 or "").strip()
    from_phone = _normalize_phone(from_number)

    # Multi-tenant routing: il numero mittente deve esistere in `pazienti`.
    paziente_id, medico_id, current_nome = get_paziente_by_phone(from_phone)
    if paziente_id is None:
        print(
            f"[ROUTING] Mittente non censito ({from_phone}). Elaborazione terminata senza INSERT.",
            flush=True,
        )
        return
    if not medico_id:
        print(
            f"WARNING: paziente {paziente_id} senza medico_id associato. Salto inserimento richieste.",
            flush=True,
        )
        return

    if num_media > 0 and not media_url_clean:
        print(
            "ERRORE: NumMedia > 0 ma MediaUrl0 assente o vuoto: "
            "impossibile scaricare l'allegato da Twilio."
        )

    # Un solo download (requests) da MediaUrl0; bucket vocali vs referti dal tipo effettivo
    if num_media > 0 and media_url_clean:
        file_bytes, dl_ct, dl_cd = download_twilio_media_requests(media_url_clean)
        if file_bytes is None:
            message_text = message_text or "[Allegato - download da Twilio non riuscito]"
        else:
            ct_resolved = _normalize_content_type(dl_ct, media_content_type_0)
            is_audio = ct_resolved.strip().lower().startswith("audio/")

            if is_audio:
                uploaded_media_path = upload_file_bytes_to_storage(
                    file_bytes, from_phone, ct_resolved, dl_cd, message_sid
                )
                if uploaded_media_path:
                    print(
                        f"AUDIO CARICATO SU SUPABASE (bucket vocali), path={uploaded_media_path}",
                        flush=True,
                    )

                transcript_text = transcribe_audio_bytes_whisper(
                    file_bytes, media_content_type_0
                )
                if transcript_text:
                    message_text = super_riassunto_vocale(transcript_text, from_number)
                else:
                    message_text = message_text or "[Vocale - trascrizione non disponibile]"
            else:
                if not message_text:
                    message_text = "[Allegato Multimediale]"
                try:
                    object_path = _storage_relative_path(
                        "referti", from_phone, ct_resolved, dl_cd, message_sid
                    )
                    uploaded_media_path = upload_bytes_to_supabase_bucket(
                        "referti", object_path, file_bytes, ct_resolved
                    )
                    if uploaded_media_path:
                        print(
                            f"REFERTO CARICATO SU SUPABASE (bucket referti), path={uploaded_media_path}",
                            flush=True,
                        )
                    else:
                        print(
                            "ERRORE: upload su bucket referti non riuscito (vedi log Storage)."
                        )
                except Exception as e:
                    print(f"ERRORE upload media referti: {e}")

    print("[OpenAI] Inizio estrazione triage (GPT)…", flush=True)
    extracted_patient_name = extract_patient_name_with_openai(message_text)
    if extracted_patient_name:
        _update_paziente_name_if_allowed(
            paziente_id=paziente_id,
            new_name=extracted_patient_name,
            profile_name_guess=profile_name,
            only_if_current_null=False,
        )
    elif current_nome:
        print("[NOME] Nessun nome rilevato nel messaggio corrente.", flush=True)

    extracted = extract_fields_with_openai(message_text, from_number)
    print("[OpenAI] Estrazione triage completata.", flush=True)
    print("ESTRAZIONE GPT-4O-MINI (JSON)", flush=True)
    print(json.dumps(extracted, indent=2), flush=True)

    print("[DB] Inizio insert_richiesta con paziente/medico da record paziente…", flush=True)

    insert_richiesta(
        paziente_id=paziente_id,
        medico_id=medico_id,
        messaggio_originale=message_text,
        riassunto_clinico=extracted.get("riassunto_clinico"),
        urgenza=extracted.get("urgenza_db"),
        url_media=uploaded_media_path,
    )
    print("[DB] Flusso salvataggio richieste terminato.", flush=True)


@app.post("/webhook")
def twilio_webhook(
    From: str = Form(...),
    To: str = Form(default=""),
    Body: str = Form(default=""),
    NumMedia: int = Form(default=0),
    MediaUrl0: str = Form(default=""),
    MediaContentType0: str = Form(default=""),
    MessageSid: str = Form(default=""),
    ProfileName: str = Form(default=""),
) -> Response:
    print("🚨 RICEVUTO MESSAGGIO DA TWILIO! 🚨", flush=True)
    # Riceve il POST da Twilio (application/x-www-form-urlencoded).
    # OpenAI + Supabase in modo SINCRONO: su Render i BackgroundTasks spesso non completano
    # prima dello shutdown del worker dopo la risposta HTTP.
    separator = "=" * 72
    print(f"\n{separator}", flush=True)
    print("TWILIO WEBHOOK — NUOVO MESSAGGIO", flush=True)
    print(separator, flush=True)
    print(f"  Mittente (From): {From}", flush=True)
    print(f"  Destinatario (To): {To}", flush=True)
    print(f"  Messaggio (Body): {Body}", flush=True)
    print(f"  NumMedia: {NumMedia}", flush=True)
    if ProfileName:
        print(f"  ProfileName: {ProfileName}", flush=True)
    if NumMedia > 0:
        print(f"  MediaUrl0: {MediaUrl0}", flush=True)
        print(f"  MediaContentType0: {MediaContentType0}", flush=True)
    if MessageSid:
        print(f"  MessageSid: {MessageSid}", flush=True)
    print(f"{separator}\n", flush=True)

    from_phone = _normalize_phone(From)
    profile_name = _normalize_person_name(ProfileName)
    incoming_text = (Body or "").strip()
    twiml = "<Response></Response>"

    if not supabase:
        _send_whatsapp_reply(
            from_phone,
            "Errore temporaneo. Riprova tra poco o contatta il tuo medico.",
        )
        return Response(content=twiml, media_type="application/xml")

    # --- 1) Activation command ---
    # Testo che inizia con "attivazione" (case insensitive): estrai UUID medico, collega/crea paziente.
    if incoming_text.lower().startswith("attivazione"):
        activation_medico_id = _extract_activation_medico_id(incoming_text)
        if not activation_medico_id or not _is_valid_uuid(activation_medico_id):
            print(
                f"ERRORE attivazione: UUID mancante/non valido nel testo: {incoming_text!r}",
                flush=True,
            )
            _send_whatsapp_reply(
                from_phone,
                "Errore durante l'attivazione. Verifica che il codice sia corretto o contatta il medico.",
            )
            return Response(content=twiml, media_type="application/xml")

        if not _medico_exists(activation_medico_id):
            print(
                f"ERRORE attivazione: medico_id non trovato in tabella medici: {activation_medico_id}",
                flush=True,
            )
            _send_whatsapp_reply(
                from_phone,
                "Errore durante l'attivazione. Verifica che il codice sia corretto o contatta il medico.",
            )
            return Response(content=twiml, media_type="application/xml")

        linked_pid, linked_mid, linked_consent = link_paziente_to_medico(
            from_phone, activation_medico_id
        )
        if not linked_pid or not linked_mid:
            print(
                "ERRORE: attivazione richiesta ma link paziente-medico non riuscito.",
                flush=True,
            )
            _send_whatsapp_reply(
                from_phone,
                "Errore durante l'attivazione. Verifica che il codice sia corretto o contatta il medico.",
            )
            return Response(content=twiml, media_type="application/xml")

        if profile_name:
            _update_paziente_name_if_allowed(
                paziente_id=linked_pid,
                new_name=profile_name,
                profile_name_guess=profile_name,
                only_if_current_null=True,
            )

        if not linked_consent:
            _send_whatsapp_template(
                to_number=from_phone,
                template_sid=GDPR_CONSENT_WHATSAPP_TEMPLATE_SID
            )
            print(
                "[GDPR] Dopo attivazione: consenso mancante, template GDPR inviato e stop.",
                flush=True,
            )
            return Response(content=twiml, media_type="application/xml")

        _send_whatsapp_reply(from_phone, "Attivazione completata")
        return Response(content=twiml, media_type="application/xml")

    # --- 2) Not linked yet (nessun comando di attivazione) ---
    patient_row = fetch_paziente_if_exists(from_phone)
    if patient_row == "error":
        _send_whatsapp_reply(
            from_phone,
            "Errore temporaneo. Riprova tra poco o contatta il tuo medico.",
        )
        return Response(content=twiml, media_type="application/xml")

    if patient_row is None or not patient_row[1]:
        _send_whatsapp_reply(
            from_phone,
            "Benvenuto in MedFlow! Per iniziare, inviami il codice di attivazione che ti ha fornito il tuo medico.",
        )
        return Response(content=twiml, media_type="application/xml")

    paziente_id, medico_id, gdpr_consent = patient_row
    if profile_name:
        _update_paziente_name_if_allowed(
            paziente_id=paziente_id,
            new_name=profile_name,
            profile_name_guess=profile_name,
            only_if_current_null=True,
        )

    # --- 3) Pending GDPR (collegato ma consenso assente) ---
    if not gdpr_consent:
        if incoming_text.lower() == "accetto":
            updated = set_paziente_gdpr_consent(paziente_id, True)
            if updated:
                _send_whatsapp_reply(
                    from_phone,
                    "Grazie! Ora puoi scrivermi i tuoi sintomi.",
                )
            else:
                _send_whatsapp_reply(
                    from_phone,
                    "Errore durante la registrazione del consenso. Riprova.",
                )
            return Response(content=twiml, media_type="application/xml")

        _send_whatsapp_template(
            to_number=from_phone,
            template_sid=GDPR_CONSENT_WHATSAPP_TEMPLATE_SID
        )
        print(
            "[GDPR] Consenso mancante: template reinviato, messaggio non processato.",
            flush=True,
        )
        return Response(content=twiml, media_type="application/xml")

    # --- 4) Normal flow (AI / media) ---
    process_message(
        from_phone,
        Body,
        NumMedia,
        MediaUrl0,
        MediaContentType0,
        MessageSid,
        profile_name or "",
    )
    print("[webhook] Risposta TwiML 200 (routing standard completato).", flush=True)
    return Response(content=twiml, media_type="application/xml")

