-- Fix PR #5: ricostruzione di anamnesi_documenti + RPC match_anamnesi_documenti.
--
-- CONTESTO: su alcuni progetti Supabase esisteva gia' una tabella
-- `anamnesi_documenti` con uno schema RIDOTTO (solo id, paziente_id, content,
-- embedding, metadata, created_at). La migrazione del PR #4 usa
-- `CREATE TABLE IF NOT EXISTS`, quindi ha trovato la tabella preesistente e NON
-- l'ha aggiornata: mancavano `medico_id, source_type, source_id, chunk_index` e
-- la funzione `match_anamnesi_documenti` non risultava creata. Conseguenza:
--   - ogni index_document() falliva (colonne mancanti) -> tabella sempre vuota;
--   - retrieve_relevant_chunks() falliva (RPC assente) -> "nessun risultato".
--
-- SICURO: la tabella e' VUOTA (0 righe), quindi la ricostruiamo da zero per
-- garantire lo schema canonico (vincoli, default, FK, indici, RPC).
-- Eseguire una tantum in Supabase SQL Editor col ruolo postgres.
-- Idempotente e rilanciabile.

CREATE EXTENSION IF NOT EXISTS vector;

-- Rimuove la RPC eventuale (qualsiasi firma legacy) e la tabella mal-formata.
DROP FUNCTION IF EXISTS public.match_anamnesi_documenti(vector, uuid, int, float);
DROP TABLE IF EXISTS public.anamnesi_documenti CASCADE;

CREATE TABLE public.anamnesi_documenti (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paziente_id uuid NOT NULL REFERENCES public.pazienti(id) ON DELETE CASCADE,
  medico_id   uuid NOT NULL REFERENCES public.medici(id)   ON DELETE CASCADE,
  source_type text NOT NULL
    CHECK (source_type IN ('referto_ocr','conversazione','richiesta_sintesi','manuale')),
  source_id text,
  chunk_index int NOT NULL DEFAULT 0,
  content text NOT NULL,
  embedding vector(1536),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS anamnesi_documenti_paziente_created_idx
  ON public.anamnesi_documenti (paziente_id, created_at);

CREATE INDEX IF NOT EXISTS anamnesi_documenti_source_idx
  ON public.anamnesi_documenti (paziente_id, source_type, source_id);

CREATE INDEX IF NOT EXISTS anamnesi_documenti_embedding_hnsw
  ON public.anamnesi_documenti
  USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE FUNCTION public.match_anamnesi_documenti(
  query_embedding vector(1536),
  match_paziente_id uuid,
  match_count int DEFAULT 5,
  min_similarity float DEFAULT 0.5
)
RETURNS TABLE (
  id uuid,
  source_type text,
  source_id text,
  chunk_index int,
  content text,
  similarity float,
  metadata jsonb,
  created_at timestamptz
)
LANGUAGE sql STABLE
AS $$
  SELECT
    id,
    source_type,
    source_id,
    chunk_index,
    content,
    1 - (embedding <=> query_embedding) AS similarity,
    metadata,
    created_at
  FROM public.anamnesi_documenti
  WHERE paziente_id = match_paziente_id
    AND embedding IS NOT NULL
    AND 1 - (embedding <=> query_embedding) >= min_similarity
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Forza il reload della schema cache di PostgREST (altrimenti l'API
-- continua a non "vedere" la RPC fino al refresh automatico).
NOTIFY pgrst, 'reload schema';
