"use client";

import { Pencil } from "lucide-react";
import { useEffect, useState } from "react";
import { ChatSection } from "@/components/dashboard/chat-section";
import { ClinicalSummary } from "@/components/dashboard/clinical-summary";
import { FascicoloQuery } from "@/components/dashboard/fascicolo-query";
import { PatientPrivateNotes } from "@/components/dashboard/patient-private-notes";
import { RecapSection } from "@/components/dashboard/recap-section";
import type { PatientProfile, RichiestaRow } from "@/lib/dashboard/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  profile: PatientProfile;
  requests: RichiestaRow[];
  sending: boolean;
  onSendMessage: (payload: {
    text: string;
    file: File | null;
  }) => Promise<boolean>;
  onNotesSaved: () => void;
  updatePatientName: (patientId: string, newName: string) => Promise<void>;
};

export function PatientMainArea({
  profile,
  requests,
  sending,
  onSendMessage,
  onNotesSaved,
  updatePatientName,
}: Props) {
  const [isEditingName, setIsEditingName] = useState(false);
  const [draftName, setDraftName] = useState(profile.nomeRaw ?? "");

  useEffect(() => {
    if (!isEditingName) {
      setDraftName(profile.nomeRaw ?? "");
    }
  }, [isEditingName, profile.nomeRaw]);

  async function commitNameEdit() {
    const nextName = draftName.trim();
    setIsEditingName(false);
    await updatePatientName(profile.id, nextName);
  }

  return (
    <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-white">
      <header className="shrink-0 border-b border-slate-200/90 px-4 py-3 md:px-6 md:py-4">
        {isEditingName ? (
          <input
            autoFocus
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            onBlur={() => void commitNameEdit()}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void commitNameEdit();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                setIsEditingName(false);
                setDraftName(profile.nomeRaw ?? "");
              }
            }}
            className="w-full max-w-xl rounded-md border border-slate-300 bg-white px-3 py-1.5 text-lg font-semibold tracking-tight text-slate-900 outline-none ring-0 transition focus:border-blue-400 focus:ring-2 focus:ring-blue-100 md:text-xl"
            aria-label="Modifica nome paziente"
            placeholder="Nome paziente"
          />
        ) : (
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold tracking-tight text-slate-900 md:text-xl">
              {profile.nomeDisplay}
            </h1>
            <button
              type="button"
              onClick={() => setIsEditingName(true)}
              className="inline-flex items-center justify-center rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              aria-label="Modifica nome paziente"
              title="Modifica nome paziente"
            >
              <Pencil className="size-4" />
            </button>
          </div>
        )}
        <p className="mt-1 font-mono text-sm text-slate-500">{profile.telefono}</p>
      </header>

      <Tabs
        defaultValue="fascicolo"
        className="flex min-h-0 w-full flex-1 flex-col gap-0"
      >
        <div className="shrink-0 border-b border-slate-200 bg-white px-4 md:px-6">
          <TabsList
            variant="line"
            className="h-11 w-full justify-start gap-4 rounded-none border-0 bg-transparent p-0 md:gap-10"
          >
            <TabsTrigger
              value="fascicolo"
              className="relative rounded-none border-0 bg-transparent px-0 py-2.5 text-sm font-medium text-slate-500 shadow-none after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:rounded-full after:bg-transparent after:transition-colors data-[state=active]:text-slate-900 data-[state=active]:after:bg-blue-600"
            >
              Fascicolo Medico
            </TabsTrigger>
            <TabsTrigger
              value="chat"
              className="relative rounded-none border-0 bg-transparent px-0 py-2.5 text-sm font-medium text-slate-500 shadow-none after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:rounded-full after:bg-transparent after:transition-colors data-[state=active]:text-slate-900 data-[state=active]:after:bg-blue-600"
            >
              Chat WhatsApp
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent
          value="fascicolo"
          className="mt-0 flex min-h-0 flex-1 flex-col overflow-hidden outline-none data-[state=inactive]:hidden"
        >
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-8">
            <div className="mx-auto flex max-w-3xl flex-col gap-6 md:gap-10">
              <ClinicalSummary requests={requests} />
              <FascicoloQuery pazienteId={profile.id} />
              <PatientPrivateNotes
                pazienteId={profile.id}
                initialNote={profile.notePrivate}
                onSaved={onNotesSaved}
                spacious
              />
              <RecapSection
                requests={requests}
                fascicoloLayout
                galleryVisualOnly
                hideSummary
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent
          value="chat"
          className="mt-0 flex min-h-0 flex-1 flex-col overflow-hidden outline-none data-[state=inactive]:hidden"
        >
          <ChatSection
            pazienteId={profile.id}
            requests={requests}
            sending={sending}
            onSend={onSendMessage}
            variant="crmColumn"
            className="min-h-0 flex-1"
          />
        </TabsContent>
      </Tabs>
    </main>
  );
}
