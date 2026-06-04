-- DEMO seed data for the MedFlow MVP presentation.
--
-- Idempotently creates a demo doctor and a demo patient with a rich, realistic
-- WhatsApp conversation PLUS a finalized AI clinical summary. Everything the
-- founder sees is in English.
--
-- KEY DESIGN NOTE:
--   The dashboard chat reads the `richieste` table (one row = one chat bubble),
--   NOT `conversazioni`. So the demo conversation is seeded as `richieste` rows
--   to be visible in the chat. Patient turns render on the left; turns prefixed
--   with the doctor marker ("👨‍⚕️ You:") render on the right. The AI clinical
--   summary lives in `riassunto_clinico` of the final row, which drives the
--   "Clinical summary" card and the record (RAG) query.
--
-- IMPORTANT:
--   - The demo doctor uses the same id as STUDIO_MEDICO_ID
--     (web-app/lib/dashboard/constants.ts), so the founder-patient activation
--     ("Activation <id>") and the dashboard writes all point to the same doctor.
--   - Embeddings are NOT created here (they need OpenAI calls). After running
--     this seed, run `python backfill_index.py` to populate anamnesi_documenti
--     so the "Ask the record" query has indexed content.
--
-- Run once in the Supabase SQL Editor as the postgres role. Idempotent
-- (ON CONFLICT DO NOTHING on fixed ids). Reversible by deleting these ids.

-- 1) Demo doctor. If `medici` has extra NOT NULL columns (e.g. name, email),
--    add them here. Usually the practice doctor already exists -> no-op.
INSERT INTO public.medici (id)
VALUES ('0aec5fee-921d-43bf-87b6-c4019182c742')
ON CONFLICT (id) DO NOTHING;

-- 2) Demo patient (separate from the founder, who will activate their own number).
INSERT INTO public.pazienti (id, nome, telefono, medico_id, gdpr_consent, session_state)
VALUES (
  'a1b2c3d4-0000-4000-8000-000000000001',
  'Sarah Bennett',
  '+390000000001',
  '0aec5fee-921d-43bf-87b6-c4019182c742',
  true,
  'FINISHED'
)
ON CONFLICT (id) DO NOTHING;

-- 3) The WhatsApp conversation, seeded as `richieste` rows so it shows in the
--    dashboard chat. Patient = left bubble; "👨‍⚕️ You:" = right bubble.
--    riassunto_clinico is left empty on message rows so they never override the
--    AI clinical summary card.
INSERT INTO public.richieste
  (id, paziente_id, medico_id, created_at, stato, urgenza, riassunto_clinico, messaggio_originale, url_media)
VALUES
  ('a1b2c3d4-0000-4000-8000-0000000000c1',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days' - interval '40 minutes',
   'gestita', NULL, '',
   'Good morning doctor, for a couple of weeks I have felt very tired and weak, I even struggle to climb the stairs.',
   NULL),
  ('a1b2c3d4-0000-4000-8000-0000000000c2',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days' - interval '38 minutes',
   'gestita', NULL, '',
   '👨‍⚕️ You: I''m sorry to hear that, Sarah. Besides the tiredness, have you noticed other symptoms such as shortness of breath, a racing heartbeat or paleness?',
   NULL),
  ('a1b2c3d4-0000-4000-8000-0000000000c3',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days' - interval '36 minutes',
   'gestita', NULL, '',
   'Yes, sometimes I feel a bit short of breath and I look pale. I had blood tests done: hemoglobin 10.1 g/dL and ferritin 8 ng/mL. I only take folic acid.',
   NULL),
  ('a1b2c3d4-0000-4000-8000-0000000000c4',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days' - interval '34 minutes',
   'gestita', NULL, '',
   '👨‍⚕️ You: Thank you, that is very helpful. Have you had heavy blood loss, intense menstrual periods, or any digestive issues recently?',
   NULL),
  ('a1b2c3d4-0000-4000-8000-0000000000c5',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days' - interval '32 minutes',
   'gestita', NULL, '',
   'My periods have always been heavy. Home blood pressure 125/80. For headaches I occasionally take ibuprofen 400.',
   NULL),
  -- Final AI clinical summary row: marker on the doctor side, summary carries
  -- the structured findings + lab values (drives the card and the RAG query).
  ('a1b2c3d4-0000-4000-8000-0000000000a1',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '3 days' - interval '30 minutes',
   'da gestire', NULL,
   'Asthenia and exertional dyspnea for ~2 weeks. Labs: hemoglobin (Hb) 10.1 g/dL, ferritin 8 ng/mL (mild-moderate iron-deficiency anemia). History of menorrhagia, occasional ibuprofen use. BP 125/80. Likely iron deficiency: consider iron supplementation and gynecological work-up.',
   '👨‍⚕️ You: 📋 Clinical summary updated',
   NULL),
  -- An older, resolved case for record history (older -> not the latest summary).
  ('a1b2c3d4-0000-4000-8000-0000000000a0',
   'a1b2c3d4-0000-4000-8000-000000000001',
   '0aec5fee-921d-43bf-87b6-c4019182c742',
   now() - interval '20 days',
   'gestita', NULL,
   'Recurrent tension-type headache, manageable in the clinic. Advised sleep hygiene and hydration.',
   'I have a headache again like the other times.',
   NULL)
ON CONFLICT (id) DO NOTHING;
