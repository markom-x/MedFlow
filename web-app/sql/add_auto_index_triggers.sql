-- Migrazione PR #5: indicizzazione automatica e continua del fascicolo.
--
-- Ogni INSERT su `richieste` e `conversazioni` accoda un job `index_document`
-- nella coda `public.jobs` (gia' esistente, PR #2). Il worker lo consuma e
-- chiama `agent.index_job(payload)`, che embedda e indicizza la riga in
-- `anamnesi_documenti`. In questo modo la consultazione del fascicolo lato
-- medico "raggiunge" qualsiasi contenuto, da qualunque sorgente (webhook,
-- agente, dashboard del medico), senza backfill manuale.
--
-- Eseguire una tantum in Supabase SQL Editor col ruolo postgres.
-- Idempotente (DROP TRIGGER IF EXISTS + CREATE OR REPLACE). Rilanciabile.
-- Reversibile: DROP TRIGGER ... ; DROP FUNCTION public.enqueue_index_job();
--
-- Prerequisiti: add_jobs_queue.sql e fix_anamnesi_documenti_rebuild.sql applicati.

CREATE OR REPLACE FUNCTION public.enqueue_index_job()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO public.jobs (kind, payload)
  VALUES (
    'index_document',
    jsonb_build_object(
      'source_table', TG_TABLE_NAME,
      'source_id', NEW.id::text,
      'paziente_id', NEW.paziente_id::text,
      'medico_id', NEW.medico_id::text
    )
  );
  RETURN NEW;
END;
$$;

-- richieste: ogni nuova riga (caso clinico / messaggio) viene indicizzata.
DROP TRIGGER IF EXISTS trg_index_richieste ON public.richieste;
CREATE TRIGGER trg_index_richieste
  AFTER INSERT ON public.richieste
  FOR EACH ROW
  EXECUTE FUNCTION public.enqueue_index_job();

-- conversazioni: solo i turni con contenuto testuale utile (niente eventi di
-- sistema/tool a content nullo), per non sprecare embedding.
DROP TRIGGER IF EXISTS trg_index_conversazioni ON public.conversazioni;
CREATE TRIGGER trg_index_conversazioni
  AFTER INSERT ON public.conversazioni
  FOR EACH ROW
  WHEN (
    NEW.content IS NOT NULL
    AND NEW.role IN ('user', 'assistant_bot', 'assistant_doctor')
  )
  EXECUTE FUNCTION public.enqueue_index_job();

COMMENT ON FUNCTION public.enqueue_index_job() IS
  'Trigger AFTER INSERT su richieste/conversazioni: accoda un job index_document in public.jobs per l indicizzazione RAG asincrona del fascicolo.';
