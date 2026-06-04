"use server";

import type { PostgrestError } from "@supabase/supabase-js";
import twilio from "twilio";

import {
  MEDICO_FILE_SENT,
  MEDICO_MSG_PREFIX,
  STUDIO_MEDICO_ID,
} from "@/lib/dashboard/constants";
import { getSupabaseServiceRoleClient } from "@/lib/supabase/server";

export type SendDoctorMessageResult =
  | { ok: true }
  | { ok: false; message: string };

function whatsappTo(telefono: string): string {
  const t = telefono.trim();
  if (t.toLowerCase().startsWith("whatsapp:")) return t;
  return `whatsapp:${t}`;
}

function formatPostgrestError(err: PostgrestError): string {
  const parts = [err.message, err.details, err.hint].filter(
    (p): p is string => Boolean(p && String(p).trim())
  );
  return parts.length ? parts.join(" — ") : "Unknown database error.";
}

export type SendDoctorMessageInput = {
  pazienteId: string;
  numeroPaziente: string;
  testo: string;
  urlPubblico?: string | null;
};

/**
 * Flusso: validazione → Twilio API → INSERT Supabase (subito dopo Twilio) → ok.
 * Il messaggio medico è identificato in DB con il prefisso MEDICO_MSG_PREFIX su messaggio_originale.
 */
export async function sendDoctorMessage(
  input: SendDoctorMessageInput
): Promise<SendDoctorMessageResult> {
  const accountSid = process.env.TWILIO_ACCOUNT_SID;
  const authToken = process.env.TWILIO_AUTH_TOKEN;
  const fromNumber = process.env.TWILIO_PHONE_NUMBER;

  if (!accountSid || !authToken || !fromNumber) {
    return {
      ok: false,
      message:
        "Twilio is not configured on the server (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER).",
    };
  }

  const testo = input.testo.trim();
  const url = input.urlPubblico?.trim() || null;

  if (!testo && !url) {
    return { ok: false, message: "Type a message or add an attachment." };
  }

  const client = twilio(accountSid, authToken);
  const to = whatsappTo(input.numeroPaziente);

  try {
    await client.messages.create({
      from: fromNumber,
      to,
      body: testo || undefined,
      mediaUrl: url ? [url] : undefined,
    });
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Twilio error while sending the message.";
    return { ok: false, message: msg };
  }

  /* --- Right after Twilio: persist to "richieste" (service role) ---
     Doctor replies are chat bubbles only: we leave riassunto_clinico empty so
     they never override the AI clinical summary shown in the record. */
  const messaggio_originale = url
    ? testo
      ? `${MEDICO_MSG_PREFIX} ${testo}`
      : MEDICO_FILE_SENT
    : `${MEDICO_MSG_PREFIX} ${testo}`;

  const medicoId = process.env.MEDICO_STUDIO_ID?.trim() || STUDIO_MEDICO_ID;

  try {
    const supabase = getSupabaseServiceRoleClient();
    const { data, error } = await supabase
      .from("richieste")
      .insert({
        paziente_id: input.pazienteId,
        medico_id: medicoId,
        messaggio_originale,
        riassunto_clinico: "",
        urgenza: null,
        stato: "gestita",
        url_media: url,
      })
      .select("id")
      .single();

    if (error) {
      return {
        ok: false,
        message: `WhatsApp sent successfully, but saving to Supabase failed: ${formatPostgrestError(error)}${error.code ? ` (code: ${error.code})` : ""}`,
      };
    }

    if (!data?.id) {
      return {
        ok: false,
        message:
          "WhatsApp sent, but Supabase did not return the id of the inserted row.",
      };
    }
  } catch (e) {
    const hint =
      e instanceof Error &&
      e.message.includes("SUPABASE_SERVICE_ROLE_KEY")
        ? " Check SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL in your server-side .env.local."
        : "";
    const msg =
      e instanceof Error
        ? e.message
        : "Unexpected error during the INSERT into 'richieste'.";
    return {
      ok: false,
      message: `WhatsApp sent, but database: ${msg}.${hint}`,
    };
  }

  return { ok: true };
}

export type UpdatePatientNotesResult =
  | { ok: true }
  | { ok: false; message: string };

/**
 * Aggiorna le note private su `pazienti.note_private` (service role).
 */
export async function updatePatientPrivateNotes(
  pazienteId: string,
  notePrivate: string
): Promise<UpdatePatientNotesResult> {
  try {
    const supabase = getSupabaseServiceRoleClient();
    const { error } = await supabase
      .from("pazienti")
      .update({ note_private: notePrivate.trim() || null })
      .eq("id", pazienteId);

    if (error) {
      return {
        ok: false,
        message: `Failed to save notes: ${formatPostgrestError(error)}`,
      };
    }
    return { ok: true };
  } catch (e) {
    const msg =
      e instanceof Error
        ? e.message
        : "Error while updating the notes.";
    return {
      ok: false,
      message: msg.includes("SUPABASE_SERVICE_ROLE_KEY")
        ? `${msg} Configure SUPABASE_SERVICE_ROLE_KEY on the server.`
        : msg,
    };
  }
}
