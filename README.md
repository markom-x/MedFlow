# MedExtract 🩺

An AI-powered medical triage assistant that turns chaotic WhatsApp messages into a structured, real-time dashboard for doctors. 

## The Problem
Doctors increasingly use WhatsApp to communicate with patients. The result? A fragmented mess of voice notes, blurry photos of lab results, and anxious text walls. It creates severe cognitive overload, makes triage nearly impossible, and wastes hours of clinical time.

## What it does
MedExtract intercepts patient messages via a WhatsApp bot and processes them instantly:
- **Multimodal ingestion:** Handles text, audio (auto-transcribed), and images/PDFs (medical reports).
- **AI Triage:** Uses GPT-4o to extract key symptoms, current medications, and automatically assigns a clinical urgency level.
- **Real-time Dashboard:** Drops the processed ticket onto the doctor's screen instantly without requiring a page refresh.

## Tech Stack
- **Frontend:** Next.js 14 (App Router), Tailwind CSS
- **Backend:** Python / FastAPI (Serverless on Render)
- **Database & Realtime:** Supabase (PostgreSQL + Realtime WebSockets)
- **AI Models:** OpenAI (GPT-4o for clinical extraction, Whisper for speech-to-text)
- **Integration:** Twilio WhatsApp API

## Architecture Highlights
Building a seamless bridge between a slow LLM and real-time UI required solving a few core engineering challenges:
- **Zero-Timeout Webhooks:** Twilio terminates connections if a webhook takes longer than 15 seconds, but LLM processing and media downloading often exceed this. We implemented asynchronous FastAPI Background Tasks to instantly acknowledge Twilio's payload while running the heavy AI pipeline in the background.
- **State Synchronization:** Next.js Server Components caching can easily clash with Supabase Realtime WebSocket payloads. We built a custom merge logic to keep the local React state strictly in sync with the server database, preventing stale closures and UI tearing.
