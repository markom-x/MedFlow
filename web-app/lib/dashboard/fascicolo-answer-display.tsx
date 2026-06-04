import type { ReactNode } from "react";

/** Intro phrases returned by the fascicolo synthesizer (shown slightly muted). */
const ANSWER_PREFIX_RE =
  /^(From the patient(?:'s)? record:\s*|Based on the record —\s*|Body temperature documented in the record:\s*|The patient reported:\s*|Clinical summary:\s*)/i;

/**
 * Values worth a subtle highlight: vitals, labs, BP, doses, quoted patient text.
 */
const VALUE_HIGHLIGHT_RE =
  /("(?:[^"]*)"|'(?:[^']*)'|\b\d{2,3}\/\d{2,3}\b|\b\d+(?:\.\d+)?(?:\s*(?:°[CF]|U\/L|mg\/L|g\/dL|mmol\/L|mmHg|\/μL|%))?)/gi;

function splitHighlightedSpans(text: string): { highlight: boolean; value: string }[] {
  const parts: { highlight: boolean; value: string }[] = [];
  let last = 0;
  const re = new RegExp(VALUE_HIGHLIGHT_RE.source, VALUE_HIGHLIGHT_RE.flags);
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > last) {
      parts.push({ highlight: false, value: text.slice(last, idx) });
    }
    parts.push({ highlight: true, value: m[0] });
    last = idx + m[0].length;
  }
  if (last < text.length) {
    parts.push({ highlight: false, value: text.slice(last) });
  }
  return parts.length ? parts : [{ highlight: false, value: text }];
}

const highlightClass =
  "rounded-sm bg-sky-100/90 px-1 py-px font-medium text-slate-900 ring-1 ring-sky-200/60";

/** Renders fascicolo answer text with muted lead-in and soft value highlights. */
export function FascicoloAnswerDisplay({ answer }: { answer: string }) {
  const prefixMatch = answer.match(ANSWER_PREFIX_RE);
  const prefix = prefixMatch?.[0] ?? "";
  const body = prefix ? answer.slice(prefix.length) : answer;
  const spans = splitHighlightedSpans(body);

  const nodes: ReactNode[] = [];
  if (prefix) {
    nodes.push(
      <span key="prefix" className="text-slate-600">
        {prefix}
      </span>
    );
  }
  spans.forEach((seg, i) => {
    if (seg.highlight) {
      nodes.push(
        <span key={`h-${i}`} className={highlightClass}>
          {seg.value}
        </span>
      );
    } else {
      nodes.push(<span key={`t-${i}`}>{seg.value}</span>);
    }
  });

  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
      {nodes}
    </p>
  );
}
