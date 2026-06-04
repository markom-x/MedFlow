import type { SupabaseClient } from "@supabase/supabase-js";

import type { RichiestaRow } from "./types";

export async function fetchRichieste(
  supabase: SupabaseClient
): Promise<RichiestaRow[]> {
  const { data, error } = await supabase
    .from("richieste")
    .select(
      `id, created_at, stato, urgenza, riassunto_clinico, messaggio_originale, url_media, paziente_id, dati_clinici,
       pazienti:paziente_id (id, nome, telefono, note_private)`
    )
    .order("created_at", { ascending: false })
    .limit(3000);

  if (error) throw error;
  return (data ?? []) as RichiestaRow[];
}
