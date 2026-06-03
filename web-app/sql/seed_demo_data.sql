-- Seed dati DEMO per la presentazione dell'MVP MedFlow.
--
-- Crea (in modo idempotente) un medico demo, un paziente demo con una storia
-- clinica ricca (conversazione multi-turno + richieste finalizzate con valori di
-- laboratorio) cosi' la dashboard non e' vuota e l'interrogazione del fascicolo
-- (RAG) ha subito qualcosa di concreto da "surfare".
--
-- IMPORTANTE:
--  - Il medico demo usa lo stesso id di STUDIO_MEDICO_ID
--    (web-app/lib/dashboard/constants.ts), cosi' l'attivazione del founder-paziente
--    ("Attivazione <id>") e le scritture della dashboard puntano allo stesso medico.
--  - Gli embedding NON si creano qui (servono chiamate OpenAI): dopo aver eseguito
--    questo seed, lancia `python backfill_index.py` per popolare anamnesi_documenti.
--
-- Eseguire una tantum in Supabase SQL Editor col ruolo postgres. Idempotente
-- (ON CONFLICT DO NOTHING su id fissi). Reversibile cancellando le righe con
-- questi id.
--
-- Prerequisiti: add_conversazioni_and_session_state.sql applicato.

-- 1) Medico demo. Se la tabella `medici` ha colonne NOT NULL aggiuntive (es. nome,
--    email), aggiungile qui. Di norma il medico dello studio esiste gia': in tal
--    caso l'INSERT e' un no-op.
INSERT INTO public.medici (id)
VALUES ('0aec5fee-921d-43bf-87b6-c4019182c742')
ON CONFLICT (id) DO NOTHING;

-- 2) Paziente demo (separato dal founder, che si attivera' col proprio numero).
INSERT INTO public.pazienti (id, nome, telefono, medico_id, gdpr_consent, session_state)
VALUES (
  'a1b2c3d4-0000-4000-8000-000000000001',
  'Giulia Bianchi',
  '+390000000001',
  '0aec5fee-921d-43bf-87b6-c4019182c742',
  true,
  'FINISHED'
)
ON CONFLICT (id) DO NOTHING;

-- 3) Conversazione multi-turno (sorgente per il RAG del fascicolo).
INSERT INTO public.conversazioni (id, paziente_id, medico_id, role, content, message_sid, created_at)
VALUES
  ('a1b2c3d4-0000-4000-8000-0000000000c1',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   'user',
   'Buongiorno dottore, da un paio di settimane mi sento molto stanca e senza forze, faccio fatica anche a salire le scale.',
   'SEED-MSG-001',
   now() - interval '3 days' - interval '40 minutes'),
  ('a1b2c3d4-0000-4000-8000-0000000000c2',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   'assistant_bot',
   'Mi dispiace Giulia. Oltre alla stanchezza ha notato altri sintomi, come mancanza di fiato, battito accelerato o pallore?',
   'SEED-MSG-002',
   now() - interval '3 days' - interval '38 minutes'),
  ('a1b2c3d4-0000-4000-8000-0000000000c3',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   'user',
   'Si, ogni tanto mi manca un po'' il fiato e mi vedo pallida. Ho fatto le analisi: emoglobina 10.1 g/dL e ferritina 8 ng/mL. Prendo solo acido folico.',
   'SEED-MSG-003',
   now() - interval '3 days' - interval '36 minutes'),
  ('a1b2c3d4-0000-4000-8000-0000000000c4',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   'assistant_bot',
   'Grazie, molto utile. Ha avuto perdite di sangue abbondanti, ciclo mestruale intenso o disturbi digestivi di recente?',
   'SEED-MSG-004',
   now() - interval '3 days' - interval '34 minutes'),
  ('a1b2c3d4-0000-4000-8000-0000000000c5',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   'user',
   'Il ciclo e'' sempre stato abbondante. Pressione a casa 125/80. Per il mal di testa ogni tanto prendo ibuprofene 400.',
   'SEED-MSG-005',
   now() - interval '3 days' - interval '32 minutes')
ON CONFLICT (id) DO NOTHING;

-- 4) Richieste (casi clinici finalizzati). La piu' recente con urgenza media
--    finisce in cima alla dashboard ("da gestire"). I valori di laboratorio nel
--    riassunto rendono ricca l'interrogazione del fascicolo.
INSERT INTO public.richieste
  (id, paziente_id, medico_id, created_at, stato, urgenza, riassunto_clinico, messaggio_originale, url_media)
VALUES
  ('a1b2c3d4-0000-4000-8000-0000000000a0',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '20 days',
   'gestita',
   'bassa',
   'Cefalea muscolo-tensiva ricorrente, gestibile in ambulatorio. Consigliata igiene del sonno e idratazione.',
   'Ho di nuovo mal di testa come le altre volte',
   NULL),
  ('a1b2c3d4-0000-4000-8000-0000000000a1',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days',
   'da gestire',
   'media',
   'Astenia e dispnea da sforzo da ~2 settimane. Esami: Hb 10.1 g/dL, ferritina 8 ng/mL (anemia sideropenica lieve-moderata). Menorragia anamnestica, uso saltuario di ibuprofene. PA 125/80. Verosimile carenza marziale: valutare supplementazione di ferro e approfondimento ginecologico.',
   'Sono molto stanca, le analisi mostrano emoglobina bassa',
   NULL)
ON CONFLICT (id) DO NOTHING;
