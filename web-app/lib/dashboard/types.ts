export type PazienteNested = {
  /** UUID testuale da Supabase */
  id: string;
  nome: string | null;
  telefono: string | null;
  note_private?: string | null;
};

export type ClinicalEntity = {
  description?: string | null;
  category?: string | null;
  source_reference?: { url?: string | null; page?: number | null } | null;
};

/** Structured AI synthesis stored in `richieste.dati_clinici` (jsonb). */
export type DatiClinici = {
  chief_complaint?: string | null;
  history_of_present_illness?: string | null;
  medications?: string[] | null;
  red_flags?: string[] | null;
  sintesi_medica?: string | null;
  clinical_entities?: ClinicalEntity[] | null;
};

export type RichiestaRow = {
  /** UUID testuale della riga `richieste` */
  id: string;
  created_at: string;
  stato: string | null;
  urgenza: string | null;
  riassunto_clinico: string | null;
  messaggio_originale: string | null;
  url_media: string | null;
  /** Structured AI synthesis (jsonb); present on summary rows. */
  dati_clinici?: DatiClinici | null;
  /** FK verso `pazienti` (utile se l'embed `pazienti` è assente ma la riga è leggibile). */
  paziente_id?: string | null;
  pazienti: PazienteNested | PazienteNested[] | null;
};

export type PatientProfile = {
  /** UUID testuale da `pazienti.id` */
  id: string;
  nomeRaw: string | null;
  nomeDisplay: string;
  telefono: string;
  /** Note interne (colonna note_private su pazienti) */
  notePrivate: string | null;
};
