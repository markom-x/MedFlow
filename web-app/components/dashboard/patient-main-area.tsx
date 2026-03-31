"use client";

import { ChatSection } from "@/components/dashboard/chat-section";
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
};

export function PatientMainArea({
  profile,
  requests,
  sending,
  onSendMessage,
  onNotesSaved,
}: Props) {
  return (
    <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-white">
      <header className="shrink-0 border-b border-slate-200/90 px-4 py-3 md:px-6 md:py-4">
        <h1 className="text-lg font-semibold tracking-tight text-slate-900 md:text-xl">
          {profile.nomeDisplay}
        </h1>
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
