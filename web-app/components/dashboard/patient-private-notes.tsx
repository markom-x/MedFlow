"use client";

import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { updatePatientPrivateNotes } from "@/lib/actions";
import { cn } from "@/lib/utils";

type Props = {
  pazienteId: string;
  initialNote: string | null;
  onSaved: () => void;
  /** Note basse con possibilità di espandere (layout fascicolo destro) */
  compact?: boolean;
  /** Layout arioso nel tab Fascicolo */
  spacious?: boolean;
};

export function PatientPrivateNotes({
  pazienteId,
  initialNote,
  onSaved,
  compact = false,
  spacious = false,
}: Props) {
  const [text, setText] = useState(initialNote ?? "");
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setText(initialNote ?? "");
  }, [pazienteId, initialNote]);

  async function handleSave() {
    setSaving(true);
    try {
      const result = await updatePatientPrivateNotes(pazienteId, text);
      if (!result.ok) {
        toast.error(result.message);
        return;
      }
      toast.success("Notes saved");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  const rows = spacious ? 5 : compact ? (expanded ? 10 : 3) : 4;

  return (
    <section
      className={cn(
        "rounded-xl border border-slate-200 bg-white shadow-sm",
        compact && "border-slate-200/90 bg-white/90 p-3",
        spacious && "border-slate-200/80 p-8",
        !compact && !spacious && "p-3"
      )}
      aria-labelledby="note-private-heading"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3
            id="note-private-heading"
            className={cn(
              "font-semibold text-slate-900",
              spacious ? "text-lg" : "text-sm"
            )}
          >
            Internal notes (visible only to you)
          </h3>
          <p
            className={cn(
              "text-slate-600",
              spacious ? "mt-2 text-sm" : "mt-0.5 text-xs"
            )}
          >
            Not sent to the patient.
          </p>
        </div>
        {compact ? (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            {expanded ? (
              <>
                Collapse <ChevronUp className="size-3.5" aria-hidden />
              </>
            ) : (
              <>
                Expand <ChevronDown className="size-3.5" aria-hidden />
              </>
            )}
          </button>
        ) : null}
      </div>
      <label htmlFor="note-private" className="sr-only">
        Internal notes
      </label>
      <textarea
        id="note-private"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={rows}
        className={cn(
          "mt-2 w-full resize-y rounded-lg border border-slate-200 bg-white text-slate-900 placeholder:text-slate-400 focus:border-blue-600 focus:ring-2 focus:ring-blue-600/25",
          spacious &&
            "mt-4 min-h-[8rem] px-4 py-3 text-base",
          !spacious && "px-2.5 py-2 text-sm",
          compact && "max-h-[min(40vh,22rem)] min-h-[4.5rem]"
        )}
        placeholder="E.g. allergies, preferences, follow-up…"
      />
      <div className={cn("flex justify-end", spacious ? "mt-4" : "mt-2")}>
        <Button
          type="button"
          size={spacious ? "default" : "sm"}
          className="min-w-[120px] bg-blue-600 text-white hover:bg-blue-700"
          disabled={saving}
          onClick={() => void handleSave()}
        >
          {saving ? (
            <>
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              Saving…
            </>
          ) : (
            "Save"
          )}
        </Button>
      </div>
    </section>
  );
}
