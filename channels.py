"""
Astrazione di canale per l'EGRESS verso il paziente (PR A del piano omnicanale).

Il core agentico non deve sapere *come* il messaggio raggiunge il paziente:
chiama `deliver_to_patient(paziente_id, text)` e questo modulo risolve il canale
preferito e dispaccia all'adapter giusto. Oggi esiste un solo adapter
(WhatsApp/Twilio, che riusa `_send_whatsapp_reply_and_log` di main.py e logga il
turno in `conversazioni`). Domani si aggiungono in-app/PWA push, email, ecc.,
senza toccare l'agente.

Identita' del paziente: oggi il canale WhatsApp risolve il numero da
`pazienti.telefono`. Quando arrivera' il binding multi-canale (PR B, tabella
`paziente_canali`), basta cambiare `_resolve_channel_address` qui dentro.
"""
from __future__ import annotations

import os
import traceback

from main import _send_whatsapp_reply_and_log, supabase

# Canale di default finche' il binding multi-canale (PR B) non e' attivo.
DEFAULT_CHANNEL = os.getenv("MEDFLOW_DEFAULT_CHANNEL", "whatsapp")


def _resolve_patient_phone(paziente_id: str) -> str | None:
    """Numero WhatsApp del paziente da `pazienti.telefono`. None se assente."""
    if not supabase or not paziente_id:
        return None
    try:
        resp = (
            supabase.table("pazienti")
            .select("telefono")
            .eq("id", paziente_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            phone = (resp.data[0].get("telefono") or "").strip()
            return phone or None
    except Exception as e:
        print(
            f"[channels] ERRORE _resolve_patient_phone({paziente_id}): "
            f"{type(e).__name__}: {e}",
            flush=True,
        )
        traceback.print_exc()
    return None


def deliver_to_patient(
    paziente_id: str,
    text: str,
    medico_id: str | None = None,
    channel: str | None = None,
) -> dict:
    """
    Consegna `text` al paziente sul canale risolto. Non solleva: ritorna un dict
    di esito ({status: ok|error, channel, reason?}). Il logging del turno e' a
    carico dell'adapter (per WhatsApp lo fa `_send_whatsapp_reply_and_log`).
    """
    channel = (channel or DEFAULT_CHANNEL).strip().lower()
    text = (text or "").strip()
    if not paziente_id or not text:
        return {"status": "error", "channel": channel, "reason": "input_mancante"}

    if channel == "whatsapp":
        phone = _resolve_patient_phone(paziente_id)
        if not phone:
            return {"status": "error", "channel": channel, "reason": "telefono_mancante"}
        try:
            _send_whatsapp_reply_and_log(
                to_number=phone,
                text=text,
                paziente_id=paziente_id,
                medico_id=medico_id,
            )
            return {"status": "ok", "channel": channel}
        except Exception as e:
            print(
                f"[channels] ERRORE invio whatsapp: {type(e).__name__}: {e}",
                flush=True,
            )
            traceback.print_exc()
            return {"status": "error", "channel": channel, "reason": "send_failed"}

    # Adapter futuri: 'inapp' (PWA push / in-app), 'email', ...
    return {"status": "error", "channel": channel, "reason": f"canale_non_supportato:{channel}"}
