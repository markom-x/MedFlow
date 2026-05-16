-- Migrazione PR #1: log conversazionale, stato sessione paziente, idempotenza webhook.
-- Eseguire una tantum in Supabase SQL Editor (Settings -> SQL Editor) col ruolo postgres.
-- Additivo e idempotente: tutte le clausole sono IF NOT EXISTS, eseguibile piu' volte.
-- Reversibile con DROP TABLE/COLUMN. Nessun dato esistente viene modificato.
-- Dopo l'esecuzione il backend abilita automaticamente idempotenza e log turni;
-- prima dell'esecuzione il webhook continua a funzionare (gli helper failano silenziosamente).

ALTER TABLE public.pazienti
  ADD COLUMN IF NOT EXISTS session_state text NOT NULL DEFAULT 'IDLE',
  ADD COLUMN IF NOT EXISTS session_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS session_updated_at timestamptz NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS public.webhook_seen (
  message_sid text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.conversazioni (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paziente_id uuid NOT NULL REFERENCES public.pazienti(id) ON DELETE CASCADE,
  medico_id   uuid NOT NULL REFERENCES public.medici(id)   ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('user','assistant_bot','assistant_doctor','tool','system')),
  content text,
  url_media text,
  message_sid text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS conversazioni_paziente_created_idx
  ON public.conversazioni (paziente_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS conversazioni_message_sid_uidx
  ON public.conversazioni (message_sid) WHERE message_sid IS NOT NULL;

COMMENT ON COLUMN public.pazienti.session_state IS
  'Stato della macchina conversazionale agentica. Valori usati: IDLE, AWAITING_GDPR, COLLECTING_ANAMNESIS, WAITING_FOR_DOCS, SYNTHESIZING, FINISHED.';
COMMENT ON COLUMN public.pazienti.session_data IS
  'Stato libero dell agente per il paziente (slot raccolti, prossima domanda, ecc.). JSON arbitrario.';
COMMENT ON TABLE public.conversazioni IS
  'Sorgente di verita per la memoria dell agente. Una riga = un turno (paziente / bot / medico / tool).';
COMMENT ON TABLE public.webhook_seen IS
  'Idempotenza dei retry Twilio. Inserire MessageSid all inizio del webhook; conflict = duplicato, skip.';
