# 🌊 MedFlow
**The AI-Powered Visit Copilot for doctors.**

![MedFlow UI Preview](https://via.placeholder.com/1000x500?text=Premium+Next.js+Dashboard+Preview) ## 📖 Overview
Being a doctor is a calling, but today, that calling is being drowned in a sea of administrative noise. Doctors waste hours deciphering chaotic info, asking routine anamnesis questions, and squinting at photos of old, crumpled lab results. It’s not just inefficient; it’s a barrier between the healer and the patient.

**MedFlow** changes this. It is an active clinical copilot that takes the raw chaos of patient clinical history and elegantly transforms it into structured and clear info. 

It intercepts patients on WhatsApp, empathetically conducts a structured anamnesis, extracts vital data from photos of medical reports, and delivers a pristine, actionable summary to a dashboard. No more sorting. No more data-entry. Just the right information, at the right time, so doctors can do the only thing that matters: *heal*.

## ✨ Core Features

- **🧠 Active AI Anamnesis:** Powered by OpenAI, the bot conducts a dynamic, structured interview (Remote & Proximal Anamnesis, Medications, Allergies) based on the patient's initial symptoms and reason of the visit.
- **👁️ Vision & OCR Integration:** Patients can send photos of past medical reports, physical symptoms or prescriptions. MedFlow reads, extracts, and contextualizes the data instantly.
- **🎙️ Voice-to-Clinical JSON:** Transcribes 2-minute panicked voice notes via Whisper and structures them into urgent clinical entities (Urgency level, key symptoms, duration).
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

1. **The Hook:** Patient sends a message/audio/photo to the doctor's number.
2. **The Interview:** MedFlow acknowledges the message and asks 2-3 targeted questions to build the clinical picture.
3. **The Processing:** LLM parses the entire conversation into a strictly typed JSON (Symptoms, Urgency, Anamnesis).
4. **The Delivery:** The doctor opens the Next.js dashboard and sees the fully compiled patient card, ready for the visit.
