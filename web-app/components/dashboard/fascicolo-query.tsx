"use client";

import { Loader2, Search, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  queryFascicolo,
  type FascicoloSource,
} from "@/lib/actions/fascicolo";

type Props = {
  pazienteId: string;
};

const SOURCE_LABELS: Record<string, string> = {
  referto_ocr: "Report",
  richiesta_sintesi: "Visit summary",
  conversazione: "Conversation",
  manuale: "Manual entry",
};

function formatSourceLabel(source: FascicoloSource): string {
  const base = source.source_type
    ? SOURCE_LABELS[source.source_type] ?? source.source_type
    : "Source";
  if (source.created_at) {
    const d = new Date(source.created_at);
    if (!Number.isNaN(d.getTime())) {
      return `${base} · ${d.toLocaleDateString("en-US")}`;
    }
  }
  return base;
}

export function FascicoloQuery({ pazienteId }: Props) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [sources, setSources] = useState<FascicoloSource[]>([]);

  useEffect(() => {
    setQuery("");
    setAnswer(null);
    setSources([]);
  }, [pazienteId]);

  async function handleAsk() {
    const q = query.trim();
    if (!q) {
      toast.error("Type a question about the patient record.");
      return;
    }
    setLoading(true);
    setAnswer(null);
    setSources([]);
    try {
      const result = await queryFascicolo(pazienteId, q);
      if (!result.ok) {
        toast.error(result.message);
        return;
      }
      setAnswer(result.answer);
      setSources(result.sources);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      className="rounded-xl border border-slate-200/80 bg-white p-8 shadow-sm"
      aria-labelledby="fascicolo-query-heading"
    >
      <div className="flex items-center gap-2">
        <Sparkles className="size-5 text-blue-600" aria-hidden />
        <h3
          id="fascicolo-query-heading"
          className="text-lg font-semibold text-slate-900"
        >
          Ask the record
        </h3>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        Ask a natural-language question about the patient&apos;s documents
        (reports, visit summaries). The answer uses only what is in the record
        and cites its sources.
      </p>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void handleAsk();
            }
          }}
          disabled={loading}
          className="w-full flex-1 rounded-lg border border-slate-200 bg-white px-4 py-3 text-base text-slate-900 placeholder:text-slate-400 focus:border-blue-600 focus:ring-2 focus:ring-blue-600/25"
          placeholder="E.g. What is the latest hemoglobin value? Any known allergies?"
          aria-label="Question about the patient record"
        />
        <Button
          type="button"
          className="min-w-[120px] bg-blue-600 text-white hover:bg-blue-700"
          disabled={loading}
          onClick={() => void handleAsk()}
        >
          {loading ? (
            <>
              <Loader2 className="mr-1.5 size-4 animate-spin" />
              Searching…
            </>
          ) : (
            <>
              <Search className="mr-1.5 size-4" />
              Ask
            </>
          )}
        </Button>
      </div>

      {answer ? (
        <div className="mt-5 rounded-lg border border-blue-100 bg-blue-50/60 p-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
            {answer}
          </p>
          {sources.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {sources.map((s, i) => (
                <span
                  key={`${s.source_id ?? "src"}-${i}`}
                  className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-medium text-slate-600"
                  title={s.content ?? undefined}
                >
                  {formatSourceLabel(s)}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
