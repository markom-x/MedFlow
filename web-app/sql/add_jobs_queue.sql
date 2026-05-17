-- Migrazione PR #2: coda jobs per decoupling del webhook dal limite Twilio 15s.
-- Eseguire una tantum in Supabase SQL Editor col ruolo postgres.
-- Additivo e idempotente: IF NOT EXISTS / CREATE OR REPLACE. Rilanciabile.
-- Reversibile con DROP FUNCTION + DROP TABLE.
-- Senza questa migrazione il webhook continua a funzionare in modalita sincrona
-- (fallback automatico quando l'enqueue fallisce).

CREATE TABLE IF NOT EXISTS public.jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL DEFAULT 'process_message',
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','processing','done','failed','dead')),
  attempts int NOT NULL DEFAULT 0,
  max_attempts int NOT NULL DEFAULT 5,
  payload jsonb NOT NULL,
  error text,
  message_sid text,
  created_at timestamptz NOT NULL DEFAULT now(),
  available_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);

CREATE INDEX IF NOT EXISTS jobs_pending_available_idx
  ON public.jobs (available_at)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS jobs_message_sid_idx
  ON public.jobs (message_sid)
  WHERE message_sid IS NOT NULL;

-- claim_one_job: prende il job pi\u00f9 vecchio in stato pending la cui available_at
-- e' nel passato, lo passa a 'processing', incrementa attempts. Concorrenza-safe
-- via FOR UPDATE SKIP LOCKED: piu' worker possono girare in parallelo.
CREATE OR REPLACE FUNCTION public.claim_one_job()
RETURNS SETOF public.jobs
LANGUAGE plpgsql
AS $$
DECLARE
  claimed_id uuid;
BEGIN
  SELECT id INTO claimed_id
  FROM public.jobs
  WHERE status = 'pending' AND available_at <= now()
  ORDER BY available_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED;

  IF claimed_id IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  UPDATE public.jobs
  SET status = 'processing',
      started_at = now(),
      attempts = attempts + 1
  WHERE id = claimed_id
  RETURNING *;
END;
$$;

COMMENT ON TABLE public.jobs IS
  'Coda dei job asincroni del webhook. Worker dedicato consuma con claim_one_job() (FOR UPDATE SKIP LOCKED). Status: pending -> processing -> done|failed|dead.';
COMMENT ON FUNCTION public.claim_one_job() IS
  'Estrae atomicamente un job pending pronto e lo passa a processing. Ritorna 0 o 1 riga.';
