"use server";

import { STUDIO_MEDICO_ID } from "@/lib/dashboard/constants";
import type { RichiestaRow } from "@/lib/dashboard/types";
import { getSupabaseAuthServerClient } from "@/lib/supabase/auth-server";
import { getSupabaseServiceRoleClient } from "@/lib/supabase/server";

export type LoadDashboardResult =
  | { ok: true; rows: RichiestaRow[] }
  | { ok: false; message: string };

/**
 * Loads dashboard rows with the service role (bypasses RLS) after verifying
 * the user has a valid session. Scoped to the studio medico_id so the demo
 * account sees the same patients as the WhatsApp backend.
 */
export async function loadDashboardRichieste(): Promise<LoadDashboardResult> {
  const auth = await getSupabaseAuthServerClient();
  const {
    data: { user },
    error: userError,
  } = await auth.auth.getUser();

  if (userError || !user) {
    return { ok: false, message: "Invalid session. Please sign in again." };
  }

  try {
    const supabase = getSupabaseServiceRoleClient();
    const medicoId =
      process.env.MEDICO_STUDIO_ID?.trim() ||
      process.env.NEXT_PUBLIC_MEDICO_STUDIO_ID?.trim() ||
      STUDIO_MEDICO_ID;

    const { data, error } = await supabase
      .from("richieste")
      .select(
        `id, created_at, stato, urgenza, riassunto_clinico, messaggio_originale, url_media, paziente_id, dati_clinici,
         pazienti:paziente_id (id, nome, telefono, note_private)`
      )
      .eq("medico_id", medicoId)
      .order("created_at", { ascending: false })
      .limit(3000);

    if (error) {
      return { ok: false, message: error.message };
    }

    const rows = (data ?? []) as RichiestaRow[];
    return { ok: true, rows };
  } catch (e) {
    const msg =
      e instanceof Error ? e.message : "Could not load patient records.";
    if (msg.includes("SUPABASE_SERVICE_ROLE_KEY")) {
      return {
        ok: false,
        message:
          "Server misconfigured: add SUPABASE_SERVICE_ROLE_KEY on Vercel.",
      };
    }
    return { ok: false, message: msg };
  }
}
