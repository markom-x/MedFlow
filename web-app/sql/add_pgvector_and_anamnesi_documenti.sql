-- Migrazione PR #4: pgvector + tabella anamnesi_documenti + RPC match_anamnesi_documenti.
-- Eseguire una tantum in Supabase SQL Editor col ruolo postgres.
-- Additivo e idempotente: IF NOT EXISTS / CREATE OR REPLACE. Rilanciabile.
-- Reversibile con DROP FUNCTION + DROP INDEX + DROP TABLE.
--
-- pgvector 0.7+ richiesto (HNSW). Supabase lo offre out-of-the-box dal 2024.
-- Senza questa migrazione i nodi node_retrieval / node_embed_and_index falliscono
-- silenziosamente (log + traceback, agent procede senza RAG) - retrocompatibile.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.anamnesi_documenti (
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

-- HNSW: meglio di ivfflat su dataset piccoli/incrementali, non richiede REINDEX
-- dopo gli insert. vector_cosine_ops perche' gli embedding di OpenAI sono
-- gia' L2-normalizzati e la cosine similarity e' la metrica naturale.
CREATE INDEX IF NOT EXISTS anamnesi_documenti_embedding_hnsw
  ON public.anamnesi_documenti
  USING hnsw (embedding vector_cosine_ops);

-- match_anamnesi_documenti: ricerca semantica per paziente. Filtra anche per
-- min_similarity (>= soglia configurabile dal client) per evitare match casuali
-- su tabelle quasi vuote. STABLE: il planner puo' inlining-are nelle CTE.
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

COMMENT ON TABLE public.anamnesi_documenti IS
  'Chunk + embeddings (text-embedding-3-small, 1536d) della storia clinica del paziente. Alimentata da OCR referti, sintesi richieste e (in futuro) conversazioni rilevanti. Consumata via match_anamnesi_documenti().';
COMMENT ON FUNCTION public.match_anamnesi_documenti(vector, uuid, int, float) IS
  'Ricerca semantica per paziente sui chunk di anamnesi_documenti. Cosine similarity, filtro min_similarity, ORDER BY distance + LIMIT.';
