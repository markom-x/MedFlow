"use server";

import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";

export type FascicoloSource = {
  source_type: string | null;
  source_id: string | null;
  similarity: number | null;
  created_at: string | null;
  content: string | null;
};

export type QueryFascicoloResult =
  | { ok: true; answer: string; sources: FascicoloSource[] }
  | { ok: false; message: string };

/**
 * Interroga il fascicolo del paziente in linguaggio naturale.
 * Chiama il backend FastAPI server-side (no CORS, il token resta sul server):
 * il backend riusa il motore RAG dell'agent (embedding + match_anamnesi_documenti
 * + sintesi LLM ancorata alle fonti).
 *
 * Config server:
 * - MEDFLOW_API_URL: base URL del backend (default http://localhost:8000)
 * - MEDFLOW_INTERNAL_TOKEN: se settato, inviato come header X-MedFlow-Token
 */
export async function queryFascicolo(
  pazienteId: string,
  query: string
): Promise<QueryFascicoloResult> {
  const q = query.trim();
  if (!pazienteId || !q) {
    return { ok: false, message: "Inserisci una domanda." };
  }

  // Richiede una sessione dashboard valida (oltre al middleware).
  const auth = await getSupabaseAuthServerClient();
  const {
    data: { user },
    error: userError,
  } = await auth.auth.getUser();
  if (userError || !user) {
    return { ok: false, message: "Sessione non valida." };
  }

  const apiUrl = (process.env.MEDFLOW_API_URL || "http://localhost:8000").replace(
    /\/+$/,
    ""
  );
  const token = process.env.MEDFLOW_INTERNAL_TOKEN;

  try {
    const res = await fetch(`${apiUrl}/api/fascicolo/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-MedFlow-Token": token } : {}),
      },
      body: JSON.stringify({ paziente_id: pazienteId, query: q }),
      cache: "no-store",
    });

    if (!res.ok) {
      const detail = (await res.text().catch(() => "")).slice(0, 300);
      return {
        ok: false,
        message: `Consultazione non riuscita (${res.status}). ${detail}`.trim(),
      };
    }

    const data = (await res.json()) as {
      answer?: string;
      sources?: FascicoloSource[];
    };
    return {
      ok: true,
      answer: data.answer ?? "",
      sources: Array.isArray(data.sources) ? data.sources : [],
    };
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Errore di rete verso il backend MedFlow.";
    const unreachable =
      msg.includes("ECONNREFUSED") ||
      msg.includes("fetch failed") ||
      msg.includes("ENOTFOUND");
    return {
      ok: false,
      message: unreachable
        ? "Backend MedFlow non raggiungibile. Verifica MEDFLOW_API_URL."
        : msg,
    };
  }
}
