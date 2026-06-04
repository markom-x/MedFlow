import type { FascicoloSource } from "@/lib/actions/fascicolo";

/** One chip per source type + day (matches backend dedupe). */
export function dedupeFascicoloSources(
  sources: FascicoloSource[],
  limit = 3
): FascicoloSource[] {
  const seen = new Set<string>();
  const out: FascicoloSource[] = [];
  for (const s of sources) {
    const st = s.source_type ?? "source";
    const day = (s.created_at ?? "").slice(0, 10);
    const key = `${st}|${day}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
    if (out.length >= limit) break;
  }
  return out;
}
