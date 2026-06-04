# 🌊 MedFlow
**The AI-Powered Visit Copilot for doctors.**

Being a doctor is a calling, but today, that calling is being drowned in a sea of administrative noise. Doctors waste hours deciphering chaotic info, scrolling through endless chat threads, and squinting at photos of old, crumpled lab results. It’s not just inefficient; it’s a barrier between the healer and the patient.

**MedFlow** changes this. It is a passive clinical copilot that takes the raw chaos of patient clinical history and elegantly transforms it into structured, instantly queryable knowledge.

The doctor stays in full control of the relationship: **MedFlow never talks to the patient and never asks questions on the doctor's behalf.** Patients write freely on WhatsApp, the doctor replies however and whenever they want, and in the background MedFlow silently ingests everything — text, voice notes, photos of medical reports — and turns it into a clean, searchable clinical memory. Then the doctor can simply *ask*: "What medications did this patient mention?", "When did the chest pain start?", "Show me their last lab results." No more sorting. No more data-entry. Just the right information, at the right time, so doctors can do the only thing that matters: *heal*.

## ✨ Core Features

- **🔎 Intelligent Clinical Query:** Powered by OpenAI and semantic search (RAG over pgvector), the doctor can ask any question in natural language about what the patient has shared — symptoms, medications, allergies, timelines — and get a grounded answer drawn straight from the conversation history.
- **🙌 Doctor-Led, Zero Interference:** The AI never messages the patient and never conducts an interview. The doctor owns the entire conversation; MedFlow only listens, structures, and assists on request.
- **👁️ Vision & OCR Integration:** Patients can send photos of past medical reports, physical symptoms or prescriptions. MedFlow reads, extracts, and contextualizes the data instantly into the patient's clinical memory.
- **🎙️ Voice-to-Clinical Memory:** Transcribes voice notes via Whisper and structures them into searchable clinical entities (key symptoms, duration, urgency cues) ready to be queried later.
- **⚡ Clear Dashboard:** A high-performance, glassmorphic Next.js interface that gives doctors a kanban-style inbox of their patients, eliminating cognitive load.

## 🛠️ Tech Stack

**Backend (The Brain)**
- **Python / FastAPI:** High-performance, asynchronous API routing.
- **Twilio API:** Seamless WhatsApp business integration.
- **OpenAI:** NLP, OCR, and medical entity extraction.

**Frontend (The Canvas)**
- **Next.js 14:** React framework for speed and SEO.
- **Tailwind CSS & Framer Motion:** For a premium aesthetic and fluid animations.
- **Lucide React:** Clean, modern iconography.

**Infrastructure (The Engine)**
- **Supabase:** PostgreSQL database and Auth (Realtime sync for the dashboard).
- **Vercel & Render:** Cloud deployment for zero-downtime availability.

## 🚀 How it Works (The Flow)

1. **The Input:** Patient sends a message/audio/photo to the doctor's number, and the doctor replies freely — MedFlow stays out of the conversation.
2. **The Ingestion:** Every turn (patient and doctor) is silently transcribed, OCR'd, and embedded into a searchable clinical memory.
3. **The Query:** The doctor asks MedFlow anything in natural language; semantic search retrieves the relevant pieces and the LLM returns a grounded, structured answer.
4. **The Delivery:** The doctor opens the Next.js dashboard, sees the compiled patient card, and queries any detail on demand — ready for the visit.
